"""
Royalty-Free Media Downloader (Multi-Source + LLM Relevance Scoring)
======================================================================
Searches multiple royalty-free video sources in parallel, uses an LLM
to score each candidate for relevance to the activity, then downloads
the best match and dual-writes to GCS + Postgres + Milvus.

Sources searched (in priority order):
  1. Pixabay  — primary, best coverage for niche travel (e.g. Sigiriya)
  2. Pexels   — secondary, large royalty-free library
  3. Internet Archive — tertiary, travel documentaries / CC content

Environment variables:
    PIXABAY_API_KEY  — free key from https://pixabay.com/api/
    PEXELS_API_KEY   — free key from https://www.pexels.com/api/

Usage:
    from app.services.royalty_free_downloader import royalty_free_downloader

    clip = royalty_free_downloader.download_and_store(
        query="sigiriya rock ancient",
        activity_name="Visit Sigiriya Rock Fortress",
        location="Sigiriya, Sri Lanka",
        keywords="sigiriya,rock,fortress,ancient",
        description="Climb the iconic Sigiriya rock fortress",
        tenant_id="tenant_xyz",
        session=db_session,
        target_duration=10.0,
    )
    if clip:
        print(clip.video_url)  # GCS URL
"""

import json
import logging
import os
import re
import shutil
import uuid
from typing import Optional

import requests
from sqlmodel import Session, select

from app.core.milvus_client import milvus_client
from app.models.sql_models import CinematicClip
from app.providers.factory import ProviderFactory
from app.services.embedding import generate_embedding
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"
PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
ARCHIVE_SEARCH_URL = "https://archive.org/advancedsearch.php"

# LLM relevance score threshold: candidates below this are discarded
LLM_SCORE_THRESHOLD = 6

# Keywords too generic for a video search query
_STOP_WORDS = {
    "arrive", "arrival", "depart", "departure", "check", "transfer",
    "via", "from", "to", "and", "the", "a", "an", "at", "in", "on",
    "return", "back", "fly", "travel", "journey", "trip",
}

_LLM_SCORING_PROMPT = """You are a travel video curator. Score each video's relevance to this activity on a scale of 0-10.

Activity: {activity_name}
Location: {location}
Description: {description}
Keywords: {keywords}

Videos (JSON list):
{candidates_json}

Return ONLY valid JSON — a list of objects with "id" and "score" fields.
Example: [{{"id": 0, "score": 8}}, {{"id": 1, "score": 3}}]

Scoring guide:
- 9-10: Exact location match (e.g. "Sigiriya Rock Fortress Sri Lanka")
- 7-8: Same landmark type at different location (e.g. "ancient rock fortress")
- 5-6: Related visual concept (e.g. "jungle ruins")
- 1-4: Loosely related (e.g. "tropical landscape")
- 0: Unrelated

Return scores for ALL {n_candidates} videos. No extra text outside the JSON array."""


class RoyaltyFreeDownloader:
    """
    Finds, downloads, and stores the best royalty-free video clip for a
    travel activity by searching Pixabay, Pexels, and Internet Archive,
    then scoring all candidates with an LLM for content relevance.

    Clips are stored with source='pixabay'|'pexels'|'archive' and are
    re-used by subsequent itinerary generations via Milvus semantic search,
    so the library self-populates over time.
    """

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def download_and_store(
        self,
        query: str,
        activity_name: str,
        location: str,
        keywords: str,
        tenant_id: str,
        session: Session,
        target_duration: float = 10.0,
        description: str = "",
    ) -> Optional[CinematicClip]:
        """
        Full pipeline:
          1. Check if an equivalent clip already exists for this tenant
          2. Search Pixabay + Pexels + Internet Archive
          3. LLM-score all candidates for relevance to the activity
          4. Pick best candidate with score >= LLM_SCORE_THRESHOLD
          5. Download to /tmp
          6. Upload to GCS
          7. Dual-write: Postgres CinematicClip + Milvus clip_vectors
          8. Return CinematicClip or None on any failure / no match
        """
        # 1. Search all sources
        all_candidates: list[dict] = []
        for search_fn in (self._search_pixabay, self._search_pexels, self._search_archive):
            try:
                results = search_fn(query)
                all_candidates.extend(results)
                logger.info(
                    "%s returned %d result(s) for query: %s",
                    search_fn.__name__, len(results), query,
                )
            except Exception as exc:
                logger.warning("%s failed for query '%s': %s", search_fn.__name__, query, exc)

        if not all_candidates:
            logger.info("No candidates from any source for query: %s", query)
            return None

        # 2. LLM relevance scoring
        try:
            scored = self._score_candidates_with_llm(
                all_candidates, activity_name, location, description, keywords
            )
        except Exception as exc:
            logger.warning("LLM scoring failed (%s) — using heuristic fallback", exc)
            scored = self._score_candidates_heuristic(all_candidates)

        logger.info(
            "LLM scores for '%s': %s",
            activity_name,
            [(c["source"], c["source_id"], c.get("llm_score", "?")) for c in scored],
        )

        # 3. Pick best above threshold
        best = max(scored, key=lambda c: c.get("llm_score", 0))
        if best.get("llm_score", 0) < LLM_SCORE_THRESHOLD:
            logger.info(
                "Best score=%d below threshold=%d for: %s — skipping download",
                best.get("llm_score", 0), LLM_SCORE_THRESHOLD, activity_name,
            )
            return None

        logger.info(
            "Selected %s clip '%s' (score=%d, duration=%.1fs) for: %s",
            best["source"], best.get("title", "?")[:60],
            best.get("llm_score", 0), best["duration"], activity_name,
        )

        # 4. Deduplication: check if this exact clip is already stored
        gcs_key = f"tenants/{tenant_id}/clips/{best['source']}_{best['source_id']}.mp4"
        existing = session.exec(
            select(CinematicClip)
            .where(CinematicClip.tenant_id == tenant_id)
            .where(CinematicClip.video_url.contains(f"{best['source']}_{best['source_id']}"))
        ).first()
        if existing:
            logger.info("Reusing existing %s clip %s", best["source"], best["source_id"])
            return existing

        # 5. Resolve download URL (Internet Archive needs a metadata lookup)
        download_url = best.get("download_url")
        if not download_url:
            logger.warning("No download URL for candidate: %s", best)
            return None

        # 6. Download to /tmp
        try:
            local_path = self.download_to_tmp(download_url)
        except Exception as exc:
            logger.error("Download failed for %s %s: %s", best["source"], best["source_id"], exc)
            return None

        # 7. Store (GCS → Postgres → Milvus)
        try:
            return self._store_clip(
                local_path, best, gcs_key, activity_name, location, keywords, tenant_id, session
            )
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    def build_search_query(
        self, activity_name: str, location: str, keywords: str
    ) -> str:
        """
        Build a simplified, visually-searchable query from activity metadata.
        Top 3 filtered keywords, falling back to location words if needed.
        """
        kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        filtered = [k for k in kw_list if k not in _STOP_WORDS][:3]

        if len(filtered) < 2 and location:
            loc_words = [
                w.lower()
                for w in location.replace(",", " ").split()
                if w.lower() not in _STOP_WORDS
            ][:2]
            filtered = (filtered + loc_words)[:3]

        if not filtered:
            filtered = activity_name.split()[:3]

        return " ".join(filtered)

    # Backward-compat wrappers (used by cinematic_video_builder.py)
    def search_pexels(self, query: str, per_page: int = 5) -> list:
        return self._search_pexels_raw(query, per_page)

    def select_best_video(
        self, videos: list, target_duration: float = 10.0
    ) -> Optional[dict]:
        """Legacy method kept for backward compatibility."""
        candidates = []
        for video in videos:
            duration = video.get("duration", 0)
            if duration < 3:
                continue
            files = video.get("video_files", [])
            hd_files = [f for f in files if f.get("quality") == "hd"]
            sd_files = [f for f in files if f.get("quality") == "sd"]
            chosen = (hd_files or sd_files or [None])[0]
            if not chosen:
                continue
            width = chosen.get("width", 0)
            height = chosen.get("height", 0)
            score = (
                (1.0 if 5 <= duration <= 30 else 0.5)
                + (0.3 if height > width else 0.0)
                + (0.2 if hd_files else 0.0)
            )
            candidates.append({
                "score": score,
                "pexels_id": video["id"],
                "download_url": chosen["link"],
                "duration": duration,
                "width": width,
                "height": height,
            })
        if not candidates:
            return None
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        return {k: v for k, v in best.items() if k != "score"}

    # ------------------------------------------------------------------ #
    #  Search methods — return normalized candidate dicts                  #
    # ------------------------------------------------------------------ #

    def _search_pixabay(self, query: str, per_page: int = 5) -> list[dict]:
        """Search Pixabay Videos API and return normalized candidates."""
        if not PIXABAY_API_KEY:
            logger.debug("PIXABAY_API_KEY not set — skipping Pixabay")
            return []
        params = {
            "key": PIXABAY_API_KEY,
            "q": query,
            "per_page": per_page,
            "video_type": "film",
        }
        resp = requests.get(PIXABAY_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        candidates = []
        for hit in hits:
            # Pixabay provides multiple sizes; prefer "large" then "medium"
            videos = hit.get("videos", {})
            file_info = videos.get("large") or videos.get("medium") or videos.get("small")
            if not file_info or not file_info.get("url"):
                continue
            candidates.append({
                "source": "pixabay",
                "source_id": str(hit["id"]),
                "title": f"Pixabay #{hit['id']}",  # Pixabay doesn't expose titles in API
                "description": "",
                "tags": hit.get("tags", ""),
                "duration": hit.get("duration", 0),
                "download_url": file_info["url"],
                "width": file_info.get("width", 0),
                "height": file_info.get("height", 0),
                "llm_score": 0,
            })
        return candidates

    def _search_pexels(self, query: str, per_page: int = 5) -> list[dict]:
        """Search Pexels Videos API and return normalized candidates."""
        if not PEXELS_API_KEY:
            logger.debug("PEXELS_API_KEY not set — skipping Pexels")
            return []
        raw = self._search_pexels_raw(query, per_page)
        candidates = []
        for video in raw:
            files = video.get("video_files", [])
            hd = [f for f in files if f.get("quality") == "hd"]
            sd = [f for f in files if f.get("quality") == "sd"]
            chosen = (hd or sd or [None])[0]
            if not chosen or not chosen.get("link"):
                continue
            candidates.append({
                "source": "pexels",
                "source_id": str(video["id"]),
                "title": video.get("url", ""),   # Pexels API doesn't expose title; use page URL
                "description": "",
                "tags": "",
                "duration": video.get("duration", 0),
                "download_url": chosen["link"],
                "width": chosen.get("width", 0),
                "height": chosen.get("height", 0),
                "llm_score": 0,
            })
        return candidates

    def _search_pexels_raw(self, query: str, per_page: int = 5) -> list:
        """Raw Pexels API call returning the native response format."""
        if not PEXELS_API_KEY:
            return []
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": query, "per_page": per_page, "orientation": "portrait"}
        resp = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("videos", [])

    def _search_archive(self, query: str, rows: int = 5) -> list[dict]:
        """
        Search Internet Archive for CC-licensed or public-domain travel videos.
        Only includes items that have a downloadable .mp4 file.
        """
        params = {
            "q": f"{query} mediatype:movies",
            "fl[]": ["identifier", "title", "description", "subject", "licenseurl"],
            "rows": rows,
            "output": "json",
            "sort[]": "downloads desc",
        }
        try:
            resp = requests.get(ARCHIVE_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()
            docs = resp.json().get("response", {}).get("docs", [])
        except Exception as exc:
            logger.debug("Internet Archive search failed: %s", exc)
            return []

        candidates = []
        for doc in docs:
            identifier = doc.get("identifier", "")
            if not identifier:
                continue

            # License check — only CC or public domain (empty licenseurl = PD on Archive)
            license_url = doc.get("licenseurl", "")
            if license_url and "creativecommons" not in license_url:
                continue

            # Resolve a direct MP4 download URL
            download_url = self._get_archive_download_url(identifier)
            if not download_url:
                continue

            title = doc.get("title", identifier)
            description = doc.get("description", "")
            if isinstance(description, list):
                description = " ".join(description)
            subjects = doc.get("subject", [])
            if isinstance(subjects, str):
                subjects = [subjects]
            tags = ", ".join(subjects)

            candidates.append({
                "source": "archive",
                "source_id": identifier,
                "title": title,
                "description": description[:300],
                "tags": tags,
                "duration": 0,   # Archive metadata rarely includes duration; LLM scores on title/desc
                "download_url": download_url,
                "width": 0,
                "height": 0,
                "llm_score": 0,
            })
        return candidates

    def _get_archive_download_url(self, identifier: str) -> Optional[str]:
        """
        Look up the item's file list and return the URL of the largest .mp4 file.
        Falls back to a predictable URL pattern if the metadata call fails.
        """
        try:
            meta_url = f"https://archive.org/metadata/{identifier}/files"
            resp = requests.get(meta_url, timeout=10)
            resp.raise_for_status()
            files = resp.json().get("result", [])
            mp4_files = [
                f for f in files
                if f.get("name", "").lower().endswith(".mp4")
                and not f.get("name", "").startswith(".")
            ]
            if not mp4_files:
                return None
            # Pick the largest MP4
            mp4_files.sort(key=lambda f: int(f.get("size", 0)), reverse=True)
            filename = mp4_files[0]["name"]
            return f"https://archive.org/download/{identifier}/{filename}"
        except Exception:
            # Fallback: common naming convention
            return f"https://archive.org/download/{identifier}/{identifier}.mp4"

    # ------------------------------------------------------------------ #
    #  LLM relevance scoring                                               #
    # ------------------------------------------------------------------ #

    def _score_candidates_with_llm(
        self,
        candidates: list[dict],
        activity_name: str,
        location: str,
        description: str,
        keywords: str,
    ) -> list[dict]:
        """
        Ask the configured LLM to score each candidate 0–10 for relevance
        to the activity. Returns candidates with 'llm_score' field populated.
        """
        # Build the list the LLM sees (no download_url — just metadata)
        llm_input = [
            {
                "id": i,
                "source": c["source"],
                "title": c["title"],
                "description": c["description"][:200] if c["description"] else "",
                "tags": c["tags"][:200] if c["tags"] else "",
            }
            for i, c in enumerate(candidates)
        ]
        prompt = _LLM_SCORING_PROMPT.format(
            activity_name=activity_name,
            location=location,
            description=description[:300] if description else "",
            keywords=keywords,
            candidates_json=json.dumps(llm_input, indent=2),
            n_candidates=len(candidates),
        )

        try:
            provider = ProviderFactory.create()
            raw = provider.generate_content(prompt)
        except Exception as exc:
            raise RuntimeError(f"LLM provider call failed: {exc}") from exc

        # Parse JSON response — try direct parse then regex extraction
        scores_by_id: dict[int, int] = {}
        try:
            parsed = json.loads(raw)
            for item in parsed:
                scores_by_id[int(item["id"])] = int(item["score"])
        except (json.JSONDecodeError, KeyError, TypeError):
            # Regex fallback: extract {"id": N, "score": M} patterns
            for match in re.finditer(r'"id"\s*:\s*(\d+).*?"score"\s*:\s*(\d+)', raw, re.DOTALL):
                scores_by_id[int(match.group(1))] = int(match.group(2))

        # Apply scores back to candidates
        result = []
        for i, c in enumerate(candidates):
            c_copy = dict(c)
            c_copy["llm_score"] = scores_by_id.get(i, 0)
            result.append(c_copy)
        return result

    def _score_candidates_heuristic(self, candidates: list[dict]) -> list[dict]:
        """
        Fallback scoring when LLM is unavailable.
        Uses duration range, portrait orientation, and source priority.
        """
        source_bonus = {"pixabay": 2, "pexels": 1, "archive": 0}
        result = []
        for c in candidates:
            duration = c["duration"]
            dur_score = 4 if 5 <= duration <= 30 else (2 if duration > 0 else 0)
            orient_score = 2 if c["height"] > c["width"] > 0 else 0
            src_score = source_bonus.get(c["source"], 0)
            c_copy = dict(c)
            c_copy["llm_score"] = min(dur_score + orient_score + src_score, 10)
            result.append(c_copy)
        return result

    # ------------------------------------------------------------------ #
    #  Download + dual-write                                               #
    # ------------------------------------------------------------------ #

    def download_to_tmp(self, url: str) -> str:
        """Stream-download a video file to /tmp and return the local path."""
        local_path = f"/tmp/rfv_{uuid.uuid4().hex}.mp4"
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                shutil.copyfileobj(resp.raw, f)
        logger.info("Downloaded clip to %s", local_path)
        return local_path

    def _store_clip(
        self,
        local_path: str,
        candidate: dict,
        gcs_key: str,
        activity_name: str,
        location: str,
        keywords: str,
        tenant_id: str,
        session: Session,
    ) -> Optional[CinematicClip]:
        """Upload to GCS and dual-write Postgres + Milvus."""
        # GCS upload
        try:
            video_url = storage_service.upload_file(local_path, gcs_key)
        except Exception as exc:
            logger.error("GCS upload failed for %s: %s", gcs_key, exc)
            return None

        source = candidate["source"]
        source_id = candidate["source_id"]

        # Postgres
        clip = CinematicClip(
            tenant_id=tenant_id,
            name=f"{activity_name} ({source.capitalize()} #{source_id})",
            tags=keywords.lower(),
            video_url=video_url,
            duration=candidate["duration"],
            description=(
                f"Auto-downloaded from {source} "
                f"(score={candidate.get('llm_score', '?')}): {candidate.get('title', '')}"
            ),
            location=location,
            type="royalty_free",
            source=source,
        )
        session.add(clip)
        session.commit()
        session.refresh(clip)

        # Milvus
        try:
            embedding_text = f"{activity_name} {keywords} {location}"
            embedding = generate_embedding(embedding_text)
            metadata = {
                "name": clip.name,
                "tags": clip.tags,
                "video_url": video_url,
                "duration": clip.duration,
                "location": location,
                "type": "royalty_free",
                "pg_id": clip.id,
                "source": source,
            }
            milvus_client.insert_clip_vector(clip.id, tenant_id, embedding, metadata)
        except Exception as exc:
            logger.error("Milvus insert failed for %s clip %s: %s", source, clip.id, exc)

        logger.info(
            "Stored %s clip '%s' (%.1fs, score=%s) for tenant %s → %s",
            source, clip.name, clip.duration,
            candidate.get("llm_score", "?"), tenant_id, video_url,
        )
        return clip


# Module-level singleton
royalty_free_downloader = RoyaltyFreeDownloader()
