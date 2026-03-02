"""
Matcher service: finds the best matching image and cinematic clip
for each itinerary activity using Milvus semantic search + LLM relevance scoring.

Match quality uses a two-stage approach:
  1. Milvus vector search retrieves the top-N candidates by cosine similarity.
  2. An LLM scores each candidate for relevance to the activity (0-10),
     allowing precise geographic disambiguation (e.g. Galle Fort vs Jaffna Fort).
     On LLM failure, falls back to pure cosine-similarity ranking.
"""
import json
import logging
import re
from typing import Optional, Set

from app.core.milvus_client import milvus_client
from app.models.sql_models import ImageLibrary, CinematicClip
from app.providers.factory import ProviderFactory
from app.services.embedding import generate_embedding

logger = logging.getLogger(__name__)

# Candidates with a cosine similarity below this threshold are rejected in the
# fallback path (LLM path uses its own score threshold below).
MIN_MATCH_SCORE = float(0.10)

# LLM relevance thresholds — candidates scoring below these are not selected.
LLM_MIN_IMAGE_SCORE = 5
LLM_MIN_CLIP_SCORE  = 5

_IMAGE_SCORING_PROMPT = """You are a travel photo curator matching library images to itinerary activities.

Activity context: {activity_context}

Candidate images (JSON):
{candidates_json}

Score each image's visual relevance to the activity on a scale of 0-10.
Return ONLY valid JSON — a list of objects with "id" and "score" fields.
Example: [{{"id": 0, "score": 8}}, {{"id": 1, "score": 3}}]

Scoring guide:
- 9-10: Exact location match (same landmark, same place name)
- 7-8: Same landmark type at a different but related location
- 5-6: Related visual category (e.g. heritage building, coastal view)
- 1-4: Loosely related visual concept
- 0: Unrelated

Return scores for ALL {n_candidates} images. No text outside the JSON array."""

_CLIP_SCORING_PROMPT = """You are a travel video curator matching library clips to itinerary activities.

Activity context: {activity_context}

Candidate clips (JSON):
{candidates_json}

Score each clip's visual relevance to the activity on a scale of 0-10.
Return ONLY valid JSON — a list of objects with "id" and "score" fields.
Example: [{{"id": 0, "score": 8}}, {{"id": 1, "score": 3}}]

Scoring guide:
- 9-10: Exact location match (same landmark or place shown)
- 7-8: Same landmark type at a different but related location
- 5-6: Related visual category (e.g. coastal, heritage, adventure)
- 1-4: Loosely related visual concept
- 0: Unrelated

Return scores for ALL {n_candidates} clips. No text outside the JSON array."""


class MatchedResult:
    def __init__(self, id: str, url: str):
        self.id = id
        self.url = url


def _score_with_llm(
    hits,
    query_text: str,
    url_field: str,
    blocked: Set[str],
    prompt_template: str,
    min_score: int,
) -> Optional[MatchedResult]:
    """
    Ask the LLM to score each Milvus hit for relevance to the activity.

    Returns the best MatchedResult with llm_score >= min_score, or None if no
    candidate meets the threshold or if the candidate list is empty.
    Raises on LLM / parse failure so callers can fall back to cosine ranking.
    """
    # 1. Filter blocked hits
    candidates = []
    for hit in hits:
        hit_id = str(hit.id)
        if hit_id in blocked:
            continue
        meta = hit.entity.get("metadata", {})
        candidates.append({
            "hit_id": hit_id,
            "distance": max(0.0, hit.distance),
            "meta": meta,
        })

    if not candidates:
        return None

    # 2. Build LLM input (metadata only — no internal IDs, no raw URLs)
    is_clip = (url_field == "video_url")
    llm_input = []
    for i, c in enumerate(candidates):
        meta = c["meta"]
        entry = {
            "id": i,
            "name": meta.get("name", ""),
            "tags": meta.get("tags", ""),
            "location": meta.get("location", ""),
            "description": (meta.get("description", "") or "")[:200],
            "type": meta.get("type", ""),
        }
        if is_clip:
            entry["duration"] = meta.get("duration", 0)
        llm_input.append(entry)

    # 3. Format prompt and call LLM
    prompt = prompt_template.format(
        activity_context=query_text,
        candidates_json=json.dumps(llm_input, indent=2),
        n_candidates=len(candidates),
    )
    provider = ProviderFactory.create()
    raw = provider.generate_content(prompt)

    # 4. Parse JSON response — try direct parse then regex fallback
    scores_by_id: dict[int, int] = {}
    try:
        parsed = json.loads(raw)
        for item in parsed:
            scores_by_id[int(item["id"])] = int(item["score"])
    except (json.JSONDecodeError, KeyError, TypeError):
        for m in re.finditer(r'"id"\s*:\s*(\d+).*?"score"\s*:\s*(\d+)', raw, re.DOTALL):
            scores_by_id[int(m.group(1))] = int(m.group(2))

    if not scores_by_id:
        raise ValueError("LLM returned no parseable scores")

    # 5. Sort by LLM score descending, return best above threshold
    scored = [
        (scores_by_id.get(i, 0), c["hit_id"], c["meta"])
        for i, c in enumerate(candidates)
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_id, best_meta = scored[0]

    logger.info(
        "LLM %s scores for '%s...': top=%d (id=%s)",
        url_field, query_text[:60], best_score, best_id,
    )

    if best_score < min_score:
        return None

    return MatchedResult(id=best_id, url=best_meta.get(url_field))


def _cosine_pick_best(hits, url_field: str, blocked: Set[str]) -> Optional[MatchedResult]:
    """
    Fallback selector: picks the highest cosine-similarity non-blocked candidate
    above MIN_MATCH_SCORE. Used when LLM scoring fails or is unavailable.
    """
    scored = []
    for hit in hits:
        hit_id = str(hit.id)
        if hit_id in blocked:
            continue
        meta = hit.entity.get("metadata", {})
        cosine_sim = max(0.0, hit.distance)
        scored.append((cosine_sim, hit_id, meta))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_id, best_meta = scored[0]

    if best_score < MIN_MATCH_SCORE:
        return None

    return MatchedResult(id=best_id, url=best_meta.get(url_field))


def match_image(
    tenant_id: str,
    query_text: str,
    exclude_ids: Optional[Set[str]] = None,
) -> Optional[MatchedResult]:
    """
    Find the best matching image from Milvus by semantic similarity + LLM scoring.
    query_text: "Visit Galle Fort, heritage, sunset"
    """
    embedding = generate_embedding(query_text)
    results = milvus_client.search_images(tenant_id, embedding, limit=10)
    blocked = exclude_ids or set()

    if not (results and len(results) > 0 and len(results[0]) > 0):
        return None

    hits = results[0]

    try:
        result = _score_with_llm(
            hits, query_text, "image_url", blocked,
            _IMAGE_SCORING_PROMPT, LLM_MIN_IMAGE_SCORE,
        )
        if result is not None:
            return result
        # LLM scored but nothing met the threshold — fall through to cosine
    except Exception as exc:
        logger.warning("LLM image scoring failed (%s) — falling back to cosine ranking", exc)

    return _cosine_pick_best(hits, "image_url", blocked)


def match_clip(
    tenant_id: str,
    query_text: str,
    exclude_ids: Optional[Set[str]] = None,
) -> Optional[MatchedResult]:
    """
    Find the best matching cinematic clip from Milvus by semantic similarity + LLM scoring.
    Skips any clip IDs in exclude_ids to ensure activity-level diversity.
    """
    embedding = generate_embedding(query_text)
    results = milvus_client.search_clips(tenant_id, embedding, limit=10)
    blocked = exclude_ids or set()

    if not (results and len(results) > 0 and len(results[0]) > 0):
        return None

    hits = results[0]

    try:
        result = _score_with_llm(
            hits, query_text, "video_url", blocked,
            _CLIP_SCORING_PROMPT, LLM_MIN_CLIP_SCORE,
        )
        if result is not None:
            return result
        # LLM scored but nothing met the threshold — fall through to cosine
    except Exception as exc:
        logger.warning("LLM clip scoring failed (%s) — falling back to cosine ranking", exc)

    return _cosine_pick_best(hits, "video_url", blocked)
