#!/usr/bin/env bash
# =============================================================================
# start.sh — Meridian Sentinel full-stack bootstrap
# =============================================================================
# Run once after cloning to bring the entire stack up and verify it works.
# Subsequent runs restart any stopped services and re-run smoke tests.
#
# Requirements: Docker Desktop 4.x+ running (no local Python needed)
#
# Usage:
#   chmod +x start.sh
#   ./start.sh
# =============================================================================

set -euo pipefail

# Terminal colour helpers
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "\n${GREEN}▶${NC} $1"; }
info() { echo -e "  ${CYAN}→${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "\n${RED}✗ Error:${NC} $1"; exit 1; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }

# =============================================================================
# 1. Pre-flight checks
# =============================================================================
step "Checking prerequisites"

command -v docker >/dev/null 2>&1 \
    || fail "Docker is not installed. Download from https://www.docker.com/products/docker-desktop"

docker info >/dev/null 2>&1 \
    || fail "Docker daemon is not running. Start Docker Desktop and try again."

docker compose version >/dev/null 2>&1 \
    || fail "Docker Compose plugin not found. Update Docker Desktop to 4.x or later."

ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
ok "Docker Compose $(docker compose version --short)"

# =============================================================================
# 2. Bootstrap environment
# =============================================================================
step "Setting up environment"

if [ ! -f .env ]; then
    cp .env.example .env
    ok "Created .env from .env.example (defaults are fine for local development)"
else
    ok ".env already exists — skipping"
fi

# The lstm-serving container writes its ONNX output into this directory.
# Docker will not create it automatically, so it must exist before compose up.
mkdir -p models/serving/lstm_v1
ok "models/serving/lstm_v1/ directory ready"

# Read ELASTIC_PASSWORD from .env for health-check polling below
ELASTIC_PASSWORD=$(grep -E '^ELASTIC_PASSWORD=' .env | cut -d '=' -f2 | tr -d '\r\n')
ELASTIC_PASSWORD="${ELASTIC_PASSWORD:-meridian123}"

# =============================================================================
# 3. Build Docker images
# =============================================================================
step "Building Docker images"
info "First build downloads PyTorch CPU (~550 MB) and dev tools — takes 3–5 minutes."
info "Subsequent builds use the layer cache and are near-instant."

docker compose --profile dev build
ok "Images built"

# =============================================================================
# 4. Start infrastructure services
# =============================================================================
step "Starting services"
docker compose up -d elasticsearch kibana logstash lstm-serving
ok "Containers started in background"

# =============================================================================
# 5. Wait for Elasticsearch
# =============================================================================
step "Waiting for Elasticsearch"
ES_MAX=24   # 24 × 5 s = 120 s maximum wait
for i in $(seq 1 $ES_MAX); do
    if curl -sf -u "elastic:${ELASTIC_PASSWORD}" \
            "http://localhost:9200/_cluster/health" \
            --max-time 5 2>/dev/null | grep -q '"status"'; then
        ok "Elasticsearch is healthy"
        break
    fi
    if [ "$i" -eq "$ES_MAX" ]; then
        fail "Elasticsearch did not become healthy after 120 s.\nDiagnose with: docker compose logs elasticsearch --tail 40"
    fi
    info "Attempt $i/$ES_MAX — retrying in 5 s..."
    sleep 5
done

# =============================================================================
# 6. Wait for LSTM Inference API
# =============================================================================
step "Waiting for LSTM Inference API"
info "First start converts lstm_checkpoint_best.pt → ONNX (~15 s extra)."
LSTM_MAX=36   # 36 × 5 s = 180 s maximum wait
for i in $(seq 1 $LSTM_MAX); do
    if curl -sf "http://localhost:8080/v1/models/lstm" --max-time 5 >/dev/null 2>&1; then
        ok "LSTM API is healthy"
        break
    fi
    if [ "$i" -eq "$LSTM_MAX" ]; then
        fail "LSTM API did not become healthy after 180 s.\nDiagnose with: docker compose logs lstm-serving --tail 40"
    fi
    info "Attempt $i/$LSTM_MAX — retrying in 5 s..."
    sleep 5
done

# =============================================================================
# 7. Run full test suite inside the dev container
# =============================================================================
step "Running test suite inside Docker"
info "SIEM unit tests run immediately. LSTM API tests call http://lstm-serving:8080."

docker compose --profile dev run --rm dev pytest tests/ -v
echo ""
ok "All tests passed"

# =============================================================================
# 8. Print service summary
# =============================================================================
step "Stack is up"
echo ""
echo -e "  ${CYAN}LSTM Inference API${NC}  →  http://localhost:8080/v1/models/lstm"
echo -e "  ${CYAN}Kibana${NC}              →  http://localhost:5601  (elastic / ${ELASTIC_PASSWORD})"
echo -e "  ${CYAN}Elasticsearch${NC}       →  http://localhost:9200"
echo -e "  ${CYAN}Logstash TCP${NC}        →  localhost:5000"
echo ""
echo -e "  Re-run tests:       ${YELLOW}docker compose --profile dev run --rm dev pytest tests/ -v${NC}"
echo -e "  Latency benchmark:  ${YELLOW}docker compose --profile dev run --rm dev python -m src.benchmark${NC}"
echo -e "  Type check:         ${YELLOW}docker compose --profile dev run --rm dev mypy src/${NC}"
echo -e "  Stop the stack:     ${YELLOW}docker compose down${NC}"
echo ""
