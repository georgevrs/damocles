#!/usr/bin/env bash
# scripts/download_models.sh — pull Ollama models for demo/production

set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
    echo "[ERR] Ollama not installed. Run scripts/setup_linux.sh first."
    exit 1
fi

echo "Pulling Ollama models for Damocles..."
echo "  This will download ~9GB. First-time pull takes 5-15 minutes."
echo ""

ollama pull llama3.1:8b
ollama pull qwen2.5:7b
ollama pull llama3.2:3b

echo ""
echo "Models ready. To switch from Gemini to Ollama:"
echo "  1. Edit .env: LLM_PROVIDER=ollama"
echo "  2. Restart backend."
