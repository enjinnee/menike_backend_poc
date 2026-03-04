#!/usr/bin/env bash
#
# setup-local.sh — Local development setup for Manike AI backend.
#
# Works on macOS and Linux. Handles:
#   - Checking for existing PostgreSQL and Milvus (Docker or native)
#   - Spinning up Docker containers if services are missing
#   - Creating / updating .env
#   - Seeding the database
#   - Starting the FastAPI app
#   - (Optional) Building and running the Cloud Run worker locally via Docker
#
# USAGE
#   ./deploy/setup-local.sh [OPTIONS]
#
# OPTIONS
#   --skip-app          Set up infrastructure only; do not start the API server
#   --skip-seed         Skip database seeding (useful after first run)
#   --reset             Wipe .env and recreate everything from scratch
#   --run-worker        After starting the app, also build & run the Cloud Run
#                       worker container locally (requires ITINERARY_ID + TENANT_ID)
#   --itinerary-id ID   Itinerary ID to pass to the local worker (--run-worker)
#   --tenant-id ID      Tenant ID to pass to the local worker (--run-worker)
#   --cinematic         Use cinematic mode for local worker (default: false)
#   --help              Show this help
#
# EXAMPLES
#   # First-time setup (starts everything, seeds DB)
#   ./deploy/setup-local.sh
#
#   # Restart app without reseeding
#   ./deploy/setup-local.sh --skip-seed
#
#   # Infrastructure + DB seed only, no API server
#   ./deploy/setup-local.sh --skip-app
#
#   # Run the Cloud Run worker locally against itinerary abc-123
#   ./deploy/setup-local.sh --skip-seed --run-worker \
#       --itinerary-id abc-123 --tenant-id default-tenant --cinematic
#

set -euo pipefail

# ─────────────────────────────── Colours ───────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[setup]${RESET} $*"; }
success() { echo -e "${GREEN}[setup]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[setup]${RESET} $*"; }
die()     { echo -e "${RED}[setup] ERROR:${RESET} $*" >&2; exit 1; }

# ─────────────────────────────── Defaults ──────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

SKIP_APP=false
SKIP_SEED=false
RESET=false
RUN_WORKER=false
WORKER_ITINERARY_ID=""
WORKER_TENANT_ID=""
WORKER_CINEMATIC=false

# Docker container names (must match docker-compose.yml)
PG_CONTAINER="manike-postgres"
MILVUS_CONTAINER="manike-milvus"
ETCD_CONTAINER="manike-etcd"
MINIO_CONTAINER="manike-minio"

# Default service coordinates (used when starting via Docker)
PG_HOST="localhost"
PG_PORT="5432"
PG_USER="postgres"
PG_PASS="postgres"
PG_DB="manike"
MILVUS_HOST="localhost"
MILVUS_PORT="19530"

# ──────────────────────────── Argument parsing ─────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-app)       SKIP_APP=true ;;
    --skip-seed)      SKIP_SEED=true ;;
    --reset)          RESET=true ;;
    --run-worker)     RUN_WORKER=true ;;
    --itinerary-id)   shift; WORKER_ITINERARY_ID="$1" ;;
    --tenant-id)      shift; WORKER_TENANT_ID="$1" ;;
    --cinematic)      WORKER_CINEMATIC=true ;;
    --help|-h)
      sed -n '/^# USAGE/,/^[^#]/p' "$0" | head -n -1 | sed 's/^# \{0,2\}//'
      exit 0 ;;
    *) die "Unknown option: $1. Run with --help for usage." ;;
  esac
  shift
done

# ──────────────────────────── Platform detection ───────────────────────
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *)      die "Unsupported platform: $OS" ;;
esac
info "Platform: $PLATFORM"

# ──────────────────────────── Prerequisite checks ──────────────────────
require_cmd() {
  command -v "$1" &>/dev/null || die "'$1' not found. $2"
}

require_cmd python3 "Install Python 3.9+ from https://python.org"
PY_VERSION=$(python3 -c 'import sys; print(sys.version_info.major * 100 + sys.version_info.minor)')
[[ $PY_VERSION -ge 309 ]] || die "Python 3.9+ required (found $(python3 --version))"

# Docker is needed only when we have to spin up containers
DOCKER_AVAILABLE=false
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  DOCKER_AVAILABLE=true
fi

# ──────────────────────────── Reset mode ───────────────────────────────
if [[ "$RESET" == true ]]; then
  warn "--reset: removing .env and virtual environment"
  rm -f "$ENV_FILE"
  rm -rf "$REPO_ROOT/.venv"
fi

# ──────────────────────────────────────────────────────────────────────
# Helper: probe a TCP port quickly
# ──────────────────────────────────────────────────────────────────────
port_open() {
  local host="$1" port="$2"
  # Try nc first, fall back to bash /dev/tcp
  if command -v nc &>/dev/null; then
    nc -z -w2 "$host" "$port" &>/dev/null
  else
    (echo >/dev/tcp/"$host"/"$port") &>/dev/null 2>&1
  fi
}

# ──────────────────────────────────────────────────────────────────────
# Helper: wait for a port to become reachable (max N seconds)
# ──────────────────────────────────────────────────────────────────────
wait_for_port() {
  local host="$1" port="$2" label="$3" max="${4:-60}"
  local elapsed=0
  info "Waiting for $label on $host:$port ..."
  until port_open "$host" "$port"; do
    sleep 2; elapsed=$((elapsed + 2))
    [[ $elapsed -ge $max ]] && die "$label did not become ready within ${max}s"
    printf "."
  done
  echo ""
  success "$label is ready"
}

# ══════════════════════════════════════════════════════════════════════
# 1. PostgreSQL — detect or start
# ══════════════════════════════════════════════════════════════════════
info "Checking PostgreSQL..."

PG_NEEDS_DOCKER=false

if port_open "$PG_HOST" "$PG_PORT"; then
  success "PostgreSQL already reachable at $PG_HOST:$PG_PORT — skipping Docker"
else
  info "PostgreSQL not detected on $PG_HOST:$PG_PORT"

  # Check if the container exists but is stopped
  if [[ "$DOCKER_AVAILABLE" == true ]]; then
    if docker ps -a --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
      CONTAINER_STATE=$(docker inspect --format '{{.State.Status}}' "$PG_CONTAINER")
      if [[ "$CONTAINER_STATE" != "running" ]]; then
        info "Starting existing container '$PG_CONTAINER' (was $CONTAINER_STATE)..."
        docker start "$PG_CONTAINER"
      else
        info "Container '$PG_CONTAINER' is running but port not open yet — waiting..."
      fi
    else
      PG_NEEDS_DOCKER=true
    fi
  else
    die "PostgreSQL is not reachable and Docker is not available. " \
        "Please install Docker (https://docs.docker.com/get-docker/) " \
        "or start PostgreSQL manually on $PG_HOST:$PG_PORT."
  fi
fi

# ══════════════════════════════════════════════════════════════════════
# 2. Milvus — detect or start
# ══════════════════════════════════════════════════════════════════════
info "Checking Milvus..."

MILVUS_NEEDS_DOCKER=false

if port_open "$MILVUS_HOST" "$MILVUS_PORT"; then
  success "Milvus already reachable at $MILVUS_HOST:$MILVUS_PORT — skipping Docker"
else
  info "Milvus not detected on $MILVUS_HOST:$MILVUS_PORT"

  if [[ "$DOCKER_AVAILABLE" == true ]]; then
    if docker ps -a --format '{{.Names}}' | grep -q "^${MILVUS_CONTAINER}$"; then
      CONTAINER_STATE=$(docker inspect --format '{{.State.Status}}' "$MILVUS_CONTAINER")
      if [[ "$CONTAINER_STATE" != "running" ]]; then
        info "Starting existing Milvus stack (etcd + minio + milvus)..."
        docker start "$ETCD_CONTAINER" "$MINIO_CONTAINER" "$MILVUS_CONTAINER" 2>/dev/null || true
      fi
    else
      MILVUS_NEEDS_DOCKER=true
    fi
  else
    die "Milvus is not reachable and Docker is not available. " \
        "Please install Docker or start Milvus manually on $MILVUS_HOST:$MILVUS_PORT."
  fi
fi

# ══════════════════════════════════════════════════════════════════════
# 3. Start containers via docker-compose if needed
# ══════════════════════════════════════════════════════════════════════
if [[ "$PG_NEEDS_DOCKER" == true || "$MILVUS_NEEDS_DOCKER" == true ]]; then
  COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
  [[ -f "$COMPOSE_FILE" ]] || die "docker-compose.yml not found at $REPO_ROOT"

  # Prefer docker compose (v2) over docker-compose (v1)
  if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
  else
    die "Neither 'docker compose' nor 'docker-compose' found. Install Docker Desktop or docker-compose."
  fi

  if [[ "$PG_NEEDS_DOCKER" == true && "$MILVUS_NEEDS_DOCKER" == true ]]; then
    info "Starting full stack (postgres + milvus + etcd + minio) via docker-compose..."
    (cd "$REPO_ROOT" && $COMPOSE_CMD up -d)
  elif [[ "$PG_NEEDS_DOCKER" == true ]]; then
    info "Starting postgres container..."
    (cd "$REPO_ROOT" && $COMPOSE_CMD up -d postgres)
  else
    info "Starting Milvus stack (etcd + minio + milvus)..."
    (cd "$REPO_ROOT" && $COMPOSE_CMD up -d etcd minio milvus)
  fi
fi

# ══════════════════════════════════════════════════════════════════════
# 4. Wait for services to be ready
# ══════════════════════════════════════════════════════════════════════
wait_for_port "$PG_HOST"     "$PG_PORT"     "PostgreSQL" 90
wait_for_port "$MILVUS_HOST" "$MILVUS_PORT" "Milvus"     120

# ══════════════════════════════════════════════════════════════════════
# 5. Create / validate .env
# ══════════════════════════════════════════════════════════════════════
info "Checking .env..."

create_env() {
  info "Creating $ENV_FILE from template..."
  cat > "$ENV_FILE" <<EOF
# ── Database ─────────────────────────────────────────────────────────
DATABASE_URL=postgresql://${PG_USER}:${PG_PASS}@${PG_HOST}:${PG_PORT}/${PG_DB}
POSTGRES_PASSWORD=${PG_PASS}

# ── Milvus ────────────────────────────────────────────────────────────
MILVUS_HOST=${MILVUS_HOST}
MILVUS_PORT=${MILVUS_PORT}

# ── Auth ──────────────────────────────────────────────────────────────
SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")

# ── AI Provider (gemini | claude) ────────────────────────────────────
AI_PROVIDER=gemini
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
GEMINI_MODEL=gemini-2.5-flash
# CLAUDE_API_KEY=YOUR_CLAUDE_API_KEY_HERE
# CLAUDE_MODEL=claude-sonnet-4-6

# ── Cloud Storage ─────────────────────────────────────────────────────
# GCS (recommended)
GCS_BUCKET_NAME=manike-ai-media
GCS_BASE_PREFIX=experience-images
# AWS S3 (alternative)
# S3_BUCKET_NAME=your-bucket
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=

# ── Video Compiler (local | cloudrun) ────────────────────────────────
VIDEO_COMPILER=local
# Set these only when VIDEO_COMPILER=cloudrun:
# CLOUD_RUN_JOB_NAME=projects/<project>/locations/<region>/jobs/manike-video-compiler
# CLOUD_RUN_REGION=us-central1

# ── Royalty-free media ────────────────────────────────────────────────
PEXELS_API_KEY=
PIXABAY_API_KEY=
ENABLE_PEXELS_FALLBACK=false
EOF
  echo ""
  warn "─────────────────────────────────────────────────────────"
  warn " .env created at: $ENV_FILE"
  warn " Edit it now to fill in your API keys before continuing."
  warn "─────────────────────────────────────────────────────────"
  read -r -p "Press ENTER after updating .env to continue (or Ctrl-C to abort)..."
}

if [[ ! -f "$ENV_FILE" ]]; then
  create_env
else
  success ".env already exists — using it"
fi

# Load .env for validation
set -a; source "$ENV_FILE"; set +a

# Validate critical vars
MISSING_VARS=()
[[ -z "${DATABASE_URL:-}"  ]] && MISSING_VARS+=("DATABASE_URL")
[[ -z "${MILVUS_HOST:-}"   ]] && MISSING_VARS+=("MILVUS_HOST")
[[ -z "${AI_PROVIDER:-}"   ]] && MISSING_VARS+=("AI_PROVIDER")

if [[ "${AI_PROVIDER:-}" == "gemini" && ( -z "${GEMINI_API_KEY:-}" || "${GEMINI_API_KEY:-}" == "YOUR_GEMINI_API_KEY_HERE" ) ]]; then
  warn "GEMINI_API_KEY is not set in .env — AI features will fail"
fi
if [[ "${AI_PROVIDER:-}" == "claude" && -z "${CLAUDE_API_KEY:-}" ]]; then
  warn "CLAUDE_API_KEY is not set in .env — AI features will fail"
fi

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
  die "Missing required .env variables: ${MISSING_VARS[*]}"
fi

success ".env validated"

# ══════════════════════════════════════════════════════════════════════
# 6. Python virtual environment + dependencies
# ══════════════════════════════════════════════════════════════════════
VENV_DIR="$REPO_ROOT/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating virtual environment at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi

PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

info "Installing/updating Python dependencies..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r "$REPO_ROOT/requirements.txt"
success "Dependencies installed"

# ══════════════════════════════════════════════════════════════════════
# 7. Database seed
# ══════════════════════════════════════════════════════════════════════
if [[ "$SKIP_SEED" == false ]]; then
  info "Seeding database..."
  (cd "$REPO_ROOT" && "$PYTHON" seed_db.py)
  success "Database seeded"
else
  info "Skipping database seed (--skip-seed)"
fi

# ══════════════════════════════════════════════════════════════════════
# 8. Build Cloud Run worker image locally (if --run-worker)
# ══════════════════════════════════════════════════════════════════════
LOCAL_WORKER_IMAGE="manike-worker:local"

if [[ "$RUN_WORKER" == true ]]; then
  [[ "$DOCKER_AVAILABLE" == true ]] || die "--run-worker requires Docker"

  info "Building local Cloud Run worker image ($LOCAL_WORKER_IMAGE)..."
  docker build \
    --platform linux/amd64 \
    -f "$REPO_ROOT/deploy/cloud-run-job/Dockerfile" \
    -t "$LOCAL_WORKER_IMAGE" \
    "$REPO_ROOT"
  success "Worker image built: $LOCAL_WORKER_IMAGE"
fi

# ══════════════════════════════════════════════════════════════════════
# 9. Start the FastAPI application
# ══════════════════════════════════════════════════════════════════════
UVICORN="$VENV_DIR/bin/uvicorn"

if [[ "$SKIP_APP" == false ]]; then
  info ""
  success "──────────────────────────────────────────────────"
  success " Starting Manike AI backend on http://0.0.0.0:8000"
  success " Swagger UI: http://localhost:8000/docs"
  success "──────────────────────────────────────────────────"

  if [[ "$RUN_WORKER" == true ]]; then
    # Start API in background so we can run the worker afterwards
    info "Starting API server in background..."
    (cd "$REPO_ROOT" && "$UVICORN" app.main:app --host 0.0.0.0 --port 8000 &)
    API_PID=$!
    info "API started (PID $API_PID). Waiting 5s for it to initialise..."
    sleep 5
  else
    # Foreground — this blocks until the user kills it
    (cd "$REPO_ROOT" && exec "$UVICORN" app.main:app --host 0.0.0.0 --port 8000 --reload)
    exit 0
  fi
else
  info "Skipping API start (--skip-app)"
fi

# ══════════════════════════════════════════════════════════════════════
# 10. Run the Cloud Run worker locally (optional)
# ══════════════════════════════════════════════════════════════════════
if [[ "$RUN_WORKER" == true ]]; then
  [[ -n "$WORKER_ITINERARY_ID" ]] || die "--run-worker requires --itinerary-id"
  [[ -n "$WORKER_TENANT_ID"    ]] || die "--run-worker requires --tenant-id"

  CINEMATIC_VAL="false"
  [[ "$WORKER_CINEMATIC" == true ]] && CINEMATIC_VAL="true"

  # Load env values we need to forward to the container
  set -a; source "$ENV_FILE"; set +a

  DB_URL="${DATABASE_URL}"
  # When running in Docker on macOS/Linux, localhost resolves to the host machine
  # Replace localhost / 127.0.0.1 with the Docker host IP so the container can reach it
  if [[ "$PLATFORM" == "macos" ]]; then
    DOCKER_HOST_IP="host.docker.internal"
  else
    # On Linux, use the docker0 bridge IP (typically 172.17.0.1)
    DOCKER_HOST_IP=$(docker network inspect bridge \
      --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null || echo "172.17.0.1")
  fi

  DB_URL=$(echo "$DB_URL"     | sed "s/localhost/$DOCKER_HOST_IP/g" | sed "s/127\.0\.0\.1/$DOCKER_HOST_IP/g")
  MV_HOST=$(echo "$MILVUS_HOST" | sed "s/localhost/$DOCKER_HOST_IP/g" | sed "s/127\.0\.0\.1/$DOCKER_HOST_IP/g")

  info ""
  info "Running Cloud Run worker locally (Docker container)..."
  info "  Image          : $LOCAL_WORKER_IMAGE"
  info "  ITINERARY_ID   : $WORKER_ITINERARY_ID"
  info "  TENANT_ID      : $WORKER_TENANT_ID"
  info "  CINEMATIC      : $CINEMATIC_VAL"
  info "  DATABASE_URL   : $DB_URL"
  info "  MILVUS_HOST    : $MV_HOST"
  info ""

  DOCKER_RUN_ARGS=(
    --rm
    --name manike-worker-local
    -e "DATABASE_URL=$DB_URL"
    -e "MILVUS_HOST=$MV_HOST"
    -e "MILVUS_PORT=${MILVUS_PORT:-19530}"
    -e "GCS_BUCKET_NAME=${GCS_BUCKET_NAME:-manike-ai-media}"
    -e "GCS_BASE_PREFIX=${GCS_BASE_PREFIX:-experience-images}"
    -e "PEXELS_API_KEY=${PEXELS_API_KEY:-}"
    -e "PIXABAY_API_KEY=${PIXABAY_API_KEY:-}"
    -e "ENABLE_PEXELS_FALLBACK=${ENABLE_PEXELS_FALLBACK:-false}"
    -e "ITINERARY_ID=$WORKER_ITINERARY_ID"
    -e "TENANT_ID=$WORKER_TENANT_ID"
    -e "CINEMATIC=$CINEMATIC_VAL"
    -e "TARGET_SECONDS=${TARGET_SECONDS:-45}"
  )

  # Mount GCP application-default credentials if present (for GCS access)
  ADC_PATH="$HOME/.config/gcloud/application_default_credentials.json"
  if [[ -f "$ADC_PATH" ]]; then
    DOCKER_RUN_ARGS+=(
      -v "$ADC_PATH:/tmp/adc.json:ro"
      -e "GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json"
    )
    info "Mounting GCP ADC from $ADC_PATH"
  else
    warn "GCP application-default credentials not found at $ADC_PATH"
    warn "GCS uploads will fail unless GOOGLE_APPLICATION_CREDENTIALS is set another way"
  fi

  # On Linux, add --add-host so container can reach services on the host
  if [[ "$PLATFORM" == "linux" ]]; then
    DOCKER_RUN_ARGS+=(--add-host "host.docker.internal:host-gateway")
  fi

  docker run "${DOCKER_RUN_ARGS[@]}" "$LOCAL_WORKER_IMAGE"
  WORKER_EXIT=$?

  if [[ $WORKER_EXIT -eq 0 ]]; then
    success "Worker completed successfully"
  else
    die "Worker exited with code $WORKER_EXIT"
  fi

  # If we started API in background, remind the user it's still running
  if [[ "${API_PID:-}" != "" ]]; then
    info ""
    info "API server is still running in background (PID $API_PID)."
    info "Press Ctrl-C or run: kill $API_PID  to stop it."
    wait "$API_PID" 2>/dev/null || true
  fi
fi
