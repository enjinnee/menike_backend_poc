from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_tenant_id
from app.core.database import get_session
from app.core.milvus_client import milvus_client
from app.models.sql_models import CinematicClip
from app.services.embedding import generate_embedding
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/cinematic-clips", tags=["Cinematic Clips (Manual Upload)"])


class ClipCreate(BaseModel):
    name: str
    tags: str               # comma-separated: "galle,fort,drone,sunset"
    video_url: str           # S3 URL of the pre-made clip
    duration: Optional[float] = None
    description: Optional[str] = None


class ClipResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    tags: str
    video_url: str
    duration: Optional[float]
    description: Optional[str]
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
    # 1. Save to PostgreSQL (tracking)
    clip = CinematicClip(
        tenant_id=tenant_id,
        name=data.name,
        tags=data.tags.lower(),
        video_url=data.video_url,
        duration=data.duration,
        description=data.description,
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)

    # 2. Generate embedding and save to Milvus (semantic search)
    text_for_embedding = f"{data.name} {data.tags} {data.description or ''}"
    embedding = generate_embedding(text_for_embedding)
    metadata = {
        "name": data.name,
        "tags": data.tags.lower(),
        "video_url": data.video_url,
        "duration": data.duration,
        "pg_id": clip.id,  # Link back to PostgreSQL
    }
    milvus_client.insert_clip_vector(clip.id, tenant_id, embedding, metadata)

    return ClipResponse(
        id=clip.id, tenant_id=clip.tenant_id, name=clip.name,
        tags=clip.tags, video_url=clip.video_url,
        duration=clip.duration, description=clip.description,
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
