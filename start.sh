#!/usr/bin/env bash
# start.sh — Damocles Linux/GCP startup
# Usage: ./start.sh [--seed]

set -euo pipefail

echo ""
echo " Damocles — Sovereign Intelligence Analysis Platform"
echo ""

# Load .env
if [[ -f .env ]]; then
    set -a; source .env; set +a
else
    echo "[WARN] .env not found. Copy .env.example to .env and fill in API keys."
fi

# Dep checks
command -v docker >/dev/null 2>&1 || { echo "[ERR] docker not found. Run: scripts/setup_linux.sh"; exit 1; }
command -v uv     >/dev/null 2>&1 || { echo "[ERR] uv not found. Run: pip install uv"; exit 1; }

# Start Neo4j
echo "[1/4] Starting Neo4j..."
docker compose -f docker/neo4j/docker-compose.yml up -d

# Wait for Neo4j HTTP
echo "       Waiting for Neo4j..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:7474 > /dev/null; then break; fi
    sleep 2
done
echo "       Neo4j ready."

# Sync deps
echo "[2/4] Syncing Python dependencies..."
uv sync

# Optional seed
if [[ "${1:-}" == "--seed" ]]; then
    echo "[3/4] Seeding demo scenario (March 2024 Aegean)..."
    uv run python scripts/seed_neo4j.py
else
    echo "[3/4] Skipping seed (use --seed to load demo data)"
fi

# Backend + frontend
echo "[4/4] Starting backend + frontend..."
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

if [[ "${DAMOCLES_ENV:-development}" == "production" ]]; then
    pushd frontend > /dev/null
    [[ -d node_modules ]] || npm install
    npm run build
    popd > /dev/null
    # Nginx serves the static build — see scripts/setup_linux.sh
else
    pushd frontend > /dev/null
    [[ -d node_modules ]] || npm install
    npm run dev &
    FRONTEND_PID=$!
    popd > /dev/null
fi

echo ""
echo " Damocles is running."
echo "  Frontend:  http://localhost:5173"
echo "  API:       http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
echo "  Neo4j:     http://localhost:7474"
echo ""
echo "  LLM Provider: ${LLM_PROVIDER:-not set}"
echo "  Demo Mode:    ${DEMO_MODE:-not set}"
echo ""

# Forward signals to children
trap "kill $BACKEND_PID ${FRONTEND_PID:-} 2>/dev/null || true" INT TERM
wait
