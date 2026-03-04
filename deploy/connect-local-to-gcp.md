# Connecting Local App to GCP Services

## Prerequisites

Authenticate with GCP:
```bash
gcloud auth login
gcloud auth application-default login
```

---

## 1. GCS (Cloud Storage)

No tunnel needed — GCS is a public API. ADC credentials are picked up automatically after `application-default login`.

Set in `.env`:
```
GCS_BUCKET_NAME=manike-ai-media
GCS_BASE_PREFIX=experience-images
```

---

## 2. Get Internal IPs of GCP VMs

```bash
gcloud compute instances describe manike-postgres --zone=us-central1-a \
  --format='get(networkInterfaces[0].networkIP)'

gcloud compute instances describe manike-milvus --zone=us-central1-a \
  --format='get(networkInterfaces[0].networkIP)'
```

---

## 3. SSH Tunnel — PostgreSQL + Milvus

Both VMs have internal-only IPs. Tunnel through `manike-app` (which has the public static IP):

```bash
gcloud compute ssh manike-app --zone=us-central1-a -- \
  -L 5433:<POSTGRES_INTERNAL_IP>:5432 \
  -L 19530:<MILVUS_INTERNAL_IP>:19530 \
  -N
```

Keep this terminal open while running the app locally.

---

## 4. Local .env Settings

```
DATABASE_URL=postgresql://manike:manike_secret@localhost:5433/manike_db
MILVUS_HOST=localhost
MILVUS_PORT=19530
GCS_BUCKET_NAME=manike-ai-media
GCS_BASE_PREFIX=experience-images
```

---

## 5. Start the App

```bash
cd menike_backend_poc
source .venv/bin/activate
python3 app/main.py
```

Swagger UI: http://localhost:8000/docs
