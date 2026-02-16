from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from app.models.experience import Experience
from app.core.milvus_client import milvus_client
import json

router = APIRouter(prefix="/experiences", tags=["Experiences (Vector Search)"])

@router.get("/", response_model=List[Experience])
async def list_experiences(limit: int = 100):
    try:
        results = milvus_client.list_experiences(limit)
        experiences = []
        for res in results:
            metadata = res.get("metadata", {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            
            full_data = {
                **metadata,
                "id": res["id"],
                "tenantId": res["tenant_id"],
                "slug": res["slug"],
                "embedding": res.get("embedding")
            }
            experiences.append(Experience(**full_data))
        return experiences
    except Exception as e:
        if "ConnectionNotExistException" in str(e) or "Fail connecting to server" in str(e):
            raise HTTPException(
                status_code=503, 
                detail="Milvus service is not running. Please start Milvus to access Experiences."
            )
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=Experience)
async def create_experience(experience: Experience):
    try:
        metadata = experience.model_dump(exclude={"embedding"})
        milvus_data = [
            [experience.id],
            [experience.tenantId],
            [experience.embedding],
            [metadata],
            [experience.slug]
        ]
        milvus_client.insert_experience(milvus_data)
        return experience
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search/", response_model=List[dict])
async def search_experiences(
    tenant_id: str,
    embedding: List[float],
    limit: int = 10
):
    try:
        results = milvus_client.search_experiences(tenant_id, embedding, limit)
        output = []
        for hits in results:
            for hit in hits:
                output.append({
                    "id": hit.id,
                    "distance": hit.distance,
                    "metadata": hit.entity.get("metadata")
                })
        return output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
