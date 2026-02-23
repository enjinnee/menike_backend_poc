#!/usr/bin/env bash
#
# deploy-gcp.sh — Provision 3 GCE VMs for the Manike AI backend.
#
# Usage:
#   ./deploy/deploy-gcp.sh \
#       --project YOUR_GCP_PROJECT_ID \
#       --gemini-key YOUR_GEMINI_API_KEY \
#       [--secret-key YOUR_JWT_SECRET] \
#       [--postgres-password YOUR_PG_PASSWORD] \
#       [--zone us-central1-a] \
#       [--bucket manike-ai-media]
#
# Prerequisites:
#   - gcloud CLI authenticated (gcloud auth login && gcloud auth application-default login)
#   - Billing enabled on the GCP project
#

set -euo pipefail

# ──────────────────────────── Defaults ────────────────────────────
ZONE="us-central1-a"
REGION="us-central1"
BUCKET="manike-ai-media"
PG_PASSWORD="manike_secret"
SECRET_KEY="$(openssl rand -hex 32 2>/dev/null || echo change-me-$(date +%s))"
GEMINI_KEY=""
PROJECT=""
REPO_URL="https://github.com/YOUR_ORG/menike_backend_poc.git"
REPO_BRANCH="main"

# ──────────────────────────── Parse args ──────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project)          PROJECT="$2";          shift 2 ;;
        --gemini-key)       GEMINI_KEY="$2";       shift 2 ;;
        --secret-key)       SECRET_KEY="$2";       shift 2 ;;
        --postgres-password) PG_PASSWORD="$2";     shift 2 ;;
        --zone)             ZONE="$2";             shift 2 ;;
        --bucket)           BUCKET="$2";           shift 2 ;;
        --repo-url)         REPO_URL="$2";         shift 2 ;;
        --repo-branch)      REPO_BRANCH="$2";      shift 2 ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
done

if [[ -z "$PROJECT" ]]; then
    echo "Error: --project is required"
    exit 1
fi

REGION="${ZONE%-*}"

echo "==> Deploying Manike AI to GCP project: $PROJECT (zone: $ZONE)"
gcloud config set project "$PROJECT"

# ──────────────────────────── Firewall ────────────────────────────
echo "==> Creating firewall rules..."

gcloud compute firewall-rules create allow-manike-app \
    --direction=INGRESS --priority=1000 --network=default \
    --action=ALLOW --rules=tcp:8000 \
    --target-tags=app-server \
    --source-ranges=0.0.0.0/0 \
    --description="Allow public access to Manike API" \
    2>/dev/null || echo "    (firewall rule allow-manike-app already exists)"

gcloud compute firewall-rules create allow-manike-db \
    --direction=INGRESS --priority=1000 --network=default \
    --action=ALLOW --rules=tcp:5432 \
    --target-tags=db-server \
    --source-tags=app-server \
    --description="Allow app server to reach PostgreSQL" \
    2>/dev/null || echo "    (firewall rule allow-manike-db already exists)"

gcloud compute firewall-rules create allow-manike-milvus \
    --direction=INGRESS --priority=1000 --network=default \
    --action=ALLOW --rules=tcp:19530 \
    --target-tags=vector-server \
    --source-tags=app-server \
    --description="Allow app server to reach Milvus" \
    2>/dev/null || echo "    (firewall rule allow-manike-milvus already exists)"

# ──────────────────────── VM1: PostgreSQL ─────────────────────────
echo "==> Creating VM1 (PostgreSQL)..."

gcloud compute instances create manike-postgres \
    --zone="$ZONE" \
    --machine-type=e2-micro \
    --no-address \
    --tags=db-server \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=20GB \
    --metadata=startup-script="$(cat <<'STARTUP'
#!/bin/bash
set -e
apt-get update -y
apt-get install -y docker.io docker-compose
systemctl enable docker && systemctl start docker

mkdir -p /opt/manike
cat > /opt/manike/docker-compose.yml <<'DCEOF'
version: "3.8"
services:
  postgres:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_DB: manike_db
      POSTGRES_USER: manike
      POSTGRES_PASSWORD: PLACEHOLDER_PG_PASSWORD
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
DCEOF

sed -i "s/PLACEHOLDER_PG_PASSWORD/${PG_PASSWORD_ENV:-manike_secret}/" /opt/manike/docker-compose.yml
cd /opt/manike && docker-compose up -d
echo "PostgreSQL is running" > /dev/ttyS0
STARTUP
)" \
    --metadata=PG_PASSWORD_ENV="$PG_PASSWORD"

# ──────────────────────── VM2: Milvus ─────────────────────────────
echo "==> Creating VM2 (Milvus)..."

gcloud compute instances create manike-milvus \
    --zone="$ZONE" \
    --machine-type=e2-small \
    --no-address \
    --tags=vector-server \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=30GB \
    --metadata=startup-script='#!/bin/bash
set -e
apt-get update -y
apt-get install -y docker.io docker-compose curl
systemctl enable docker && systemctl start docker

mkdir -p /opt/manike
cat > /opt/manike/docker-compose.yml <<'"'"'DCEOF'"'"'
version: "3.8"
services:
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    restart: always
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
      ETCD_SNAPSHOT_COUNT: "50000"
    volumes:
      - etcd_data:/etcd
    command: >
      etcd
      --advertise-client-urls=http://127.0.0.1:2379
      --listen-client-urls=http://0.0.0.0:2379
      --data-dir=/etcd
      --initial-advertise-peer-urls=http://127.0.0.1:2380
      --listen-peer-urls=http://0.0.0.0:2380
      --initial-cluster=default=http://127.0.0.1:2380
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3
  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    restart: always
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    volumes:
      - minio_data:/minio_data
    command: minio server /minio_data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
  milvus:
    image: milvusdb/milvus:v2.4.4
    restart: always
    command: ["milvus", "run", "standalone"]
    security_opt:
      - seccomp:unconfined
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
      - "9091:9091"
    volumes:
      - milvus_data:/var/lib/milvus
    depends_on:
      etcd:
        condition: service_healthy
      minio:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      start_period: 90s
      timeout: 20s
      retries: 3
volumes:
  etcd_data:
  minio_data:
  milvus_data:
DCEOF

cd /opt/manike && docker-compose up -d
echo "Milvus is running" > /dev/ttyS0
'

# ──────────────────────── GCS Bucket ──────────────────────────────
echo "==> Creating GCS bucket: gs://$BUCKET"

gsutil mb -l "$REGION" "gs://$BUCKET" 2>/dev/null \
    || echo "    (bucket gs://$BUCKET already exists)"

gsutil iam ch allUsers:objectViewer "gs://$BUCKET"
echo "    Bucket is publicly readable."

# ──────────────── Wait for internal IPs ───────────────────────────
echo "==> Waiting for VM internal IPs..."
sleep 10

PG_IP=$(gcloud compute instances describe manike-postgres \
    --zone="$ZONE" --format='get(networkInterfaces[0].networkIP)')
MILVUS_IP=$(gcloud compute instances describe manike-milvus \
    --zone="$ZONE" --format='get(networkInterfaces[0].networkIP)')

echo "    PostgreSQL internal IP: $PG_IP"
echo "    Milvus internal IP:     $MILVUS_IP"

# ──────────────────────── VM3: App Server ─────────────────────────
echo "==> Creating VM3 (App Server)..."

gcloud compute instances create manike-app \
    --zone="$ZONE" \
    --machine-type=e2-micro \
    --tags=app-server \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=20GB \
    --scopes=storage-rw \
    --metadata=startup-script="#!/bin/bash
set -e

# Print current external IP to serial console for easy retrieval
EXTERNAL_IP=\$(curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)
echo \"Manike API available at: http://\${EXTERNAL_IP}:8000\" > /dev/ttyS0
echo \"Manike API IP: \${EXTERNAL_IP}\" > /dev/ttyS0

# Install system deps
apt-get update -y
apt-get install -y python3 python3-pip python3-venv ffmpeg git

# Create app user
useradd -m -s /bin/bash manike 2>/dev/null || true

# Clone repo
cd /home/manike
if [ ! -d menike_backend_poc ]; then
    sudo -u manike git clone --branch $REPO_BRANCH $REPO_URL menike_backend_poc
fi
cd menike_backend_poc

# Python venv
sudo -u manike python3 -m venv .venv
sudo -u manike .venv/bin/pip install --upgrade pip
sudo -u manike .venv/bin/pip install -r requirements.txt

# Write .env
cat > .env <<ENVEOF
DATABASE_URL=postgresql://manike:${PG_PASSWORD}@${PG_IP}:5432/manike_db
MILVUS_HOST=${MILVUS_IP}
MILVUS_PORT=19530
GCS_BUCKET_NAME=${BUCKET}
GCS_BASE_PREFIX=experience-images
SECRET_KEY=${SECRET_KEY}
AI_PROVIDER=gemini
GEMINI_API_KEY=${GEMINI_KEY}
ENVEOF
chown manike:manike .env
chmod 600 .env

# Seed database (wait for Postgres to be ready)
echo 'Waiting for PostgreSQL...'
for i in \$(seq 1 30); do
    if sudo -u manike .venv/bin/python3 -c \"
import psycopg2
psycopg2.connect('postgresql://manike:${PG_PASSWORD}@${PG_IP}:5432/manike_db')
print('connected')
\" 2>/dev/null; then
        break
    fi
    sleep 5
done

sudo -u manike .venv/bin/python3 seed_db.py || echo 'seed_db.py failed (may need manual run)'

# Install systemd service
cp deploy/manike-api.service /etc/systemd/system/manike-api.service
systemctl daemon-reload
systemctl enable manike-api
systemctl start manike-api

echo 'Manike API service started' > /dev/ttyS0
"

# ──────────────────────── Done ────────────────────────────────────
echo ""
echo "==> Deployment initiated! VMs are booting and running startup scripts."
echo ""
echo "    VM1 (PostgreSQL): manike-postgres  (internal: $PG_IP)"
echo "    VM2 (Milvus):     manike-milvus    (internal: $MILVUS_IP)"
echo "    VM3 (App):        manike-app       (public, ephemeral IP)"
echo ""
echo "==> To get the public URL once VM3 is ready (~3-5 min):"
echo ""
echo "    gcloud compute instances describe manike-app \\"
echo "        --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)'"
echo ""
echo "    Or check serial output:"
echo "    gcloud compute instances get-serial-port-output manike-app --zone=$ZONE | grep 'Manike API'"
echo ""
echo "==> SSH into VMs (IAP tunnel for private VMs):"
echo "    gcloud compute ssh manike-postgres --zone=$ZONE"
echo "    gcloud compute ssh manike-milvus --zone=$ZONE"
echo "    gcloud compute ssh manike-app --zone=$ZONE"
echo ""
echo "==> Swagger UI: http://<APP_IP>:8000/docs"
