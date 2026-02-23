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

### Seeding the DB
```bash
python3 seed_db.py
```

### Running the Engine
```bash
python3 app/main.py
```

Access the Swagger UI at `http://localhost:8000/docs`

## GCP Deployment

The `deploy/` directory contains everything needed to provision the backend on 3 GCP Compute Engine VMs:

| VM | Role | Machine Type | Network |
|----|------|-------------|---------|
| `manike-postgres` | PostgreSQL (Docker) | e2-micro | Internal only |
| `manike-milvus` | Milvus + etcd + MinIO (Docker Compose) | e2-small | Internal only |
| `manike-app` | FastAPI application | e2-micro | Public (ephemeral IP) |

### Deploy files

| File | Purpose |
|------|---------|
| `deploy/deploy-gcp.sh` | One-command provisioning script |
| `deploy/docker-compose-postgres.yml` | PostgreSQL container config |
| `deploy/docker-compose-milvus.yml` | Milvus stack config |
| `deploy/manike-api.service` | Systemd unit for the FastAPI service |
| `deploy/.env.gcp.example` | Environment variable template |

### Quick deploy

```bash
./deploy/deploy-gcp.sh \
    --project YOUR_GCP_PROJECT_ID \
    --gemini-key YOUR_GEMINI_API_KEY \
    --repo-url https://github.com/YOUR_ORG/menike_backend_poc.git
```

The script will:
1. Create firewall rules (port 8000 public, 5432/19530 internal only)
2. Provision all 3 VMs with startup scripts
3. Create a publicly-readable GCS bucket
4. Configure the app with internal IPs, seed the database, and start the service

Once complete, retrieve the public URL:
```bash
gcloud compute instances get-serial-port-output manike-app --zone=us-central1-a | grep 'Manike API'
```

### SSH access
```bash
gcloud compute ssh manike-app --zone=us-central1-a       # App server
gcloud compute ssh manike-postgres --zone=us-central1-a   # DB (IAP tunnel)
gcloud compute ssh manike-milvus --zone=us-central1-a     # Milvus (IAP tunnel)
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
- [x] Video Compilation: collect clips per itinerary, stitch, upload to GCS
- [x] GCS Storage: replaced S3 with Google Cloud Storage
- [x] GCP Deployment: 3-VM architecture with single deploy script
