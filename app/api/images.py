from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_tenant_id
from app.core.database import get_session
from app.core.milvus_client import milvus_client
from app.models.sql_models import ImageLibrary
from app.services.embedding import generate_embedding
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/images", tags=["Image Library"])


class ImageCreate(BaseModel):
    name: str
    tags: str           # comma-separated: "galle,fort,sunset"
    location: Optional[str] = None
    image_url: str      # S3 URL


class ImageResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    tags: str
    location: Optional[str]
    image_url: str
    created_at: str


class ImageSearchRequest(BaseModel):
    query: str          # Natural language: "beautiful beach at sunset"
    limit: int = 5


class ImageSearchResult(BaseModel):
    id: str
    name: str
    tags: str
    image_url: str
    similarity_score: float


@router.post("/", response_model=ImageResponse)
async def upload_image(
    data: ImageCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """
    Upload an image to the tenant's library.
    Dual-write: PostgreSQL (tracking) + Milvus (semantic search).
    """
    # 1. Save to PostgreSQL (tracking)
    image = ImageLibrary(
        tenant_id=tenant_id,
        name=data.name,
        tags=data.tags.lower(),
        location=data.location,
        image_url=data.image_url,
    )
    session.add(image)
    session.commit()
    session.refresh(image)

    # 2. Generate embedding and save to Milvus (semantic search)
    text_for_embedding = f"{data.name} {data.tags} {data.location or ''}"
    embedding = generate_embedding(text_for_embedding)
    metadata = {
        "name": data.name,
        "tags": data.tags.lower(),
        "location": data.location or "",
        "image_url": data.image_url,
        "pg_id": image.id,  # Link back to PostgreSQL
    }
    milvus_client.insert_image_vector(image.id, tenant_id, embedding, metadata)

    return ImageResponse(
        id=image.id, tenant_id=image.tenant_id, name=image.name,
        tags=image.tags, location=image.location, image_url=image.image_url,
        created_at=str(image.created_at),
    )


@router.get("/", response_model=List[ImageResponse])
async def list_images(
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """List all images in the tenant's library (from PostgreSQL)."""
    statement = select(ImageLibrary).where(ImageLibrary.tenant_id == tenant_id)
    images = session.exec(statement).all()
    return [
        ImageResponse(
            id=img.id, tenant_id=img.tenant_id, name=img.name,
            tags=img.tags, location=img.location, image_url=img.image_url,
            created_at=str(img.created_at),
        ) for img in images
    ]


@router.post("/search", response_model=List[ImageSearchResult])
async def search_images(
    req: ImageSearchRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Semantic search for images using Milvus vector similarity.
    Example: query="ancient fortress at sunset" will match "Galle Fort" images.
    """
    # Generate embedding for the search query
    query_embedding = generate_embedding(req.query)

    # Search Milvus
    results = milvus_client.search_images(tenant_id, query_embedding, req.limit)

    output = []
    for hits in results:
        for hit in hits:
            meta = hit.entity.get("metadata", {})
            output.append(ImageSearchResult(
                id=hit.id,
                name=meta.get("name", ""),
                tags=meta.get("tags", ""),
                image_url=meta.get("image_url", ""),
                similarity_score=round(1 - hit.distance, 4),  # COSINE: lower distance = higher similarity
            ))
    return output
