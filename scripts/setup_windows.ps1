# scripts/setup_windows.ps1 — one-time Windows dev environment setup
# Usage: .\scripts\setup_windows.ps1

$ErrorActionPreference = "Stop"

Write-Host "Setting up Damocles development environment on Windows..." -ForegroundColor Cyan
Write-Host ""

# uv (Python package manager)
Write-Host "[1/6] Checking uv..." -ForegroundColor Yellow
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "       Installing uv via pip..." -ForegroundColor DarkGray
    pip install uv
} else {
    Write-Host "       uv found: $(uv --version)" -ForegroundColor Green
}

# Node.js
Write-Host "[2/6] Checking Node.js..." -ForegroundColor Yellow
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "       [MANUAL] Install Node.js LTS (v20+) from https://nodejs.org" -ForegroundColor Red
} else {
    Write-Host "       Node.js found: $(node --version)" -ForegroundColor Green
}

# Docker Desktop
Write-Host "[3/6] Checking Docker..." -ForegroundColor Yellow
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "       [MANUAL] Install Docker Desktop from https://docker.com" -ForegroundColor Red
} else {
    Write-Host "       Docker found: $(docker --version)" -ForegroundColor Green
}

# .env
Write-Host "[4/6] Checking .env..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "       .env created from .env.example. Fill in your GEMINI_API_KEY." -ForegroundColor Yellow
} else {
    Write-Host "       .env already present." -ForegroundColor Green
}

# Pull Neo4j image
Write-Host "[5/6] Pulling Neo4j image..." -ForegroundColor Yellow
docker pull neo4j:5.24-community

# Python deps + spaCy
Write-Host "[6/6] Installing Python dependencies (uv sync)..." -ForegroundColor Yellow
uv sync

Write-Host "       Downloading spaCy Greek model..." -ForegroundColor DarkGray
uv run python -m spacy download el_core_news_lg

Write-Host ""
Write-Host "Setup complete. Next steps:" -ForegroundColor Green
Write-Host "  1. Edit .env and add GEMINI_API_KEY (free at aistudio.google.com)" -ForegroundColor White
Write-Host "  2. Run: .\start.ps1 -Seed" -ForegroundColor White
Write-Host "  3. Open: http://localhost:5173" -ForegroundColor White
Write-Host ""
