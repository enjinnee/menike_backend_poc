"""
Cloud Run Job worker — compiles a cinematic travel video.

Two modes, selected by the CINEMATIC env var:

  CINEMATIC=false  (default / legacy)
    Reads CLIP_URLS (JSON list of GCS URLs), stitches them in order,
    uploads to GCS and updates the DB.  Identical to the original behaviour.

  CINEMATIC=true
    Reads ITINERARY_ID and loads the full rich_itinerary_json from Postgres,
    then runs the full CinematicVideoBuilder pipeline:
      1. Build segment list (activities interleaved with map transitions)
      2. Pexels fallback for activities with no matched clip
      3. Generate animated map transition clips
      4. Trim + assemble all clips to target duration
      5. Upload final video to GCS
      6. Update FinalVideo + Itinerary rows in Postgres

Execution-specific env vars (set as Cloud Run override per execution):
  CLIP_URLS          JSON list of GCS clip URLs          (legacy mode only)
  ITINERARY_ID       Target itinerary row ID             (both modes)
  TENANT_ID          Owning tenant ID                    (both modes)
  CINEMATIC          "true" / "false"                    (default: false)
  TARGET_SECONDS     Target video duration in seconds    (cinematic, default 45)

Shared env vars (baked into the Job definition):
  DATABASE_URL
  GCS_BUCKET_NAME
  GCS_BASE_PREFIX
  PEXELS_API_KEY         (cinematic mode — Pexels royalty-free fallback)
  ENABLE_PEXELS_FALLBACK "true"/"false" (default: true)

Retry behaviour (both modes):
  The GCS output path is checked before any heavy work begins.
  If the final video already exists in GCS the worker skips encoding,
  goes straight to the DB update, and exits 0.  Cloud Run retries
  (on transient DB failures) are therefore safe and cheap.
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 1. Parse execution-specific env vars
# ---------------------------------------------------------------------------
itinerary_id = os.environ.get("ITINERARY_ID")
tenant_id    = os.environ.get("TENANT_ID")
cinematic    = os.environ.get("CINEMATIC", "false").lower() == "true"
target_secs  = float(os.environ.get("TARGET_SECONDS", "45.0"))

if not itinerary_id or not tenant_id:
    print("ERROR: ITINERARY_ID and TENANT_ID env vars are required.")
    sys.exit(1)

# Legacy mode also requires CLIP_URLS
clip_urls: list[str] = []
if not cinematic:
    clip_urls_raw = os.environ.get("CLIP_URLS")
    if not clip_urls_raw:
        print("ERROR: CLIP_URLS is required when CINEMATIC=false.")
        sys.exit(1)
    clip_urls = json.loads(clip_urls_raw)
    if not clip_urls:
        print("ERROR: CLIP_URLS is empty.")
        sys.exit(1)

print(f"[worker] mode={'cinematic' if cinematic else 'legacy'} "
      f"itinerary={itinerary_id} tenant={tenant_id}")

# ---------------------------------------------------------------------------
# 2. GCS idempotency check — skip heavy work if output already exists
# ---------------------------------------------------------------------------
from google.cloud import storage as gcs_storage

bucket_name = os.environ["GCS_BUCKET_NAME"]

if cinematic:
    gcs_key = f"tenants/{tenant_id}/final-video/{itinerary_id}_cinematic.mp4"
else:
    gcs_key = f"tenants/{tenant_id}/final-video/{itinerary_id}.mp4"

gcs_client = gcs_storage.Client()
bucket     = gcs_client.bucket(bucket_name)
blob       = bucket.blob(gcs_key)

if blob.exists():
    print(f"[worker] Output already exists in GCS at {gcs_key} — skipping encode.")
    video_url = f"https://storage.googleapis.com/{bucket_name}/{gcs_key}"
else:
    # -----------------------------------------------------------------------
    # 3a. CINEMATIC MODE — full pipeline via CinematicVideoBuilder
    # -----------------------------------------------------------------------
    if cinematic:
        from sqlmodel import Session, select, create_engine
        from app.models.sql_models import Itinerary, ItineraryActivity
        from app.services.cinematic_video_builder import CinematicVideoBuilder

        database_url = os.environ["DATABASE_URL"]
        engine = create_engine(database_url, echo=False)

        print(f"[worker] Loading itinerary {itinerary_id} from Postgres...")
        try:
            with Session(engine) as session:
                itinerary_row = session.get(Itinerary, itinerary_id)
                if not itinerary_row:
                    print(f"ERROR: Itinerary {itinerary_id} not found in DB.")
                    sys.exit(1)
                if not itinerary_row.rich_itinerary_json:
                    print("ERROR: Itinerary has no rich_itinerary_json "
                          "(was it generated via the AI flow?).")
                    sys.exit(1)

                rich_itinerary = json.loads(itinerary_row.rich_itinerary_json)

                activities = session.exec(
                    select(ItineraryActivity)
                    .where(ItineraryActivity.itinerary_id == itinerary_id)
                    .where(ItineraryActivity.tenant_id == tenant_id)
                    .order_by(ItineraryActivity.order_index)
                ).all()

                print(f"[worker] Running CinematicVideoBuilder "
                      f"({len(activities)} activities, target={target_secs}s)...")
                builder = CinematicVideoBuilder()
                try:
                    result = builder.build(
                        itinerary_id=itinerary_id,
                        tenant_id=tenant_id,
                        rich_itinerary=rich_itinerary,
                        activities=list(activities),
                        session=session,
                        target_total_seconds=target_secs,
                    )
                except Exception as e:
                    print(f"ERROR during cinematic build: {e}")
                    sys.exit(1)

                video_url = result.video_url
                print(f"[worker] Cinematic build complete: {video_url} "
                      f"({result.total_duration:.1f}s, {result.clips_used} clips, "
                      f"{result.map_transitions_generated} maps, "
                      f"{result.pexels_downloads} Pexels downloads)")

        except SystemExit:
            raise
        except Exception as e:
            print(f"ERROR during cinematic DB session: {e}")
            sys.exit(1)

    # -----------------------------------------------------------------------
    # 3b. LEGACY MODE — stitch existing clip URLs
    # -----------------------------------------------------------------------
    else:
        from app.services.media_processor import MediaProcessor
        from app.services.storage import storage_service

        output_path = f"/tmp/final_video_{itinerary_id}.mp4"
        media_processor = MediaProcessor()

        print(f"[worker] Stitching {len(clip_urls)} clips for itinerary {itinerary_id}...")
        try:
            media_processor.stitch_scenes(clip_urls, output_path)
        except Exception as e:
            print(f"ERROR during video stitching: {e}")
            sys.exit(1)

        print(f"[worker] Uploading to GCS: {gcs_key}")
        try:
            video_url = storage_service.upload_file(output_path, gcs_key)
        except Exception as e:
            print(f"ERROR during GCS upload: {e}")
            sys.exit(1)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)

        print(f"[worker] Upload complete: {video_url}")

# ---------------------------------------------------------------------------
# 4. Update database: FinalVideo + Itinerary status
#    Safe to retry — GCS check above makes the full worker idempotent.
# ---------------------------------------------------------------------------
from sqlmodel import Session, select, create_engine as _create_engine
from app.models.sql_models import FinalVideo, Itinerary

_db_url = os.environ["DATABASE_URL"]
_engine = _create_engine(_db_url, echo=False)

print(f"[worker] Updating DB for itinerary {itinerary_id}...")
try:
    with Session(_engine) as session:
        final_video = session.exec(
            select(FinalVideo)
            .where(FinalVideo.itinerary_id == itinerary_id)
            .where(FinalVideo.tenant_id == tenant_id)
        ).first()

        if final_video:
            final_video.video_url = video_url
            final_video.status = "compiled"
            session.add(final_video)
        else:
            # Worker triggered without a pre-created FinalVideo row —
            # create one so the API's video-status endpoint can return it.
            print("[worker] No FinalVideo row found — creating one.")
            fv = FinalVideo(
                tenant_id=tenant_id,
                itinerary_id=itinerary_id,
                video_url=video_url,
                status="compiled",
            )
            session.add(fv)

        itin = session.get(Itinerary, itinerary_id)
        if itin:
            itin.status = "video_compiled"
            session.add(itin)

        session.commit()
except Exception as e:
    print(f"ERROR updating database: {e}")
    sys.exit(1)

print(f"[worker] Done. Itinerary {itinerary_id} video_compiled. URL: {video_url}")
