"""
Matcher service: finds the best matching image and cinematic clip
for each itinerary activity using Milvus semantic search.

Match quality is improved by a two-stage approach:
  1. Milvus vector search retrieves the top-N candidates by cosine similarity.
  2. A token-overlap re-ranker scores each candidate against the query tokens
     and boosts/penalises based on tag/name overlap before selecting the best.
     Candidates whose combined score falls below MIN_MATCH_SCORE are rejected
     so that semantically similar but contextually wrong clips are not used.
"""
import re
from typing import Optional, Set
from app.core.milvus_client import milvus_client
from app.services.embedding import generate_embedding
from app.models.sql_models import ImageLibrary, CinematicClip

# Candidates with a combined (vector + token-overlap) score below this threshold
# will be rejected rather than used as a bad match.  0.0 disables the filter.
MIN_MATCH_SCORE = float(0.10)

# Words that carry no discriminative power and should be ignored when comparing
# query tokens against clip metadata.
_NOISE_WORDS = {
    "a", "an", "the", "at", "in", "on", "to", "of", "for", "near",
    "with", "and", "or", "is", "are", "was", "be", "by", "from",
    "visit", "explore", "experience", "enjoy",
}


def _tokenize(text: str) -> Set[str]:
    """Lowercase alpha tokens, at least 3 chars, excluding noise words."""
    tokens = re.findall(r'[a-z]+', (text or "").lower())
    return {t for t in tokens if len(t) >= 3 and t not in _NOISE_WORDS}


def _token_overlap_score(query_tokens: Set[str], meta: dict) -> float:
    """
    Return a 0–1 overlap score between the query and a clip's metadata tokens.

    We extract tokens from name + tags + location, then compute
    Jaccard similarity: |intersection| / |union|.

    A clip labelled "Sigiriya Rock Climbing drone" vs a query for
    "Lunch near Sigiriya" will share only "sigiriya" (1 token) while
    the union is much larger → low score.
    A clip labelled "Sigiriya Rock Climbing" vs query "Climbing Sigiriya"
    will share "sigiriya" and "climbing" → much higher score.
    """
    meta_text = " ".join([
        meta.get("name", ""),
        meta.get("tags", ""),
        meta.get("location", ""),
    ])
    meta_tokens = _tokenize(meta_text)
    if not query_tokens or not meta_tokens:
        return 0.0
    intersection = query_tokens & meta_tokens
    union = query_tokens | meta_tokens
    return len(intersection) / len(union)


class MatchedResult:
    def __init__(self, id: str, url: str):
        self.id = id
        self.url = url


def _pick_best(hits, query_tokens: Set[str], url_field: str, blocked: Set[str]) -> Optional[MatchedResult]:
    """
    From a list of Milvus search hits, select the best non-blocked candidate
    using a combined score:  cosine_similarity * 0.6 + token_overlap * 0.4

    If all scored candidates fall below MIN_MATCH_SCORE, return None so the
    caller can fall back to Pexels / map-transition rather than a wrong clip.
    """
    scored = []
    for hit in hits:
        hit_id = str(hit.id)
        if hit_id in blocked:
            continue
        meta = hit.entity.get("metadata", {})
        # Milvus COSINE distance is in [0,2]; convert to similarity [0,1]
        cosine_sim = max(0.0, 1.0 - hit.distance)
        overlap = _token_overlap_score(query_tokens, meta)
        combined = cosine_sim * 0.6 + overlap * 0.4
        scored.append((combined, hit_id, meta, url_field))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_id, best_meta, field = scored[0]

    if best_score < MIN_MATCH_SCORE:
        return None

    return MatchedResult(id=best_id, url=best_meta.get(field))


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
    results = milvus_client.search_images(tenant_id, embedding, limit=10)
    blocked = exclude_ids or set()
    query_tokens = _tokenize(query_text)

    if results and len(results) > 0 and len(results[0]) > 0:
        return _pick_best(results[0], query_tokens, "image_url", blocked)
    return None


def match_clip(
    tenant_id: str,
    query_text: str,
    exclude_ids: Optional[Set[str]] = None,
) -> Optional[MatchedResult]:
    """
    Find the best matching cinematic clip from Milvus by semantic similarity.
    Skips any clip IDs in exclude_ids to ensure activity-level diversity.
    """
    embedding = generate_embedding(query_text)
    results = milvus_client.search_clips(tenant_id, embedding, limit=10)
    blocked = exclude_ids or set()
    query_tokens = _tokenize(query_text)

    if results and len(results) > 0 and len(results[0]) > 0:
        return _pick_best(results[0], query_tokens, "video_url", blocked)
    return None
