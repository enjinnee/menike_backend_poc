"""
migrate_to_public_urls.py

Rewrites all signed GCS URLs stored in PostgreSQL and Milvus to plain public URLs.

Signed URLs contain query params like ?X-Goog-Signature=... or X-Goog-Algorithm=...
Public URL format: https://storage.googleapis.com/{bucket}/{key}

Usage:
    python3 migrate_to_public_urls.py
    python3 migrate_to_public_urls.py --dry-run
"""

import argparse
import json
import os
import re
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import text
from sqlmodel import Session

load_dotenv()

# ── helpers ──────────────────────────────────────────────────────────────────

def strip_signed_params(url: str) -> str:
    """Strip GCS signed URL query params, returning the bare public URL."""
    if not url:
        return url
    parsed = urlparse(url)
    # Only touch storage.googleapis.com URLs that have signing query params
    if parsed.netloc != "storage.googleapis.com":
        return url
    if not any(p in parsed.query for p in ("X-Goog-Signature", "X-Goog-Algorithm")):
        return url
    return urlunparse(parsed._replace(query="", fragment=""))


def clean(url: str | None) -> tuple[str | None, bool]:
    """Return (cleaned_url, changed)."""
    if not url:
        return url, False
    cleaned = strip_signed_params(url)
    return cleaned, cleaned != url


# ── PostgreSQL migration ──────────────────────────────────────────────────────

def migrate_postgres(dry_run: bool):
    from app.core.database import engine

    url_columns = [
        ("image_library",       "image_url"),
        ("cinematic_clip",      "video_url"),
        ("itinerary_activity",  "image_url"),
        ("itinerary_activity",  "cinematic_clip_url"),
        ("final_video",         "video_url"),
        ("scene",               "media_url"),
    ]

    total = 0
    with Session(engine) as session:
        for table, column in url_columns:
            rows = session.exec(
                text(f'SELECT id, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')
            ).fetchall()

            updates = []
            for row_id, url in rows:
                new_url, changed = clean(url)
                if changed:
                    updates.append((row_id, new_url))

            if updates:
                print(f"  {table}.{column}: {len(updates)} row(s) to update")
                if not dry_run:
                    for row_id, new_url in updates:
                        session.exec(
                            text(f'UPDATE "{table}" SET "{column}" = :url WHERE id = :id'),
                            params={"url": new_url, "id": row_id},
                        )
                    session.commit()
                    print(f"    -> committed")
            else:
                print(f"  {table}.{column}: no signed URLs found")

            total += len(updates)

    print(f"\nPostgreSQL: {total} URL(s) {'would be' if dry_run else ''} updated.")


# ── Milvus migration ──────────────────────────────────────────────────────────

def migrate_milvus(dry_run: bool):
    from pymilvus import connections, Collection, utility

    milvus_host = os.getenv("MILVUS_HOST", "localhost")
    milvus_port = os.getenv("MILVUS_PORT", "19530")
    connections.connect(host=milvus_host, port=milvus_port)

    # collection name -> metadata field that holds the URL
    collections_map = {
        "image_vectors": "image_url",
        "clip_vectors":  "video_url",
    }

    total = 0
    for coll_name, url_field in collections_map.items():
        if not utility.has_collection(coll_name):
            print(f"  Milvus collection '{coll_name}' not found, skipping.")
            continue

        coll = Collection(coll_name)
        coll.load()

        results = coll.query(
            expr="id != ''",
            output_fields=["id", "metadata"],
        )

        updates = []
        for entity in results:
            meta = entity.get("metadata")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    continue

            old_url = meta.get(url_field, "")
            new_url, changed = clean(old_url)
            if changed:
                meta[url_field] = new_url
                updates.append({"id": entity["id"], "metadata": meta})

        if updates:
            print(f"  Milvus {coll_name}.metadata.{url_field}: {len(updates)} entity(ies) to update")
            if not dry_run:
                # Milvus doesn't support partial field updates — upsert the full entity.
                # First fetch all fields so we don't lose embeddings.
                full_results = coll.query(
                    expr=f'id in [{", ".join(repr(u["id"]) for u in updates)}]',
                    output_fields=["id", "tenant_id", "embedding", "metadata"],
                )
                full_map = {r["id"]: r for r in full_results}
                upsert_data = []
                for upd in updates:
                    row = full_map.get(upd["id"])
                    if row:
                        row["metadata"] = upd["metadata"]
                        upsert_data.append(row)

                if upsert_data:
                    coll.upsert(upsert_data)
                    coll.flush()
                    print(f"    -> upserted {len(upsert_data)} entities")
        else:
            print(f"  Milvus {coll_name}.metadata.{url_field}: no signed URLs found")

        total += len(updates)

    print(f"\nMilvus: {total} entity(ies) {'would be' if dry_run else ''} updated.")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()

    if args.dry_run:
        print("==> DRY RUN — no changes will be written\n")

    print("==> Migrating PostgreSQL...")
    migrate_postgres(dry_run=args.dry_run)

    print("\n==> Migrating Milvus...")
    migrate_milvus(dry_run=args.dry_run)

    print("\nDone.")
