#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Provisions the Cloud Run *Job* used for async video compilation.
#
# Prerequisites:
#   - gcloud CLI authenticated with a project that has Cloud Run + Artifact
#     Registry APIs enabled.
#   - Docker (or gcloud builds submit) available.
#   - The following env vars (or edit the defaults below):
#       PROJECT_ID, REGION, REPOSITORY, DATABASE_URL,
#       GCS_BUCKET_NAME, GCS_BASE_PREFIX
# ============================================================================

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-manike}"
JOB_NAME="${JOB_NAME:-manike-video-compiler}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${JOB_NAME}:${IMAGE_TAG}"

# DB + GCS settings baked into the Job (not per-execution)
DATABASE_URL="${DATABASE_URL:?Set DATABASE_URL}"
GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-manike-ai-media}"
GCS_BASE_PREFIX="${GCS_BASE_PREFIX:-experience-images}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# 1. Build context — we need files from both deploy/cloud-run-job/ and app/
# ---------------------------------------------------------------------------
BUILD_DIR=$(mktemp -d)
trap 'rm -rf "${BUILD_DIR}"' EXIT

cp "${SCRIPT_DIR}/cloud-run-job/Dockerfile"       "${BUILD_DIR}/"
cp "${SCRIPT_DIR}/cloud-run-job/requirements.txt"  "${BUILD_DIR}/"
cp "${SCRIPT_DIR}/cloud-run-job/worker.py"         "${BUILD_DIR}/"

mkdir -p "${BUILD_DIR}/app/services" "${BUILD_DIR}/app/models"

# Create __init__.py files (these may not exist in the source repo)
touch "${BUILD_DIR}/app/__init__.py"
touch "${BUILD_DIR}/app/services/__init__.py"
touch "${BUILD_DIR}/app/models/__init__.py"

cp "${REPO_ROOT}/app/services/media_processor.py"  "${BUILD_DIR}/app/services/"
cp "${REPO_ROOT}/app/services/storage.py"           "${BUILD_DIR}/app/services/"
cp "${REPO_ROOT}/app/models/sql_models.py"          "${BUILD_DIR}/app/models/"

# ---------------------------------------------------------------------------
# 2. Build & push image
# ---------------------------------------------------------------------------
echo "==> Building image: ${IMAGE_URI}"
# Cloud Run requires linux/amd64; use buildx to cross-compile on Apple Silicon
docker buildx build --platform linux/amd64 -t "${IMAGE_URI}" --push "${BUILD_DIR}"

# ---------------------------------------------------------------------------
# 3. Create (or update) the Cloud Run Job
# ---------------------------------------------------------------------------
echo "==> Creating/updating Cloud Run Job: ${JOB_NAME}"
if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud run jobs update "${JOB_NAME}" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --image="${IMAGE_URI}" \
        --cpu=2 \
        --memory=4Gi \
        --task-timeout=600s \
        --set-env-vars="DATABASE_URL=${DATABASE_URL},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},GCS_BASE_PREFIX=${GCS_BASE_PREFIX}"
else
    gcloud run jobs create "${JOB_NAME}" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --image="${IMAGE_URI}" \
        --cpu=2 \
        --memory=4Gi \
        --task-timeout=600s \
        --set-env-vars="DATABASE_URL=${DATABASE_URL},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},GCS_BASE_PREFIX=${GCS_BASE_PREFIX}"
fi

# Print the fully-qualified job name for use in VIDEO_COMPILER config
FULL_JOB_NAME="projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}"
echo ""
echo "==> Done! Set these env vars on your API server:"
echo "    VIDEO_COMPILER=cloudrun"
echo "    CLOUD_RUN_JOB_NAME=${FULL_JOB_NAME}"
echo "    CLOUD_RUN_REGION=${REGION}"
