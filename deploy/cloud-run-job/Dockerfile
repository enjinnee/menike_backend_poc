FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /work

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create package structure
RUN mkdir -p app/services app/models

# Copy only the modules the worker needs
COPY worker.py .

# These files are copied from the repo root at build time
# (see setup-cloud-run-job.sh for the build context)
COPY app/__init__.py          app/__init__.py
COPY app/services/__init__.py app/services/__init__.py
COPY app/models/__init__.py   app/models/__init__.py
COPY app/services/media_processor.py app/services/media_processor.py
COPY app/services/storage.py         app/services/storage.py
COPY app/models/sql_models.py        app/models/sql_models.py

ENTRYPOINT ["python", "worker.py"]
