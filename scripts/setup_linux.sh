#!/usr/bin/env bash
# scripts/setup_linux.sh — one-time GCP/Linux setup
# Tested on Debian 12 / Ubuntu 22.04 LTS

set -euo pipefail

echo "Setting up Damocles on Linux..."

# System packages
sudo apt-get update
sudo apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    build-essential curl git \
    libgdal-dev gdal-bin \
    nginx

# Docker (for Neo4j)
if ! command -v docker >/dev/null 2>&1; then
    echo "[1/5] Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo "       Re-login or run: newgrp docker"
fi

# Node.js
if ! command -v node >/dev/null 2>&1; then
    echo "[2/5] Installing Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# uv
if ! command -v uv >/dev/null 2>&1; then
    echo "[3/5] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Ollama (for local LLM in production)
if ! command -v ollama >/dev/null 2>&1; then
    echo "[4/5] Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# .env
if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "[5/5] .env created from .env.example. Fill in API keys."
fi

# Sync deps + spaCy
uv sync
uv run python -m spacy download el_core_news_lg

echo ""
echo "Setup complete. Next steps:"
echo "  1. Edit .env"
echo "  2. (Production) Pull Ollama models:  ./scripts/download_models.sh"
echo "  3. Run: ./start.sh --seed"
