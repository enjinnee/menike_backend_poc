# Manike B2B AI Engine POC

A high-performance, multi-tenant AI engine for cinematic itinerary and scene orchestration.

## Architecture Overview

The engine follows a layered B2B architecture designed for scalability, security, and AI resource management.

### 1. API Layer (FastAPI)
- **Modular Routing**: Organized into `auth`, `chat`, `scenes`, `itinerary`, `images`, `cinematic_clips`, `experiences`, `tenants`, `admin`, and `pages` domains.
- **Tenant-Aware**: Every request is authenticated via JWT and scoped to a specific `tenant_id`.

### 2. Core Infrastructure
- **Authentication**: JWT-based OAuth2 flow with `pbkdf2_sha256` password hashing. `SECRET_KEY` configurable via environment variable.
- **Database (SQLModel)**: High-level ORM managing `Tenant`, `User`, `Scene`, `ImageLibrary`, `CinematicClip`, `Itinerary`, `ItineraryActivity`, and `FinalVideo` entities (PostgreSQL).
- **AI Providers**: Pluggable provider abstraction supporting Gemini and Claude, selectable via `AI_PROVIDER` env var.

### 3. Scene Orchestrator Service
The heartbeat of the system. It coordinates:
- **LLM Prompt Engine**: Transforms user descriptions into optimized AI prompts.
- **Generators**: Mocked AI services for Image and Video generation (VEO-3 ready).
- **Media Processor**: FFmpeg wrapper for video optimization, normalization, and concatenation.
- **Storage Service**: GCS-backed persistence for generated media assets.

### 4. Chat Pipeline
- **ChatManager** orchestrates a **ConversationFlow** state machine that collects travel requirements (destination, dates, budget, travelers, preferences, accommodations).
- **FieldExtractor** uses AI + regex to parse user messages; **ResponseGenerator** creates contextual replies.

### 5. Persistence Layer
- **SQL Data**: PostgreSQL for relational metadata (tenants, users, itineraries, media records).
- **Vector DB (Milvus)**: 4 collections — `experiences` (4-dim), `tenants` (metadata), `image_vectors` (128-dim), `clip_vectors` (128-dim) — all COSINE + HNSW indexed for semantic search.
- **Blob Storage**: Google Cloud Storage for binary media hosting.

### 6. Core Workflow
Chat session → extract travel requirements → AI generates itinerary JSON → match images/clips via Milvus semantic search → compile video from matched clips (FFmpeg) → upload to GCS.

## Getting Started

### Prerequisites
- Python 3.10+
- FFmpeg (for media processing)
- PostgreSQL
- Milvus (optional, backend will skip if unavailable)

### Installation
```bash
pip install -r requirements.txt
```

### Environment Variables
```bash
cp deploy/.env.gcp.example .env
# Edit .env with your values
```

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus server address (default: `localhost:19530`) |
| `GCS_BUCKET_NAME` | Google Cloud Storage bucket name |
| `GCS_BASE_PREFIX` | Key prefix for uploaded media (default: `experience-images`) |
| `SECRET_KEY` | JWT signing secret |
| `AI_PROVIDER` | `gemini` or `claude` |
| `GEMINI_API_KEY` | Google Gemini API key (if using Gemini) |
| `CLAUDE_API_KEY` | Anthropic Claude API key (if using Claude) |
| `VIDEO_COMPILER` | `local` (default) or `cloudrun` |
| `CLOUD_RUN_JOB_NAME` | Full Cloud Run Job name (when `VIDEO_COMPILER=cloudrun`) |
| `CLOUD_RUN_REGION` | Cloud Run region (default: `us-central1`) |

### Seeding the DB
```bash
python3 seed_db.py
```
This creates the default tenant, a tenant admin (`admin@manike.ai` / `admin123`), and a super admin (`superadmin@manike.ai` / `superadmin123`).

### Running the Engine
```bash
python3 app/main.py
```

Access the Swagger UI at `http://localhost:8000/docs`

## Chat UI

The backend serves a built-in chat interface for AI-powered travel planning.

### Accessing the Chat UI

1. Open `http://<HOST>:8000/auth/login` in your browser
2. Log in with `admin@manike.ai` / `admin123`
3. You'll be redirected to the chat UI at `http://<HOST>:8000/`

**On the current GCP deployment:** http://34.171.132.91:8000/auth/login

The chat UI supports:
- Natural language conversation to collect travel preferences
- AI-powered itinerary generation
- Image and cinematic clip matching per activity
- Video compilation of matched clips
- Voice input mode with HeyGen avatar integration

### Chat API Flow

```bash
# 1. Login to get a token
TOKEN=$(curl -s http://localhost:8000/auth/login \
  -d "username=admin@manike.ai&password=admin123" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Start a new chat session
curl -s http://localhost:8000/api/session/new \
  -H "Authorization: Bearer $TOKEN"

# 3. Send messages (returns AI response + requirement tracking)
curl -s http://localhost:8000/api/chat/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "SESSION_ID", "message": "I want to visit Galle for 3 days"}'

# 4. Generate itinerary (after all requirements collected)
curl -s http://localhost:8000/itinerary/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "SESSION_ID"}'
```

## Inserting Data into PostgreSQL and Milvus

When you upload images or cinematic clips, the backend performs a **dual-write**: it saves metadata to PostgreSQL and generates a 128-dim embedding that gets inserted into Milvus for semantic search. This happens automatically via the upload API endpoints.

### Authentication

All data endpoints require a JWT token:

```bash
TOKEN=$(curl -s http://localhost:8000/auth/login \
  -d "username=admin@manike.ai&password=admin123" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Upload Images

**Upload a file directly** (saves to GCS, writes to PostgreSQL + Milvus):
```bash
curl -X POST http://localhost:8000/images/upload-file \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=Galle Fort Lighthouse" \
  -F "tags=galle,fort,sunset,heritage,lighthouse" \
  -F "location=Galle, Sri Lanka" \
  -F "file=@/path/to/galle-fort.jpg"
```

**Register an image by URL** (if already hosted on GCS or elsewhere):
```bash
curl -X POST http://localhost:8000/images/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Galle Fort Lighthouse",
    "tags": "galle,fort,sunset,heritage",
    "location": "Galle, Sri Lanka",
    "image_url": "https://storage.googleapis.com/manike-ai-media/experience-images/galle-fort.jpg"
  }'
```

### Upload Cinematic Clips

**Upload a video file** (saves to GCS, writes to PostgreSQL + Milvus):
```bash
curl -X POST http://localhost:8000/cinematic-clips/upload-file \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=Galle Fort Aerial Drone" \
  -F "tags=galle,fort,drone,aerial,heritage" \
  -F "duration=15.5" \
  -F "description=Drone footage of Galle Fort from above" \
  -F "file=@/path/to/galle-drone.mp4"
```

**Register a clip by URL**:
```bash
curl -X POST http://localhost:8000/cinematic-clips/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Galle Fort Aerial Drone",
    "tags": "galle,fort,drone,aerial",
    "video_url": "https://storage.googleapis.com/manike-ai-media/experience-images/galle-drone.mp4",
    "duration": 15.5,
    "description": "Drone footage of Galle Fort"
  }'
```

### Semantic Search

Once data is in Milvus, you can search semantically:

```bash
# Search images by natural language
curl -X POST http://localhost:8000/images/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "beautiful ancient fortress at sunset", "limit": 5}'

# Search cinematic clips
curl -X POST http://localhost:8000/cinematic-clips/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "aerial drone shot of historic fort", "limit": 5}'
```

### How the Dual-Write Works

When you upload an image or clip:
1. **GCS**: File is uploaded to the configured bucket
2. **PostgreSQL**: Metadata row is inserted (`ImageLibrary` or `CinematicClip` table)
3. **Milvus**: A 128-dim TF-IDF embedding is generated from `name + tags + location/description` and inserted into the `image_vectors` or `clip_vectors` collection

The embedding uses travel-domain semantic groups (beach, mountain, temple, heritage, nature, etc.) for the first dimensions, plus character-level hash features for the remainder. Search uses COSINE similarity with HNSW indexing.

### Batch Upload Example

```bash
# Upload multiple images from a directory
for img in /path/to/images/*.jpg; do
  name=$(basename "$img" .jpg | tr '-_' ' ')
  curl -X POST http://localhost:8000/images/upload-file \
    -H "Authorization: Bearer $TOKEN" \
    -F "name=$name" \
    -F "tags=sri-lanka,travel" \
    -F "file=@$img"
done
```

## GCP Deployment

The `deploy/` directory contains everything needed to provision the backend on GCP.

### Infrastructure

| Resource | Type | Details |
|----------|------|---------|
| `manike-postgres` | GCE e2-micro | PostgreSQL 15 in Docker, internal only |
| `manike-milvus` | GCE e2-small | Milvus + etcd + MinIO in Docker, internal only |
| `manike-app` | GCE e2-micro | FastAPI app via systemd, public ephemeral IP |
| `manike-ai-media` | GCS bucket | Media storage |
| `manike-video-compiler` | Cloud Run Job | Async video compilation (2 vCPU, 4GB RAM) |
| `manike-router/manike-nat` | Cloud NAT | Internet access for internal VMs |

### Deploy files

| File | Purpose |
|------|---------|
| `deploy/deploy-gcp.sh` | One-command provisioning script |
| `deploy/setup-cloud-run-job.sh` | Cloud Run Job setup for async video compilation |
| `deploy/cloud-run-job/` | Dockerfile, worker.py, requirements for the video worker |
| `deploy/docker-compose-postgres.yml` | PostgreSQL container config |
| `deploy/docker-compose-milvus.yml` | Milvus stack config |
| `deploy/manike-api.service` | Systemd unit for the FastAPI service |
| `deploy/.env.gcp.example` | Environment variable template |

### Initial Deployment

**Option A: Public repo (git clone on VM)**
```bash
./deploy/deploy-gcp.sh \
    --project YOUR_GCP_PROJECT_ID \
    --gemini-key YOUR_GEMINI_API_KEY \
    --repo-url https://github.com/YOUR_ORG/menike_backend_poc.git \
    --repo-branch main
```

**Option B: Private repo (SCP upload)**
```bash
./deploy/deploy-gcp.sh \
    --project YOUR_GCP_PROJECT_ID \
    --gemini-key YOUR_GEMINI_API_KEY \
    --deploy-method scp
```

Then upload the code manually:
```bash
# Create tarball
tar czf /tmp/menike_backend_poc.tar.gz \
    --exclude='.venv' --exclude='.git' --exclude='.env' \
    menike_backend_poc

# Upload to VM
gcloud compute scp /tmp/menike_backend_poc.tar.gz manike-app:/tmp/ --zone=us-central1-a

# Extract, install deps, seed DB, start service
gcloud compute ssh manike-app --zone=us-central1-a --command='
  sudo bash -c "
    tar xzf /tmp/menike_backend_poc.tar.gz -C /home/manike/
    chown -R manike:manike /home/manike/menike_backend_poc
    cd /home/manike/menike_backend_poc
    sudo -u manike python3 -m venv .venv
    sudo -u manike .venv/bin/pip install --upgrade pip
    sudo -u manike .venv/bin/pip install -r requirements.txt
    sudo -u manike .venv/bin/python3 seed_db.py
    cp deploy/manike-api.service /etc/systemd/system/
    systemctl daemon-reload && systemctl enable manike-api && systemctl start manike-api
  "
'
```

The script will:
1. Set up Cloud NAT (so internal VMs can download Docker images)
2. Create firewall rules (port 8000 public, 5432/19530 internal only)
3. Provision all 3 VMs with Docker CE and startup scripts
4. Create a GCS bucket for media storage
5. Configure the app with internal IPs and start the service

**deploy-gcp.sh flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--project` | (required) | GCP project ID |
| `--gemini-key` | (empty) | Gemini API key |
| `--secret-key` | (random) | JWT signing secret |
| `--postgres-password` | `manike_secret` | PostgreSQL password |
| `--zone` | `us-central1-a` | GCE zone |
| `--bucket` | `manike-ai-media` | GCS bucket name |
| `--repo-url` | — | Git repo URL (for git mode) |
| `--repo-branch` | `main` | Git branch |
| `--deploy-method` | `git` | `git` or `scp` |

### Setting Up the Cloud Run Video Compiler

After the initial deployment, set up async video compilation:

```bash
# Create Artifact Registry repo (one-time)
gcloud artifacts repositories create manike \
    --repository-format=docker --location=us-central1

# Get the PostgreSQL internal IP
PG_IP=$(gcloud compute instances describe manike-postgres \
    --zone=us-central1-a --format='get(networkInterfaces[0].networkIP)')

# Build and deploy the Cloud Run Job
export PROJECT_ID=YOUR_GCP_PROJECT_ID
export DATABASE_URL="postgresql://manike:manike_secret@${PG_IP}:5432/manike_db"
export GCS_BUCKET_NAME=manike-ai-media

./deploy/setup-cloud-run-job.sh

# Update the app server .env
gcloud compute ssh manike-app --zone=us-central1-a --command='
  sudo -u manike bash -c "cat >> /home/manike/menike_backend_poc/.env <<EOF
VIDEO_COMPILER=cloudrun
CLOUD_RUN_JOB_NAME=projects/YOUR_PROJECT_ID/locations/us-central1/jobs/manike-video-compiler
CLOUD_RUN_REGION=us-central1
EOF"
  sudo systemctl restart manike-api
'
```

### Redeploying After Code Changes

After making changes to the backend code locally, redeploy to GCP:

```bash
# 1. Create a fresh tarball (excluding venv, git, env)
tar czf /tmp/menike_backend_poc.tar.gz \
    --exclude='.venv' --exclude='.git' --exclude='.env' --exclude='__pycache__' \
    menike_backend_poc

# 2. Upload to the app VM
gcloud compute scp /tmp/menike_backend_poc.tar.gz manike-app:/tmp/ --zone=us-central1-a

# 3. Extract and restart (preserves existing .env)
gcloud compute ssh manike-app --zone=us-central1-a --command='
  sudo bash -c "
    # Backup .env
    cp /home/manike/menike_backend_poc/.env /tmp/manike-env-backup

    # Extract new code
    tar xzf /tmp/menike_backend_poc.tar.gz -C /home/manike/
    chown -R manike:manike /home/manike/menike_backend_poc

    # Restore .env
    cp /tmp/manike-env-backup /home/manike/menike_backend_poc/.env
    chown manike:manike /home/manike/menike_backend_poc/.env
    chmod 600 /home/manike/menike_backend_poc/.env

    # Reinstall deps (in case requirements.txt changed)
    cd /home/manike/menike_backend_poc
    sudo -u manike .venv/bin/pip install -r requirements.txt 2>&1 | tail -3

    # Restart the service
    systemctl restart manike-api
    sleep 2
    systemctl status manike-api --no-pager | head -8
  "
'
```

**If you only changed Python code** (no new dependencies):
```bash
# Quick redeploy: upload and restart (skip pip install)
gcloud compute scp /tmp/menike_backend_poc.tar.gz manike-app:/tmp/ --zone=us-central1-a

gcloud compute ssh manike-app --zone=us-central1-a --command='
  sudo bash -c "
    cp /home/manike/menike_backend_poc/.env /tmp/manike-env-backup
    tar xzf /tmp/menike_backend_poc.tar.gz -C /home/manike/
    chown -R manike:manike /home/manike/menike_backend_poc
    cp /tmp/manike-env-backup /home/manike/menike_backend_poc/.env
    chown manike:manike /home/manike/menike_backend_poc/.env
    chmod 600 /home/manike/menike_backend_poc/.env
    systemctl restart manike-api
  "
'
```

**If you changed the Cloud Run Job worker** (deploy/cloud-run-job/):
```bash
# Rebuild and push the Docker image, then update the job
export PROJECT_ID=YOUR_GCP_PROJECT_ID
export DATABASE_URL="postgresql://manike:manike_secret@PG_INTERNAL_IP:5432/manike_db"
export GCS_BUCKET_NAME=manike-ai-media

./deploy/setup-cloud-run-job.sh
```

### Verify deployment

```bash
# Get the app server's public IP
gcloud compute instances describe manike-app \
    --zone=us-central1-a \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)'

# Check serial output for startup progress
gcloud compute instances get-serial-port-output manike-app --zone=us-central1-a | grep 'Manike API'

# Test the API
curl http://<APP_IP>:8000/docs
curl http://<APP_IP>:8000/auth/login -d "username=admin@manike.ai&password=admin123"
```

### SSH access
```bash
gcloud compute ssh manike-app --zone=us-central1-a                       # App server
gcloud compute ssh manike-postgres --zone=us-central1-a --tunnel-through-iap  # DB
gcloud compute ssh manike-milvus --zone=us-central1-a --tunnel-through-iap    # Milvus
```

### Check service logs
```bash
gcloud compute ssh manike-app --zone=us-central1-a --command='sudo journalctl -u manike-api -f --no-pager -n 50'
```

## Work Done
- [x] Multi-Tenant Database Design with SQLModel + PostgreSQL
- [x] JWT Auth System with configurable secret key
- [x] AI Orchestration Pipeline: description → prompts → generation → processing → GCS
- [x] Pluggable AI Providers (Gemini, Claude) with factory pattern
- [x] Chat-driven itinerary generation with conversation flow state machine
- [x] Milvus Integration: 4 collections for semantic search (images, clips, experiences, tenants)
- [x] Dual-write persistence: SQL + Milvus for images and clips
- [x] Media Processing: FFmpeg normalization (H.264/30fps/AAC) and concatenation
- [x] Video Compilation: collect clips per itinerary, stitch, upload to GCS (local + Cloud Run)
- [x] GCS Storage: replaced S3 with Google Cloud Storage
- [x] GCP Deployment: 3-VM architecture with single deploy script + Cloud NAT
- [x] Cloud Run Job: Async video compilation offloaded to serverless container
- [x] Chat UI: Built-in web interface with voice + avatar support
