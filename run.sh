#!/usr/bin/env bash
set -e

# ─────────────────────────────────────────────────────────────────────────────
# Manike Backend — one-command setup & run
#
# Usage:
#   ./run.sh              # first run: creates venv, installs deps, starts server
#   ./run.sh --reset      # wipe venv & .env, start fresh
#   ./run.sh --skip-db    # skip DB seed (useful after first run)
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
ENV_FILE=".env"
PYTHON="${VENV_DIR}/bin/python3"
PIP="${VENV_DIR}/bin/pip"

RESET=false
SKIP_DB=false
for arg in "$@"; do
  case "$arg" in
    --reset)   RESET=true ;;
    --skip-db) SKIP_DB=true ;;
  esac
done

# ─── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}▸ $1${NC}"; }
ok()   { echo -e "  ${GREEN}✔ $1${NC}"; }
warn() { echo -e "  ${YELLOW}⚠ $1${NC}"; }
err()  { echo -e "  ${RED}✖ $1${NC}"; }

# ─── Reset mode ───────────────────────────────────────────────────────────────
if $RESET; then
  step "Resetting environment"
  rm -rf "$VENV_DIR"
  rm -f "$ENV_FILE"
  ok "Cleaned venv and .env"
fi

# ─── Check Python 3 ──────────────────────────────────────────────────────────
step "Checking Python 3"
if ! command -v python3 &>/dev/null; then
  err "python3 not found. Install Python 3.10+ first."
  exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "Found Python ${PY_VERSION}"

# ─── Create virtual environment ──────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
  step "Creating virtual environment"
  python3 -m venv "$VENV_DIR"
  ok "Created ${VENV_DIR}/"
else
  ok "Virtual environment exists"
fi

# ─── Install dependencies ────────────────────────────────────────────────────
step "Installing dependencies"
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r requirements.txt
ok "All packages installed"

# ─── Create .env if missing ──────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  step "Creating .env file (edit with your real values)"
  cat > "$ENV_FILE" <<'DOTENV'
# ─── Database (PostgreSQL) ────────────────────────────────────────────────────
# Replace with your actual PostgreSQL connection string
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/manike

# ─── Milvus (Vector DB) ──────────────────────────────────────────────────────
MILVUS_HOST=localhost
MILVUS_PORT=19530

# ─── AI Provider (pick one: gemini or claude) ────────────────────────────────
AI_PROVIDER=gemini

# Gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# Claude (uncomment and set AI_PROVIDER=claude to use)
# CLAUDE_API_KEY=your_claude_api_key_here
# CLAUDE_MODEL=claude-sonnet-4-6

# ─── AWS S3 (for video/image uploads) ────────────────────────────────────────
# S3_BUCKET_NAME=your-bucket
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=your_key
# AWS_SECRET_ACCESS_KEY=your_secret

# ─── HeyGen LiveAvatar (optional) ────────────────────────────────────────────
# HEYGEN_API_KEY=your_heygen_api_key_here
# HEYGEN_AVATAR_ID=
# HEYGEN_VOICE_ID=
DOTENV
  warn ".env created with placeholder values — edit it before running!"
  echo ""
  echo -e "${YELLOW}  Open the file:${NC}"
  echo -e "    ${CYAN}nano ${SCRIPT_DIR}/${ENV_FILE}${NC}"
  echo ""
  echo -e "  ${YELLOW}At minimum, set:${NC}"
  echo "    1. DATABASE_URL  (PostgreSQL connection string)"
  echo "    2. GEMINI_API_KEY or CLAUDE_API_KEY"
  echo ""
  read -rp "  Press Enter after editing .env (or Ctrl+C to abort)... "
fi

# ─── Validate critical env vars ──────────────────────────────────────────────
step "Validating environment"
set -a; source "$ENV_FILE"; set +a

ERRORS=0

if [ -z "$DATABASE_URL" ]; then
  err "DATABASE_URL is not set in .env"; ERRORS=1
fi

PROVIDER="${AI_PROVIDER:-gemini}"
if [ "$PROVIDER" = "gemini" ]; then
  if [ -z "$GEMINI_API_KEY" ] || [ "$GEMINI_API_KEY" = "your_gemini_api_key_here" ]; then
    err "GEMINI_API_KEY is not set (AI_PROVIDER=gemini)"; ERRORS=1
  else
    ok "AI Provider: Gemini (${GEMINI_MODEL:-gemini-2.0-flash})"
  fi
elif [ "$PROVIDER" = "claude" ]; then
  if [ -z "$CLAUDE_API_KEY" ] || [ "$CLAUDE_API_KEY" = "your_claude_api_key_here" ]; then
    err "CLAUDE_API_KEY is not set (AI_PROVIDER=claude)"; ERRORS=1
  else
    ok "AI Provider: Claude (${CLAUDE_MODEL:-claude-sonnet-4-6})"
  fi
else
  err "Unknown AI_PROVIDER '${PROVIDER}'. Use 'gemini' or 'claude'."; ERRORS=1
fi

if [ "$ERRORS" -ne 0 ]; then
  echo ""
  err "Fix the errors above in .env and re-run ./run.sh"
  exit 1
fi

# ─── Check external services ─────────────────────────────────────────────────
step "Checking external services"

# PostgreSQL
DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_PORT="${DB_PORT:-5432}"
if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
  ok "PostgreSQL reachable at ${DB_HOST}:${DB_PORT}"
else
  warn "PostgreSQL not reachable at ${DB_HOST}:${DB_PORT} — server may fail to start"
fi

# Milvus
M_HOST="${MILVUS_HOST:-localhost}"
M_PORT="${MILVUS_PORT:-19530}"
if nc -z "$M_HOST" "$M_PORT" 2>/dev/null; then
  ok "Milvus reachable at ${M_HOST}:${M_PORT}"
else
  warn "Milvus not reachable at ${M_HOST}:${M_PORT} — vector features will be unavailable"
fi

# ─── Seed database ───────────────────────────────────────────────────────────
if ! $SKIP_DB; then
  step "Seeding database"
  "$PYTHON" seed_db.py && ok "Database seeded" || warn "Seed failed (DB might not be ready)"
fi

# ─── Start server ────────────────────────────────────────────────────────────
step "Starting Manike Backend on http://localhost:8000"
echo -e "  Swagger UI: ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop"
echo ""

exec "$PYTHON" app/main.py
