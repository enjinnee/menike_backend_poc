#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Provisions the Cloud Run *Job* used for async video compilation.
#
# Prerequisites:
#   - gcloud CLI authenticated with a project that has Cloud Run + Artifact
#     Registry APIs enabled.
#   - Docker available and authenticated to Artifact Registry.
#   - The following env vars (or edit the defaults below):
#       PROJECT_ID, REGION, REPOSITORY, DATABASE_URL,
#       GCS_BUCKET_NAME, GCS_BASE_PREFIX
#       INVOKER_SA  (optional — defaults to manike-app@PROJECT_ID.iam.gserviceaccount.com)
#       VPC_CONNECTOR (optional — defaults to manike-connector)
#
# Retry behaviour:
#   maxRetries=2 — if the DB update fails the job retries up to 2 times.
#   Video stitching + GCS upload are idempotent: the worker checks whether
#   the output object already exists in GCS before re-encoding, so retries
#   never re-compile the video.
# ============================================================================

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-manike}"
JOB_NAME="${JOB_NAME:-manike-video-compiler}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${JOB_NAME}:${IMAGE_TAG}"
VPC_CONNECTOR="${VPC_CONNECTOR:-manike-connector}"
VPC_CONNECTOR_RANGE="${VPC_CONNECTOR_RANGE:-10.8.0.0/28}"

# DB + GCS settings baked into the Job (not per-execution)
DATABASE_URL="${DATABASE_URL:?Set DATABASE_URL}"
GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-manike-ai-media}"
GCS_BASE_PREFIX="${GCS_BASE_PREFIX:-experience-images}"

# Service account that runs the API server and needs permission to invoke this job.
INVOKER_SA="${INVOKER_SA:-manike-app@${PROJECT_ID}.iam.gserviceaccount.com}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# 1. Enable required APIs
# ---------------------------------------------------------------------------
echo "==> Enabling required APIs..."
gcloud services enable \
    vpcaccess.googleapis.com \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    --project="${PROJECT_ID}" --quiet

# ---------------------------------------------------------------------------
# 2. Ensure VPC connector exists (Cloud Run → internal VMs / PostgreSQL)
# ---------------------------------------------------------------------------
echo "==> Checking VPC connector: ${VPC_CONNECTOR}"
if ! gcloud compute networks vpc-access connectors describe "${VPC_CONNECTOR}" \
        --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "    Creating VPC connector ${VPC_CONNECTOR} (${VPC_CONNECTOR_RANGE})..."
    gcloud compute networks vpc-access connectors create "${VPC_CONNECTOR}" \
        --region="${REGION}" \
        --network=default \
        --range="${VPC_CONNECTOR_RANGE}" \
        --project="${PROJECT_ID}"
else
    echo "    VPC connector ${VPC_CONNECTOR} already exists."
fi

# ---------------------------------------------------------------------------
# 3. Build & push image
#    Build context is the repo root so the Dockerfile can COPY app/ modules.
# ---------------------------------------------------------------------------
echo "==> Building image: ${IMAGE_URI}"
# --platform linux/amd64 ensures compatibility with Cloud Run (needed on Apple Silicon)
docker buildx build \
    --platform linux/amd64 \
    -f "${SCRIPT_DIR}/cloud-run-job/Dockerfile" \
    -t "${IMAGE_URI}" \
    --push \
    "${REPO_ROOT}"

# ---------------------------------------------------------------------------
# 4. Create (or update) the Cloud Run Job
# ---------------------------------------------------------------------------
echo "==> Creating/updating Cloud Run Job: ${JOB_NAME}"

COMMON_FLAGS=(
    --region="${REGION}"
    --project="${PROJECT_ID}"
    --image="${IMAGE_URI}"
    --cpu=2
    --memory=4Gi
    --task-timeout=600s
    --max-retries=2
    --vpc-connector="${VPC_CONNECTOR}"
    --vpc-egress=private-ranges-only
    --set-env-vars="DATABASE_URL=${DATABASE_URL},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},GCS_BASE_PREFIX=${GCS_BASE_PREFIX}"
)

if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud run jobs update "${JOB_NAME}" "${COMMON_FLAGS[@]}"
else
    gcloud run jobs create "${JOB_NAME}" "${COMMON_FLAGS[@]}"
fi

# ---------------------------------------------------------------------------
# 5. Grant the API service account permission to invoke the job
#
# roles/run.invoker only covers run.jobs.run. Passing container overrides
# (env vars per execution) also requires run.jobs.runWithOverrides, so we
# use roles/run.admin scoped to this job resource instead.
# ---------------------------------------------------------------------------
echo "==> Granting roles/run.admin (job-scoped) to ${INVOKER_SA}..."
gcloud run jobs add-iam-policy-binding "${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --member="serviceAccount:${INVOKER_SA}" \
    --role="roles/run.admin"

FULL_JOB_NAME="projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}"
echo ""
echo "==> Done! Set these env vars on your API server:"
echo "    VIDEO_COMPILER=cloudrun"
echo "    CLOUD_RUN_JOB_NAME=${FULL_JOB_NAME}"
echo "    CLOUD_RUN_REGION=${REGION}"
