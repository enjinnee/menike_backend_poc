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
itinerary_id = os.environ.get("ITINERARY_ID")
tenant_id = os.environ.get("TENANT_ID")

if not clip_urls_raw or not itinerary_id or not tenant_id:
    print("ERROR: CLIP_URLS, ITINERARY_ID, and TENANT_ID env vars are required.")
    sys.exit(1)

clip_urls: list[str] = json.loads(clip_urls_raw)
if not clip_urls:
    print("ERROR: CLIP_URLS is empty.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Stitch clips via MediaProcessor (same logic as the API server)
# ---------------------------------------------------------------------------
# We import here so env vars (DATABASE_URL etc.) are loaded first.
from app.services.media_processor import MediaProcessor
from app.services.storage import storage_service

output_path = f"/tmp/final_video_{itinerary_id}.mp4"
media_processor = MediaProcessor()

print(f"Compiling {len(clip_urls)} clips for itinerary {itinerary_id} ...")
try:
    media_processor.stitch_scenes(clip_urls, output_path)
except Exception as e:
    print(f"ERROR during video stitching: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 3. Upload to GCS
# ---------------------------------------------------------------------------
gcs_key = f"tenants/{tenant_id}/final-video/{itinerary_id}.mp4"
print(f"Uploading to GCS: {gcs_key}")
video_url = storage_service.upload_file(output_path, gcs_key)
print(f"Upload complete: {video_url}")

# Clean up temp file
if os.path.exists(output_path):
    os.remove(output_path)

# ---------------------------------------------------------------------------
# 4. Update database: FinalVideo + Itinerary status
# ---------------------------------------------------------------------------
from sqlmodel import Session, select, create_engine
from app.models.sql_models import FinalVideo, Itinerary

database_url = os.environ["DATABASE_URL"]
engine = create_engine(database_url, echo=False)

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

print(f"Done. Itinerary {itinerary_id} marked as video_compiled.")
