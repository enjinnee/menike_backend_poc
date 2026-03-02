"""
Cinematic Video Builder
========================
Orchestrates the full cinematic video generation pipeline for an itinerary:

  1. Build ordered segment list — activities interleaved with map transitions
     extracted from the itinerary's rides[] data.
  2. Fill missing activity clips via Pexels (royalty_free_downloader).
  3. Calculate clip pacing so the total hits the target duration (default 45 s).
  4. Generate animated map transition clips (map_clip_generator), cached in the
     MapTransition table to avoid redundant re-renders.
  5. Download, trim, and normalise all clips then concatenate with FFmpeg.
  6. Upload the final video to GCS and return the result.

Usage (called from app/api/itinerary.py):

    from app.services.cinematic_video_builder import cinematic_builder

    result = cinematic_builder.build(
        itinerary_id=itinerary.id,
        tenant_id=tenant_id,
        rich_itinerary=json.loads(itinerary.rich_itinerary_json),
        activities=db_activities,   # list[ItineraryActivity]
        session=session,
    )
    # result.video_url  → GCS public URL of the final cinematic video
"""

import logging
import os
import shutil
import ssl
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

import certifi
from google.cloud import storage as gcs_storage
from sqlmodel import Session, select

from app.models.sql_models import CinematicClip, FinalVideo, ItineraryActivity, MapTransition
from app.services.map_clip_generator import map_clip_generator
from app.services.royalty_free_downloader import royalty_free_downloader
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

_DEFAULT_TARGET_SECONDS = float(os.getenv("CINEMATIC_TARGET_DURATION", "45.0"))
_ENABLE_PEXELS = os.getenv("ENABLE_PEXELS_FALLBACK", "true").lower() == "true"

# Portrait output resolution for all clips
_OUTPUT_WIDTH = 720
_OUTPUT_HEIGHT = 1280


@dataclass
class ClipSegment:
    """One segment in the final video timeline."""
    segment_type: str           # "activity" | "map_transition"
    label: str
    order_index: int
    clip_url: Optional[str] = None          # GCS/HTTP URL; None until resolved
    target_duration: Optional[float] = None  # seconds to trim to

    # Internal references (not serialised)
    _activity_data: Optional[dict] = field(default=None, repr=False)
    _db_activity: Optional[object] = field(default=None, repr=False)
    _ride_data: Optional[dict] = field(default=None, repr=False)


@dataclass
class CinematicBuildResult:
    video_url: str
    total_duration: float
    clips_used: int
    map_transitions_generated: int
    pexels_downloads: int


class CinematicVideoBuilder:
    """
    Orchestrates cinematic video assembly from a rich itinerary JSON.
    """

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def build(
        self,
        itinerary_id: str,
        tenant_id: str,
        rich_itinerary: dict,
        activities: List[ItineraryActivity],
        session: Session,
        target_total_seconds: float = _DEFAULT_TARGET_SECONDS,
    ) -> CinematicBuildResult:
        """
        Run all 5 pipeline phases and return a CinematicBuildResult.
        The final video is uploaded to GCS before this method returns.
        """
        logger.info(
            "Starting cinematic build for itinerary %s (target %.0fs)",
            itinerary_id, target_total_seconds
        )

        # Phase 1 — Build segment list
        segments = self._build_segment_list(rich_itinerary, activities)
        logger.info("Segment list: %d segments (%d activities, %d map transitions)",
                    len(segments),
                    sum(1 for s in segments if s.segment_type == "activity"),
                    sum(1 for s in segments if s.segment_type == "map_transition"))

        # Phase 2 — Pexels fallback for missing activity clips
        pexels_count = 0
        if _ENABLE_PEXELS:
            pexels_count = self._fill_missing_clips(segments, tenant_id, session)

        # Phase 3 — Calculate pacing
        self._calculate_pacing(segments, target_total_seconds)

        # Phase 4 — Generate map transition clips
        map_count = self._generate_map_clips(segments, itinerary_id, tenant_id, session)

        # Phase 5 — Trim, assemble, upload
        # Remove segments that still have no clip URL
        valid_segments = [s for s in segments if s.clip_url]
        if not valid_segments:
            raise RuntimeError(
                "Cinematic build failed: no usable clips found after all fallbacks. "
                "Upload clips or set PEXELS_API_KEY."
            )

        clip_plan = [(s.clip_url, s.target_duration) for s in valid_segments]
        output_path = f"/tmp/cinematic_{itinerary_id}_{uuid.uuid4().hex[:6]}.mp4"
        total_duration = self._trim_and_assemble(clip_plan, output_path)

        gcs_key = f"tenants/{tenant_id}/final-video/{itinerary_id}_cinematic.mp4"
        final_url = storage_service.upload_file(output_path, gcs_key)
        if os.path.exists(output_path):
            os.remove(output_path)

        logger.info(
            "Cinematic build complete: %s (%.1fs, %d clips, %d maps, %d Pexels)",
            final_url, total_duration, len(valid_segments), map_count, pexels_count
        )
        return CinematicBuildResult(
            video_url=final_url,
            total_duration=total_duration,
            clips_used=len(valid_segments),
            map_transitions_generated=map_count,
            pexels_downloads=pexels_count,
        )

    # ------------------------------------------------------------------ #
    #  Phase 1 — Build segment list                                        #
    # ------------------------------------------------------------------ #

    def _build_segment_list(
        self,
        rich_itinerary: dict,
        db_activities: List[ItineraryActivity],
    ) -> List[ClipSegment]:
        """
        Produce an ordered list of ClipSegments that interleaves:
          [activity] → [map_transition after its ride] → [next activity] → ...

        Activities come from rich_itinerary["days"][*]["activities"].
        Rides (map transitions) come from rich_itinerary["days"][*]["rides"].

        We match rides to activities positionally: the i-th ride in a day
        provides the transition after the i-th activity.
        """
        # Build a lookup: rich-itinerary activity id → ItineraryActivity DB obj
        db_act_by_order = {act.order_index: act for act in db_activities}
        # We iterate activities in their declaration order and track a global index
        global_act_idx = 0
        segments: List[ClipSegment] = []
        order = 0

        for day_data in rich_itinerary.get("days", []):
            day_activities = day_data.get("activities", [])
            day_rides = day_data.get("rides", [])

            for i, act_data in enumerate(day_activities):
                # Find matching DB activity by order (generated sequentially)
                db_act = db_act_by_order.get(global_act_idx)
                global_act_idx += 1

                seg = ClipSegment(
                    segment_type="activity",
                    label=f"Day {day_data.get('day', '?')}: {act_data.get('title', act_data.get('activity_name', 'Activity'))}",
                    order_index=order,
                    clip_url=db_act.cinematic_clip_url if db_act else None,
                    _activity_data=act_data,
                    _db_activity=db_act,
                )
                segments.append(seg)
                order += 1

                # Attach the corresponding ride as a map transition after this activity
                if i < len(day_rides):
                    ride = day_rides[i]
                    if self._ride_has_valid_coords(ride):
                        map_seg = ClipSegment(
                            segment_type="map_transition",
                            label=f"{ride.get('from_location', '?')} → {ride.get('to_location', '?')}",
                            order_index=order,
                            _ride_data=ride,
                        )
                        segments.append(map_seg)
                        order += 1

        return segments

    # ------------------------------------------------------------------ #
    #  Phase 2 — Pexels fallback                                           #
    # ------------------------------------------------------------------ #

    def _fill_missing_clips(
        self,
        segments: List[ClipSegment],
        tenant_id: str,
        session: Session,
    ) -> int:
        """
        For each activity segment with no clip_url, attempt a royalty-free download
        (Pixabay → Pexels → Internet Archive, scored by LLM).
        Returns the number of successful downloads.
        """
        downloaded = 0
        for seg in segments:
            if seg.segment_type != "activity" or seg.clip_url:
                continue

            act = seg._activity_data or {}
            db_act = seg._db_activity

            activity_name = act.get("title") or act.get("activity_name") or seg.label
            location = act.get("location") or (db_act.location if db_act else "") or ""
            keywords = act.get("keywords") or (db_act.keywords if db_act else "") or ""
            description = act.get("description") or ""

            query = royalty_free_downloader.build_search_query(
                activity_name, location, keywords
            )

            logger.info("Searching royalty-free sources for: '%s' (query: '%s')", seg.label, query)

            try:
                clip = royalty_free_downloader.download_and_store(
                    query=query,
                    activity_name=activity_name,
                    location=location,
                    keywords=keywords,
                    description=description,
                    tenant_id=tenant_id,
                    session=session,
                    target_duration=10.0,
                )
            except Exception as exc:
                logger.error("Royalty-free download failed for '%s': %s", seg.label, exc)
                clip = None

            if clip:
                seg.clip_url = clip.video_url
                # Update the DB activity record so future itineraries reuse this clip
                if db_act:
                    db_act.cinematic_clip_id = clip.id
                    db_act.cinematic_clip_url = clip.video_url
                    session.add(db_act)
                downloaded += 1
            else:
                logger.warning("No clip found for segment: %s", seg.label)

        if downloaded:
            session.commit()

        return downloaded

    # ------------------------------------------------------------------ #
    #  Phase 3 — Calculate pacing                                          #
    # ------------------------------------------------------------------ #

    def _calculate_pacing(
        self,
        segments: List[ClipSegment],
        target_total_seconds: float,
        map_duration: float = 2.5,
        min_activity_duration: float = 3.0,
        max_activity_duration: float = 5.0,
    ) -> None:
        """
        Assign target_duration to every segment so the final video hits the
        target_total_seconds.

        Map transitions always get map_duration seconds.
        The remaining budget is divided equally among activity segments,
        clamped to [min_activity_duration, max_activity_duration].
        """
        n_maps = sum(1 for s in segments if s.segment_type == "map_transition")
        n_activities = sum(1 for s in segments if s.segment_type == "activity" and s.clip_url)

        map_total = n_maps * map_duration
        activity_budget = max(0.0, target_total_seconds - map_total)

        if n_activities > 0:
            per_activity = activity_budget / n_activities
            per_activity = max(min_activity_duration, min(per_activity, max_activity_duration))
        else:
            per_activity = min_activity_duration

        for seg in segments:
            if seg.segment_type == "map_transition":
                seg.target_duration = map_duration
            elif seg.segment_type == "activity" and seg.clip_url:
                seg.target_duration = per_activity

        logger.info(
            "Pacing: %d activities × %.1fs + %d maps × %.1fs = %.1fs total",
            n_activities, per_activity, n_maps, map_duration,
            n_activities * per_activity + map_total
        )

    # ------------------------------------------------------------------ #
    #  Phase 4 — Generate map transition clips                             #
    # ------------------------------------------------------------------ #

    def _generate_map_clips(
        self,
        segments: List[ClipSegment],
        itinerary_id: str,
        tenant_id: str,
        session: Session,
    ) -> int:
        """
        For each map_transition segment, either retrieve from the MapTransition
        cache or generate a new animated clip.
        Returns the number of newly generated (non-cached) clips.
        """
        generated = 0

        for idx, seg in enumerate(segments):
            if seg.segment_type != "map_transition":
                continue

            ride = seg._ride_data
            if not ride:
                continue

            from_lat = ride["from_coordinates"]["latitude"]
            from_lon = ride["from_coordinates"]["longitude"]
            to_lat = ride["to_coordinates"]["latitude"]
            to_lon = ride["to_coordinates"]["longitude"]
            transport_type = ride.get("transportation_type", "car")
            from_label = ride.get("from_location", "")
            to_label = ride.get("to_location", "")

            cache_key = map_clip_generator.make_cache_key(from_lat, from_lon, to_lat, to_lon)

            # Check MapTransition cache
            cached = session.exec(
                select(MapTransition)
                .where(MapTransition.cache_key == cache_key)
                .where(MapTransition.tenant_id == tenant_id)
            ).first()

            if cached:
                seg.clip_url = cached.video_url
                logger.info("Reusing cached map clip for %s → %s", from_label, to_label)
                continue

            # Generate new map clip
            duration = seg.target_duration or 2.5
            try:
                result = map_clip_generator.generate_and_upload(
                    from_lat=from_lat,
                    from_lon=from_lon,
                    to_lat=to_lat,
                    to_lon=to_lon,
                    from_label=from_label,
                    to_label=to_label,
                    itinerary_id=itinerary_id,
                    tenant_id=tenant_id,
                    transition_idx=idx,
                    transport_type=transport_type,
                    duration_seconds=duration,
                )
                seg.clip_url = result.gcs_url

                # Cache in MapTransition table
                mt = MapTransition(
                    tenant_id=tenant_id,
                    cache_key=cache_key,
                    from_location=from_label,
                    to_location=to_label,
                    transport_type=transport_type,
                    video_url=result.gcs_url,
                    duration=duration,
                )
                session.add(mt)
                session.commit()
                generated += 1

            except Exception as exc:
                logger.error(
                    "Map clip generation failed for %s → %s: %s",
                    from_label, to_label, exc
                )
                # Leave clip_url as None — this segment is skipped in assembly

        return generated

    # ------------------------------------------------------------------ #
    #  Phase 5 — Trim and assemble                                         #
    # ------------------------------------------------------------------ #

    def _trim_and_assemble(
        self,
        clip_plan: List[tuple],     # [(url, target_duration_seconds), ...]
        output_path: str,
    ) -> float:
        """
        For each clip:
          1. Download from GCS/HTTPS to /tmp.
          2. Trim to target_duration + normalise to 720×1280 portrait H.264/30fps.
          3. Concat all trimmed+normalised clips into output_path.

        Returns the approximate total duration in seconds.
        """
        tmp_files: List[str] = []
        trimmed_paths: List[str] = []
        total_duration = 0.0

        try:
            for clip_url, target_duration in clip_plan:
                local = self._ensure_local(clip_url)
                tmp_files.append(local)

                trimmed = os.path.join(
                    tempfile.gettempdir(),
                    f"trimmed_{os.getpid()}_{uuid.uuid4().hex[:6]}.mp4"
                )
                actual_dur = target_duration or 4.0

                try:
                    self._trim_normalise(local, trimmed, actual_dur)
                    trimmed_paths.append(trimmed)
                    total_duration += actual_dur
                except subprocess.CalledProcessError as exc:
                    logger.error(
                        "FFmpeg trim/normalise failed for %s: %s",
                        clip_url, exc.stderr.decode() if exc.stderr else exc
                    )
                    # Skip this clip

            if not trimmed_paths:
                raise RuntimeError("No clips could be processed by FFmpeg.")

            self._ffmpeg_concat(trimmed_paths, output_path)

        finally:
            for p in tmp_files + trimmed_paths:
                if os.path.exists(p):
                    os.remove(p)

        return total_duration

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ensure_local(url: str) -> str:
        """Download a remote clip URL to /tmp and return the local path."""
        if not (url.startswith("http://") or url.startswith("https://")):
            return url  # already local

        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1] or ".mp4"
        local_path = os.path.join(tempfile.gettempdir(), f"dl_{uuid.uuid4().hex}{ext}")

        host = parsed.netloc.lower()
        if host == "storage.googleapis.com":
            parts = parsed.path.lstrip("/").split("/", 1)
            bucket_name = parts[0]
            key = parts[1] if len(parts) > 1 else ""
            client = gcs_storage.Client()
            blob = client.bucket(bucket_name).blob(key)
            blob.download_to_filename(local_path)
        else:
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            with urlopen(url, context=ssl_ctx) as src, open(local_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

        return local_path

    @staticmethod
    def _trim_normalise(input_path: str, output_path: str, duration: float) -> None:
        """
        Trim a clip to *duration* seconds and normalise to a stable portrait baseline:
          - Resolution: 720×1280 (portrait); letterboxed/pillarboxed if needed
          - Codec:      H.264 libx264 (veryfast preset, CRF 23)
          - Framerate:  30 fps
          - Audio:      AAC 192k stereo 48 kHz
        """
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-t", str(duration),
            # Video: scale to portrait, pad to fill canvas
            "-vf", (
                f"scale={_OUTPUT_WIDTH}:{_OUTPUT_HEIGHT}"
                ":force_original_aspect_ratio=decrease,"
                f"pad={_OUTPUT_WIDTH}:{_OUTPUT_HEIGHT}:"
                "(ow-iw)/2:(oh-ih)/2:color=black"
            ),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            # Audio
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-movflags", "+faststart",
            "-y",
            output_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @staticmethod
    def _ffmpeg_concat(input_paths: List[str], output_path: str) -> None:
        """Concatenate already-normalised clips using the concat demuxer."""
        list_file = f"/tmp/concat_{os.getpid()}_{uuid.uuid4().hex[:6]}.txt"
        try:
            with open(list_file, "w") as f:
                for p in input_paths:
                    safe = p.replace("'", "'\\''")
                    f.write(f"file '{safe}'\n")

            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c", "copy",
                "-y",
                output_path,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            if os.path.exists(list_file):
                os.remove(list_file)

    @staticmethod
    def _ride_has_valid_coords(ride: dict) -> bool:
        """Return True if the ride dict has non-zero from/to coordinates."""
        try:
            fc = ride.get("from_coordinates", {})
            tc = ride.get("to_coordinates", {})
            return (
                fc.get("latitude") and fc.get("longitude") and
                tc.get("latitude") and tc.get("longitude") and
                (fc["latitude"] != tc["latitude"] or fc["longitude"] != tc["longitude"])
            )
        except (TypeError, KeyError):
            return False


# Module-level singleton
cinematic_builder = CinematicVideoBuilder()
