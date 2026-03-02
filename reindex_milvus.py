"""
Milvus re-indexing migration script.

Run this after deploying the Gemini text-embedding-004 embedding change.
It drops the old 128-dim image_vectors and clip_vectors collections,
recreates them with the new 768-dim schema, then re-embeds every record
from PostgreSQL and inserts it into Milvus.

Usage:
    cd menike_backend_poc
    python3 reindex_milvus.py

Prerequisites:
    - .env must be present with GEMINI_API_KEY and DATABASE_URL
    - Milvus must be reachable (tunnel open if remote)
"""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# Bootstrap the app paths before importing app modules
sys.path.insert(0, os.path.dirname(__file__))

from pymilvus import connections, utility, Collection

from app.core.database import get_session
from app.models.sql_models import ImageLibrary, CinematicClip
from app.models.milvus_schema import get_image_vector_schema, get_clip_vector_schema
from app.services.embedding import generate_embedding
from app.core.milvus_client import milvus_client, MILVUS_HOST, MILVUS_PORT, IMAGE_COLLECTION_NAME, CLIP_COLLECTION_NAME
from sqlmodel import select


BATCH_SLEEP = 0.3  # seconds between Gemini API calls to avoid rate limiting


def drop_and_recreate(collection_name: str, schema_fn):
    print(f"\n[{collection_name}] Dropping old collection...")
    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        print(f"[{collection_name}] Dropped.")
    else:
        print(f"[{collection_name}] Did not exist, skipping drop.")

    print(f"[{collection_name}] Recreating with 768-dim schema...")
    milvus_client.create_collection(collection_name, schema_fn())
    print(f"[{collection_name}] Created.")


def reindex_images(session):
    images = session.exec(select(ImageLibrary)).all()
    print(f"\n[image_vectors] Re-embedding {len(images)} images...")
    ok = 0
    failed = 0
    for img in images:
        try:
            text = " ".join(filter(None, [
                img.name,
                img.tags,
                img.location,
                img.type,
                img.description,
            ]))
            embedding = generate_embedding(text)
            metadata = {
                "name": img.name or "",
                "tags": img.tags or "",
                "location": img.location or "",
                "image_url": img.image_url or "",
                "description": (img.description or "")[:500],
                "type": img.type or "",
                "pg_id": img.id,
            }
            milvus_client.insert_image_vector(img.id, img.tenant_id, embedding, metadata)
            ok += 1
            print(f"  [{ok}/{len(images)}] OK: {img.name[:60]}")
            time.sleep(BATCH_SLEEP)
        except Exception as e:
            failed += 1
            print(f"  FAILED: {img.name[:60]} — {e}")

    print(f"\n[image_vectors] Done: {ok} inserted, {failed} failed.")


def reindex_clips(session):
    from sqlalchemy import text as sa_text
    # Use raw SQL to avoid ORM issues when the cinematic_clip table has columns
    # added after the initial schema (e.g. the 'source' column added later).
    rows = session.execute(sa_text(
        "SELECT id, tenant_id, name, tags, video_url, duration, description, location, type "
        "FROM cinematic_clip"
    )).all()

    clips = [
        type("Clip", (), {
            "id": r[0], "tenant_id": r[1], "name": r[2], "tags": r[3],
            "video_url": r[4], "duration": r[5], "description": r[6],
            "location": r[7], "type": r[8],
        })()
        for r in rows
    ]
    print(f"\n[clip_vectors] Re-embedding {len(clips)} clips...")
    ok = 0
    failed = 0
    for clip in clips:
        try:
            text = " ".join(filter(None, [
                clip.name,
                clip.tags,
                clip.location,
                clip.type,
                clip.description,
            ]))
            embedding = generate_embedding(text)
            metadata = {
                "name": clip.name or "",
                "tags": clip.tags or "",
                "location": clip.location or "",
                "video_url": clip.video_url or "",
                "description": (clip.description or "")[:500],
                "type": clip.type or "",
                "duration": clip.duration or 0,
                "pg_id": clip.id,
            }
            milvus_client.insert_clip_vector(clip.id, clip.tenant_id, embedding, metadata)
            ok += 1
            print(f"  [{ok}/{len(clips)}] OK: {clip.name[:60]}")
            time.sleep(BATCH_SLEEP)
        except Exception as e:
            failed += 1
            print(f"  FAILED: {clip.name[:60]} — {e}")

    print(f"\n[clip_vectors] Done: {ok} inserted, {failed} failed.")


def main():
    print("=== Milvus Re-indexing: 128-dim → 768-dim (Gemini text-embedding-004) ===")
    print(f"Milvus: {MILVUS_HOST}:{MILVUS_PORT}")

    # Drop and recreate collections with 768-dim schema
    drop_and_recreate(IMAGE_COLLECTION_NAME, get_image_vector_schema)
    drop_and_recreate(CLIP_COLLECTION_NAME, get_clip_vector_schema)

    # Re-embed all records from PostgreSQL
    with next(get_session()) as session:
        reindex_images(session)
        reindex_clips(session)

    print("\n=== Re-indexing complete. ===")
    print("You can now regenerate itineraries and the new 768-dim embeddings will be used.")


if __name__ == "__main__":
    main()
