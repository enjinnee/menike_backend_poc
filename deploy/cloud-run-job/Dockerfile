FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /work

# Install Python deps
COPY deploy/cloud-run-job/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create package structure with empty __init__.py files
RUN mkdir -p app/services app/models && \
    touch app/__init__.py app/services/__init__.py app/models/__init__.py

# Copy worker and only the app modules it needs.
# Build context must be the menike_backend_poc/ repo root.
COPY deploy/cloud-run-job/worker.py          worker.py
COPY app/services/media_processor.py         app/services/media_processor.py
COPY app/services/storage.py                 app/services/storage.py
COPY app/models/sql_models.py                app/models/sql_models.py

ENTRYPOINT ["python", "worker.py"]
