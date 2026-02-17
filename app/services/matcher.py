"""
Matcher service: finds the best matching image and cinematic clip
for each itinerary activity using Milvus semantic search.
"""
from typing import Optional, Set
from app.core.milvus_client import milvus_client
from app.services.embedding import generate_embedding
from app.models.sql_models import ImageLibrary, CinematicClip

class MatchedResult:
    def __init__(self, id: str, url: str):
        self.id = id
        self.url = url

def match_image(
    tenant_id: str,
    query_text: str,
    exclude_ids: Optional[Set[str]] = None,
) -> Optional[MatchedResult]:
    """
    Find the best matching image from Milvus by semantic similarity.
    query_text: "Visit Galle Fort, heritage, sunset"
    """
    embedding = generate_embedding(query_text)
    results = milvus_client.search_images(tenant_id, embedding, limit=5)
    blocked = exclude_ids or set()

    if results and len(results) > 0 and len(results[0]) > 0:
        for hit in results[0]:
            hit_id = str(hit.id)
            if hit_id in blocked:
                continue
            meta = hit.entity.get("metadata", {})
            # We inserted vectors with image.id as Milvus id.
            return MatchedResult(id=hit_id, url=meta.get("image_url"))

        # All candidates were excluded; fall back to top result.
        hit = results[0][0]
        meta = hit.entity.get("metadata", {})
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
