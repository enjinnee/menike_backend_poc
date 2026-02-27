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
- **FieldExtractor** uses AI + regex to parse user messages; **ResponseGenerator** creates contextual replies keeping chat clean — the itinerary detail appears only in the right panel, never in chat.

### 5. Persistence Layer
- **SQL Data**: PostgreSQL for relational metadata (tenants, users, itineraries, media records).
- **Vector DB (Milvus)**: 4 collections — `experiences` (4-dim), `tenants` (metadata), `image_vectors` (128-dim), `clip_vectors` (128-dim) — all COSINE + HNSW indexed for semantic search.
- **Blob Storage**: Google Cloud Storage for binary media hosting.

### 6. Core Workflow
Chat session → extract travel requirements → AI generates itinerary JSON → match images/clips via Milvus semantic search → compile video from matched clips (FFmpeg) → upload to GCS.

---

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
| `VIDEO_COMPILER` | `local` (FFmpeg on VM, default) or `cloudrun` (async Cloud Run Job) |
| `CLOUD_RUN_JOB_NAME` | Full Cloud Run Job resource name (required when `VIDEO_COMPILER=cloudrun`) |
| `CLOUD_RUN_REGION` | Cloud Run region (default: `us-central1`) |

### Seeding the DB
```bash
python3 seed_db.py
```
Creates the default tenant, a tenant admin (`admin@manike.ai` / `admin123`), and a super admin (`superadmin@manike.ai` / `superadmin123`).

### Running the Engine
```bash
python3 app/main.py
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Access the Swagger UI at `http://localhost:8000/docs`

---

## Chat UI

The backend serves a built-in chat interface for AI-powered travel planning.

### Accessing the Chat UI

1. Open `http://<HOST>:8000/auth/login` in your browser
2. Log in with `admin@manike.ai` / `admin123`
3. You'll be redirected to the chat UI at `http://<HOST>:8000/`

**Staging URL:** http://35.239.250.79:8000/auth/login

The chat UI supports:
- Natural language conversation to collect travel preferences
- AI-powered itinerary generation (auto-triggered when all fields are collected)
- Image and cinematic clip matching per activity via Milvus semantic search
- Cinematic video compilation with live progress indicator
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

# 5. Compile video
curl -s -X POST http://localhost:8000/itinerary/ITINERARY_ID/compile-video \
  -H "Authorization: Bearer $TOKEN"

# 6. Poll video status (when VIDEO_COMPILER=cloudrun)
curl -s http://localhost:8000/itinerary/ITINERARY_ID/video-status \
  -H "Authorization: Bearer $TOKEN"
```

---

## Inserting Data into PostgreSQL and Milvus

When you upload images or cinematic clips, the backend performs a **dual-write**: it saves metadata to PostgreSQL and generates a 128-dim embedding that gets inserted into Milvus for semantic search.

### Authentication

```bash
TOKEN=$(curl -s http://localhost:8000/auth/login \
  -d "username=admin@manike.ai&password=admin123" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Upload Images

```bash
# Upload a file directly
curl -X POST http://localhost:8000/images/upload-file \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=Galle Fort Lighthouse" \
  -F "tags=galle,fort,sunset,heritage,lighthouse" \
  -F "location=Galle, Sri Lanka" \
  -F "file=@/path/to/galle-fort.jpg"

# Register by URL (if already in GCS)
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

```bash
# Upload a video file
curl -X POST http://localhost:8000/cinematic-clips/upload-file \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=Galle Fort Aerial Drone" \
  -F "tags=galle,fort,drone,aerial,heritage" \
  -F "duration=15.5" \
  -F "description=Drone footage of Galle Fort from above" \
  -F "file=@/path/to/galle-drone.mp4"

# Register by URL
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

```bash
curl -X POST http://localhost:8000/images/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "beautiful ancient fortress at sunset", "limit": 5}'

curl -X POST http://localhost:8000/cinematic-clips/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "aerial drone shot of historic fort", "limit": 5}'
```

### Batch Upload

```bash
for img in /path/to/images/*.jpg; do
  name=$(basename "$img" .jpg | tr '-_' ' ')
  curl -X POST http://localhost:8000/images/upload-file \
    -H "Authorization: Bearer $TOKEN" \
    -F "name=$name" \
    -F "tags=sri-lanka,travel" \
    -F "file=@$img"
done
```

---

## GCP Deployment

The `deploy/` directory contains everything needed to provision the backend on GCP.

### Staging Environment (Project: `manike-ai-staging`)

> Environment variables are stored in `.env` on the `manike-app` Compute Engine VM.

| Resource | GCP Console Link |
|----------|-----------------|
| All Compute Engine VMs | [View VMs](https://console.cloud.google.com/compute/instances?project=manike-ai-staging) |
| `manike-app` VM (FastAPI) | [View instance](https://console.cloud.google.com/compute/instancesDetail/zones/us-central1-a/instances/manike-app?project=manike-ai-staging) |
| `manike-postgres` VM | [View instance](https://console.cloud.google.com/compute/instancesDetail/zones/us-central1-a/instances/manike-postgres?project=manike-ai-staging) |
| `manike-milvus` VM | [View instance](https://console.cloud.google.com/compute/instancesDetail/zones/us-central1-a/instances/manike-milvus?project=manike-ai-staging) |
| `manike-ai-media` GCS bucket | [View bucket](https://console.cloud.google.com/storage/browser/manike-ai-media?project=manike-ai-staging) |
| Cloud Run Jobs | [View jobs](https://console.cloud.google.com/run/jobs?project=manike-ai-staging) |
| `manike-video-compiler` job | [View job](https://console.cloud.google.com/run/jobs/details/us-central1/manike-video-compiler?project=manike-ai-staging) |
| VPC connectors | [View connectors](https://console.cloud.google.com/networking/connectors/list?project=manike-ai-staging) |
| Firewall rules | [View firewall](https://console.cloud.google.com/networking/firewalls/list?project=manike-ai-staging) |
| Logs | [View logs](https://console.cloud.google.com/logs/query?project=manike-ai-staging) |

**View or edit environment variables on the staging VM:**
```bash
gcloud compute ssh manike-app --zone=us-central1-a --project=manike-ai-staging
sudo cat /home/manike/menike_backend_poc/.env
sudo nano /home/manike/menike_backend_poc/.env
sudo systemctl restart manike-api
```

**Single-command variable update:**
```bash
gcloud compute ssh manike-app --zone=us-central1-a --project=manike-ai-staging \
  --command='sudo sed -i "s/^AI_PROVIDER=.*/AI_PROVIDER=claude/" /home/manike/menike_backend_poc/.env && sudo systemctl restart manike-api'
```

### Infrastructure

| Resource | Type | Details |
|----------|------|---------|
| `manike-postgres` | GCE e2-micro | PostgreSQL 15 in Docker, internal-only |
| `manike-milvus` | GCE e2-small | Milvus + etcd + MinIO in Docker, internal-only |
| `manike-app` | GCE e2-micro | FastAPI via systemd, static public IP |
| `manike-ai-media` | GCS bucket | Media storage (publicly readable) |
| `manike-video-compiler` | Cloud Run Job | Async video compilation (2 vCPU, 4 GB RAM, maxRetries=2) |
| `manike-connector` | VPC connector | Routes Cloud Run → internal VMs (PostgreSQL at `10.128.0.2`) |
| `manike-router` / `manike-nat` | Cloud NAT | Internet access for internal VMs |

### Deploy files

| File | Purpose |
|------|---------|
| `deploy/deploy-gcp.sh` | One-command provisioning and redeploy script |
| `deploy/setup-cloud-run-job.sh` | Cloud Run Job setup (VPC connector, image build, IAM) |
| `deploy/cloud-run-job/Dockerfile` | Worker image — build context is repo root |
| `deploy/cloud-run-job/worker.py` | Video stitching worker with GCS idempotency check |
| `deploy/cloud-run-job/requirements.txt` | Worker Python deps |
| `deploy/docker-compose-postgres.yml` | PostgreSQL container config |
| `deploy/docker-compose-milvus.yml` | Milvus stack config |
| `deploy/manike-api.service` | Systemd unit for the FastAPI service |

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

**deploy-gcp.sh flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--project` | *(required)* | GCP project ID |
| `--gemini-key` | — | Gemini API key |
| `--secret-key` | *(random)* | JWT signing secret |
| `--postgres-password` | `manike_secret` | PostgreSQL password |
| `--zone` | `us-central1-a` | GCE zone |
| `--bucket` | `manike-ai-media` | GCS bucket name |
| `--repo-url` | — | Git repo URL (for git deploy method) |
| `--repo-branch` | `main` | Git branch |
| `--deploy-method` | `scp` | `git` or `scp` |
| `--redeploy` | — | Push updated code to existing VM and restart |
| `--rebuild-worker` | — | Also rebuild and push the Cloud Run job image (use with `--redeploy`) |
| `--teardown` | — | Destroy all VMs, IPs, firewall, NAT, SA (bucket preserved) |

### Redeploying After Code Changes

**API only (most common):**
```bash
./deploy/deploy-gcp.sh --project manike-ai-staging --redeploy
```

**API + Cloud Run video worker** (when `worker.py`, `media_processor.py`, or `storage.py` changed):
```bash
./deploy/deploy-gcp.sh --project manike-ai-staging --redeploy --rebuild-worker
```

The redeploy: tarballs local code → SCPs to VM → extracts (preserving `.env`) → `pip install` → runs migrations → restarts the service. With `--rebuild-worker` it also: builds a linux/amd64 Docker image → pushes to Artifact Registry → updates the Cloud Run Job.

### Setting Up the Cloud Run Video Compiler (first time)

```bash
# Create Artifact Registry repo (one-time)
gcloud artifacts repositories create manike \
    --repository-format=docker --location=us-central1 \
    --project=YOUR_GCP_PROJECT_ID

# Get the PostgreSQL internal IP
PG_IP=$(gcloud compute instances describe manike-postgres \
    --zone=us-central1-a --format='get(networkInterfaces[0].networkIP)')

# Build, push, and configure the Cloud Run Job
export PROJECT_ID=YOUR_GCP_PROJECT_ID
export DATABASE_URL="postgresql://manike:manike_secret@${PG_IP}:5432/manike_db"
export GCS_BUCKET_NAME=manike-ai-media

./deploy/setup-cloud-run-job.sh
```

`setup-cloud-run-job.sh` will:
1. Enable `vpcaccess.googleapis.com` and other required APIs
2. Create the `manike-connector` VPC connector if it doesn't exist (allows Cloud Run to reach PostgreSQL on its internal IP)
3. Build and push the Docker image using the repo root as the build context
4. Create or update the Cloud Run Job with `--max-retries=2`, VPC connector, 2 vCPU, 4 GB RAM
5. Grant `roles/run.admin` to the app service account

Then configure the app VM:
```bash
gcloud compute ssh manike-app --zone=us-central1-a --command='
  sudo bash -c "cat >> /home/manike/menike_backend_poc/.env <<EOF
VIDEO_COMPILER=cloudrun
CLOUD_RUN_JOB_NAME=projects/YOUR_PROJECT_ID/locations/us-central1/jobs/manike-video-compiler
CLOUD_RUN_REGION=us-central1
EOF"
  sudo systemctl restart manike-api
'
```

### Video Compiler Retry Behaviour

The Cloud Run Job uses `maxRetries=2`. On retry the worker skips re-encoding:

1. Before stitching, the worker checks whether the output MP4 already exists in GCS
2. If it does → skips FFmpeg stitching and GCS upload, jumps straight to the DB update
3. If stitching fails → exits immediately (no retry will fix a broken clip encoding)
4. If only the DB update fails → the job retries and the GCS check prevents double-encoding

This means a transient DB/network error will recover on retry without wasting CPU re-compiling the video.

### Tearing Down

```bash
# Destroy all VMs, IPs, firewall rules, NAT, SA (bucket is preserved)
./deploy/deploy-gcp.sh --project manike-ai-staging --teardown
```

---

## Accessing Milvus and PostgreSQL Locally

Both databases are on **internal-only VMs**. Access them via SSH tunnel through the `manike-app` VM.

### Milvus — Attu GUI

**Step 1 — Open SSH tunnel (keep terminal open):**
```bash
gcloud compute ssh manike-app \
    --zone=us-central1-a --project=manike-ai-staging \
    -- -L 19530:10.128.0.3:19530 -N
```

**Step 2 — Launch Attu:**
```bash
docker run -d --rm -p 8080:3000 \
    -e MILVUS_URL=host.docker.internal:19530 \
    zilliz/attu:latest
```

Open `http://localhost:8080` and connect with `host.docker.internal:19530`.

**Query via Python:**
```python
from pymilvus import connections, Collection, utility
connections.connect(host="localhost", port=19530)
print(utility.list_collections())
coll = Collection("image_vectors")
coll.load()
results = coll.query(expr='id != ""', output_fields=["id", "metadata"], limit=10)
for r in results:
    print(r)
```

### PostgreSQL — psql / pgAdmin

**Step 1 — Open SSH tunnel:**
```bash
gcloud compute ssh manike-app \
    --zone=us-central1-a --project=manike-ai-staging \
    -- -L 5432:10.128.0.2:5432 -N
```

**Step 2 — Connect:**
```bash
psql "postgresql://manike:manike_secret@localhost:5432/manike_db"
```

Or connect pgAdmin to `localhost:5432`, database `manike_db`, user `manike`.

**Useful queries:**
```sql
-- All uploaded images
SELECT name, location, image_url FROM image_library ORDER BY created_at DESC;

-- All cinematic clips
SELECT name, video_url, duration FROM cinematic_clip ORDER BY created_at DESC;

-- Generated itineraries
SELECT destination, days, status, created_at FROM itinerary ORDER BY created_at DESC;

-- Activity-to-clip mapping
SELECT day, activity_name, location, cinematic_clip_url
FROM itinerary_activity
WHERE itinerary_id = 'YOUR_ITINERARY_ID'
ORDER BY day, order_index;

-- Final compiled videos
SELECT fv.video_url, i.destination, fv.status, fv.created_at
FROM final_video fv
JOIN itinerary i ON i.id = fv.itinerary_id
ORDER BY fv.created_at DESC;
```

### Operational Commands

```bash
# Stream API logs
gcloud compute ssh manike-app --zone=us-central1-a \
    --command='sudo journalctl -u manike-api -f --no-pager -n 50'

# Check Cloud Run job executions
gcloud run jobs executions list --job=manike-video-compiler \
    --region=us-central1 --project=manike-ai-staging --limit=5

# Stream Cloud Run job logs
gcloud logging read 'resource.labels.job_name="manike-video-compiler"' \
    --project=manike-ai-staging --limit=50 \
    --format='value(severity,textPayload)'

# SSH access
gcloud compute ssh manike-app --zone=us-central1-a
gcloud compute ssh manike-postgres --zone=us-central1-a --tunnel-through-iap
gcloud compute ssh manike-milvus --zone=us-central1-a --tunnel-through-iap
```

---

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
- [x] Cloud Run Job: Async video compilation with VPC connector for DB access
- [x] Idempotent worker: GCS check prevents re-encoding on Cloud Run retries
- [x] Chat UI: clean conversation — itinerary detail in panel only, not in chat messages
- [x] Chat UI: live video compilation progress with auto-polling (no page refresh needed)
- [x] Chat UI: voice input mode with HeyGen avatar integration
