"""
Matcher service: finds the best matching image and cinematic clip
for each itinerary activity using Milvus semantic search.
"""
from typing import Optional
from app.core.milvus_client import milvus_client
from app.services.embedding import generate_embedding
from app.models.sql_models import ImageLibrary, CinematicClip

class MatchedResult:
    def __init__(self, id: str, url: str):
        self.id = id
        self.url = url

def match_image(tenant_id: str, query_text: str) -> Optional[MatchedResult]:
    """
    Find the best matching image from Milvus by semantic similarity.
    query_text: "Visit Galle Fort, heritage, sunset"
    """
    embedding = generate_embedding(query_text)
    results = milvus_client.search_images(tenant_id, embedding, limit=1)
    
    if results and len(results) > 0 and len(results[0]) > 0:
        hit = results[0][0]
        meta = hit.entity.get("metadata", {})
        # We need the postgres ID (pg_id) if we stored it, or the Milvus ID if they are the same.
        # Check how we inserted it. In images.py: milvus_client.insert_image_vector(image.id, ...)
        # So hit.id is the Postgres ID.
        return MatchedResult(id=str(hit.id), url=meta.get("image_url"))
    return None


def match_clip(tenant_id: str, query_text: str) -> Optional[MatchedResult]:
    """
    Find the best matching cinematic clip from Milvus by semantic similarity.
    """
    embedding = generate_embedding(query_text)
    results = milvus_client.search_clips(tenant_id, embedding, limit=1)
    
    if results and len(results) > 0 and len(results[0]) > 0:
        hit = results[0][0]
        meta = hit.entity.get("metadata", {})
        return MatchedResult(id=str(hit.id), url=meta.get("video_url"))
    return None
