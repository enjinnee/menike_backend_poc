"""
Cloud Run Job worker — compiles video clips into a single final video.

Reads configuration from environment variables (set as execution overrides):
  CLIP_URLS      — JSON list of GCS clip URLs
  ITINERARY_ID   — target itinerary row
  TENANT_ID      — owning tenant

Shared env vars (set on the Job definition):
  DATABASE_URL   — PostgreSQL connection string
  GCS_BUCKET_NAME
  GCS_BASE_PREFIX

Retry behaviour:
  - Video stitching + GCS upload are idempotent: if the output object already
    exists in GCS the worker skips both steps and goes straight to the DB
    update.  This means Cloud Run retries (on DB / network failures) will never
    re-encode the video.
  - If stitching itself fails the worker exits(1) immediately; Cloud Run will
    not retry because maxRetries=0 on the job definition.
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 1. Parse execution-specific env vars
# ---------------------------------------------------------------------------
clip_urls_raw = os.environ.get("CLIP_URLS")
itinerary_id  = os.environ.get("ITINERARY_ID")
tenant_id     = os.environ.get("TENANT_ID")

if not clip_urls_raw or not itinerary_id or not tenant_id:
    print("ERROR: CLIP_URLS, ITINERARY_ID, and TENANT_ID env vars are required.")
    sys.exit(1)

clip_urls: list[str] = json.loads(clip_urls_raw)
if not clip_urls:
    print("ERROR: CLIP_URLS is empty.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Imports (after env vars are loaded)
# ---------------------------------------------------------------------------
from app.services.media_processor import MediaProcessor
from app.services.storage import storage_service
from google.cloud import storage as gcs_storage

bucket_name = os.environ["GCS_BUCKET_NAME"]
gcs_key     = f"tenants/{tenant_id}/final-video/{itinerary_id}.mp4"
output_path = f"/tmp/final_video_{itinerary_id}.mp4"

# ---------------------------------------------------------------------------
# 3. Check GCS — skip stitch+upload if the video already exists (retry-safe)
# ---------------------------------------------------------------------------
gcs_client = gcs_storage.Client()
bucket     = gcs_client.bucket(bucket_name)
blob       = bucket.blob(gcs_key)

if blob.exists():
    print(f"Video already exists in GCS at {gcs_key} — skipping stitch and upload.")
    video_url = f"https://storage.googleapis.com/{bucket_name}/{gcs_key}"
else:
    # -----------------------------------------------------------------------
    # 4. Stitch clips — exit immediately on failure (no point retrying encode)
    # -----------------------------------------------------------------------
    media_processor = MediaProcessor()
    print(f"Compiling {len(clip_urls)} clips for itinerary {itinerary_id} ...")
    try:
        media_processor.stitch_scenes(clip_urls, output_path)
    except Exception as e:
        print(f"ERROR during video stitching: {e}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 5. Upload to GCS
    # -----------------------------------------------------------------------
    print(f"Uploading to GCS: {gcs_key}")
    try:
        video_url = storage_service.upload_file(output_path, gcs_key)
    except Exception as e:
        print(f"ERROR during GCS upload: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

    print(f"Upload complete: {video_url}")

# ---------------------------------------------------------------------------
# 6. Update database: FinalVideo + Itinerary status
#    This section can be safely retried — GCS check above makes it idempotent.
# ---------------------------------------------------------------------------
from sqlmodel import Session, select, create_engine
from app.models.sql_models import FinalVideo, Itinerary

database_url = os.environ["DATABASE_URL"]
engine = create_engine(database_url, echo=False)

try:
    with Session(engine) as session:
        final_video = session.exec(
            select(FinalVideo)
            .where(FinalVideo.itinerary_id == itinerary_id)
            .where(FinalVideo.tenant_id == tenant_id)
        ).first()

        if final_video:
            final_video.video_url = video_url
            final_video.status = "compiled"
            session.add(final_video)

        itinerary = session.get(Itinerary, itinerary_id)
        if itinerary:
            itinerary.status = "video_compiled"
            session.add(itinerary)

        session.commit()
except Exception as e:
    print(f"ERROR updating database: {e}")
    sys.exit(1)

print(f"Done. Itinerary {itinerary_id} marked as video_compiled.")
