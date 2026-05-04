# scripts/download_models.ps1 — pull Ollama models for demo/production
# Run only when switching from Gemini (dev) to Ollama (demo).
# Requires Ollama installed: https://ollama.ai/download/windows

$ErrorActionPreference = "Stop"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "[ERR] Ollama not installed. Download from https://ollama.ai/download/windows" -ForegroundColor Red
    exit 1
}

Write-Host "Pulling Ollama models for Damocles..." -ForegroundColor Cyan
Write-Host "  This will download ~9GB. First-time pull takes 5-15 minutes." -ForegroundColor DarkGray
Write-Host ""

ollama pull llama3.1:8b      # Primary reasoning model (~4.7 GB)
ollama pull qwen2.5:7b       # Devil's Advocate (~4.4 GB)
ollama pull llama3.2:3b      # Fast Watch query parsing (~2.0 GB)

Write-Host ""
Write-Host "Models ready. To switch from Gemini to Ollama:" -ForegroundColor Green
Write-Host "  1. Edit .env: LLM_PROVIDER=ollama" -ForegroundColor White
Write-Host "  2. Restart backend." -ForegroundColor White
