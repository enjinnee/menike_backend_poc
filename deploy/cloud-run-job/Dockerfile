FROM python:3.11-slim

# Install system deps:
#   ffmpeg       — video normalise + concat (both legacy and cinematic modes)
#   libgeos-dev  — required by Shapely (contextily dependency for map tiles)
#   libproj-dev  — required by pyproj (great-circle route for flights)
#   libgl1       — required by matplotlib Agg backend
#   libglib2.0-0 — shared GLib runtime (matplotlib/contextily transitive dep)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libgeos-dev \
        libproj-dev \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# Install Python deps
COPY deploy/cloud-run-job/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create package structure with empty __init__.py files
RUN mkdir -p app/services app/models app/core && \
    touch app/__init__.py app/services/__init__.py app/models/__init__.py app/core/__init__.py

# Copy worker and all app modules it needs.
# Build context must be the menike_backend_poc/ repo root.
COPY deploy/cloud-run-job/worker.py              worker.py

# Core services used by both modes
COPY app/services/media_processor.py             app/services/media_processor.py
COPY app/services/storage.py                     app/services/storage.py
COPY app/models/sql_models.py                    app/models/sql_models.py

# Additional services for cinematic mode
COPY app/services/cinematic_video_builder.py     app/services/cinematic_video_builder.py
COPY app/services/map_clip_generator.py          app/services/map_clip_generator.py
COPY app/services/royalty_free_downloader.py     app/services/royalty_free_downloader.py
COPY app/services/embedding.py                   app/services/embedding.py
COPY app/core/milvus_client.py                   app/core/milvus_client.py

ENTRYPOINT ["python", "worker.py"]
