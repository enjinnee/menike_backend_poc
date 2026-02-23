import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from app.core.auth import get_current_tenant_id
from app.core.database import get_session
from app.core.milvus_client import milvus_client
from app.models.sql_models import CinematicClip
from app.services.embedding import generate_embedding
from app.services.storage import storage_service
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/cinematic-clips", tags=["Cinematic Clips (Manual Upload)"])


def _tenant_clip_key(tenant_id: str, key: str) -> str:
    normalized = key.strip("/")
    tenant_prefix = f"tenants/{tenant_id}/clips/"
    if normalized.startswith(tenant_prefix):
        return normalized
    if normalized.startswith(f"tenants/{tenant_id}/"):
        filename = normalized.split("/")[-1]
        return f"{tenant_prefix}{filename}"
    if "/" in normalized:
        filename = normalized.split("/")[-1]
        return f"{tenant_prefix}{filename}"
    return f"{tenant_prefix}{normalized}"


class ClipCreate(BaseModel):
    name: str
    tags: str               # comma-separated: "galle,fort,drone,sunset"
    video_url: Optional[str] = None        # S3 URL of the pre-made clip
    s3_key: Optional[str] = None           # Relative key under configured S3 base prefix
    duration: Optional[float] = None
    description: Optional[str] = None
    location: Optional[str] = None         # e.g. "Galle, Sri Lanka"
    type: Optional[str] = None            # e.g. "drone", "timelapse", "underwater", "ground"
    reviews: Optional[str] = None         # e.g. "4.9/5 - Perfect for travel reels"
    approximate: Optional[str] = None     # e.g. "Duration: 30s, Resolution: 4K"


class ClipResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    tags: str
    video_url: str
    duration: Optional[float]
    description: Optional[str]
    location: Optional[str]
    type: Optional[str]
    reviews: Optional[str]
    approximate: Optional[str]
    created_at: str


class ClipSearchRequest(BaseModel):
    query: str              # Natural language: "drone shot of historic fort"
    limit: int = 5


class ClipSearchResult(BaseModel):
    id: str
    name: str
    tags: str
    video_url: str
    duration: Optional[float]
    similarity_score: float


@router.post("/", response_model=ClipResponse)
async def upload_clip(
    data: ClipCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """
    Upload a pre-generated cinematic video clip.
    Dual-write: PostgreSQL (tracking) + Milvus (semantic search).
    """
    if not data.video_url and not data.s3_key:
        raise HTTPException(status_code=400, detail="Provide either video_url or s3_key")

    video_url = data.video_url
    if not video_url:
        tenant_safe_key = _tenant_clip_key(tenant_id, data.s3_key or "")
        video_url = storage_service.get_url(tenant_safe_key)

    # 1. Save to PostgreSQL (tracking)
    clip = CinematicClip(
        tenant_id=tenant_id,
        name=data.name,
        tags=data.tags.lower(),
        video_url=video_url,
        duration=data.duration,
        description=data.description,
        location=data.location,
        type=data.type,
        reviews=data.reviews,
        approximate=data.approximate,
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)

    # 2. Generate embedding and save to Milvus (semantic search)
    text_for_embedding = f"{data.name} {data.tags} {data.description or ''} {data.location or ''} {data.type or ''}"
    embedding = generate_embedding(text_for_embedding)
    metadata = {
        "name": data.name,
        "tags": data.tags.lower(),
        "video_url": video_url,
        "duration": data.duration,
        "location": data.location or "",
        "type": data.type or "",
        "pg_id": clip.id,
    }
    milvus_client.insert_clip_vector(clip.id, tenant_id, embedding, metadata)

    return ClipResponse(
        id=clip.id, tenant_id=clip.tenant_id, name=clip.name,
        tags=clip.tags, video_url=clip.video_url,
        duration=clip.duration, description=clip.description,
        location=clip.location, type=clip.type,
        reviews=clip.reviews, approximate=clip.approximate,
        created_at=str(clip.created_at),
    )


@router.post("/upload-file", response_model=ClipResponse)
async def upload_clip_file(
    name: str = Form(...),
    tags: str = Form(...),
    duration: Optional[float] = Form(default=None),
    description: Optional[str] = Form(default=None),
    location: Optional[str] = Form(default=None),
    type: Optional[str] = Form(default=None),
    reviews: Optional[str] = Form(default=None),
    approximate: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session),
):
    content = await file.read()
    ext = os.path.splitext(file.filename or "")[1].lower() or ".mp4"
    object_key = f"tenants/{tenant_id}/clips/{uuid.uuid4()}{ext}"
    video_url = storage_service.upload_bytes(content, object_key, file.content_type)

    clip = CinematicClip(
        tenant_id=tenant_id,
        name=name,
        tags=tags.lower(),
        video_url=video_url,
        duration=duration,
        description=description,
        location=location,
        type=type,
        reviews=reviews,
        approximate=approximate,
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)

    text_for_embedding = f"{name} {tags} {description or ''} {location or ''} {type or ''}"
    embedding = generate_embedding(text_for_embedding)
    metadata = {
        "name": name,
        "tags": tags.lower(),
        "video_url": video_url,
        "duration": duration,
        "location": location or "",
        "type": type or "",
        "pg_id": clip.id,
    }
    milvus_client.insert_clip_vector(clip.id, tenant_id, embedding, metadata)

    return ClipResponse(
        id=clip.id, tenant_id=clip.tenant_id, name=clip.name,
        tags=clip.tags, video_url=clip.video_url,
        duration=clip.duration, description=clip.description,
        location=clip.location, type=clip.type,
        reviews=clip.reviews, approximate=clip.approximate,
        created_at=str(clip.created_at),
    )


@router.get("/", response_model=List[ClipResponse])
async def list_clips(
    tenant_id: str = Depends(get_current_tenant_id),
    session: Session = Depends(get_session)
):
    """List all cinematic clips for the tenant (from PostgreSQL)."""
    statement = select(CinematicClip).where(CinematicClip.tenant_id == tenant_id)
    clips = session.exec(statement).all()
    return [
        ClipResponse(
            id=c.id, tenant_id=c.tenant_id, name=c.name,
            tags=c.tags, video_url=c.video_url,
            duration=c.duration, description=c.description,
            location=c.location, type=c.type,
            reviews=c.reviews, approximate=c.approximate,
            created_at=str(c.created_at),
        ) for c in clips
    ]


@router.post("/search", response_model=List[ClipSearchResult])
async def search_clips(
    req: ClipSearchRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    Semantic search for cinematic clips using Milvus vector similarity.
    Example: query="aerial coastal view" will match beach/drone clips.
    """
    query_embedding = generate_embedding(req.query)
    results = milvus_client.search_clips(tenant_id, query_embedding, req.limit)

    output = []
    for hits in results:
        for hit in hits:
            meta = hit.entity.get("metadata", {})
            output.append(ClipSearchResult(
                id=hit.id,
                name=meta.get("name", ""),
                tags=meta.get("tags", ""),
                video_url=meta.get("video_url", ""),
                duration=meta.get("duration"),
                similarity_score=round(1 - hit.distance, 4),
            ))
    return output
