# Manike B2B AI Engine POC

A high-performance, multi-tenant AI engine for cinematic itinerary and scene orchestration.

## 🏗️ Architecture Overview

The engine follows a layered B2B architecture designed for scalability, security, and AI resource management.

### 1. API Layer (FastAPI)
- **Modular Routing**: Organized into `auth`, `scenes`, and `itinerary` domains.
- **Tenant-Aware**: Every request is authenticated via JWT and scoped to a specific `tenant_id`.

### 2. Core Infrastructure
- **Authentication**: JWT-based OAuth2 flow with `pbkdf2_sha256` password hashing.
- **Database (SQLModel)**: High-level ORM managing `Tenant`, `User`, and `Scene` entities. (PostgreSQL ready, currently using SQLite for POC).

### 3. Scene Orchestrator Service
The heartbeat of the system. It coordinates:
- **LLM Prompt Engine**: Transforms user descriptions into optimized AI prompts.
- **Generators**: Mocked AI services for Image and Video generation (VEO-3 ready).
- **Media Processor**: FFmpeg wrapper for video optimization and normalization.
- **Storage Service**: S3-compatible persistence for generated media assets.

### 4. Persistence Layer
- **SQL Data**: Relational metadata for tenants and users.
- **Vector DB (Milvus)**: Integrated for high-dimensional experience search and semantic retrieval.
- **Blob Storage**: S3 for binary media hosting.

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- FFmpeg (for media processing)
- Milvus (optional, backend will skip if unavailable)

### Installation
```bash
pip install -r requirements.txt
```

### Seeding the DB
```bash
python3 seed_db.py
```

### Running the Engine
```bash
python3 app/main.py
```

Access the Swagger UI at `http://localhost:8000/docs`

## 🛠️ Work Done in POC
- [x] **Multi-Tenant Database Design**: Implemented SQLModel schema for isolation.
- [x] **JWT Auth System**: Secure login and tenant identification flow.
- [x] **AI Orchestration Pipeline**: Full flow from description -> prompts -> generation -> processing -> S3.
- [x] **Milvus Integration**: Foundation for vector-based itinerary discovery.
- [x] **Media Processing**: FFmpeg integration for localized video optimization.
- [x] **API Stabilization**: Resolved dependency issues, import errors, and refined error handling.