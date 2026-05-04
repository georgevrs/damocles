# start.ps1 — Damocles Windows development startup
# Usage: .\start.ps1 [-Seed]

param(
    [switch]$Seed,
    [switch]$NoFrontend
)

$ErrorActionPreference = "Stop"

# Force UTF-8 everywhere so Greek text and Rich's box-drawing characters render
# correctly in PowerShell (default Windows console is cp1252).
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "  ____                                 _" -ForegroundColor Cyan
Write-Host " |  _ \  __ _ _ __ ___   ___   ___| | ___  ___" -ForegroundColor Cyan
Write-Host " | | | |/ _\` | '_ \` _ \ / _ \ / __| |/ _ \/ __|" -ForegroundColor Cyan
Write-Host " | |_| | (_| | | | | | | (_) | (__| |  __/\__ \" -ForegroundColor Cyan
Write-Host " |____/ \__,_|_| |_| |_|\___/ \___|_|\___||___/" -ForegroundColor Cyan
Write-Host ""
Write-Host " Sovereign Intelligence Analysis Platform" -ForegroundColor White
Write-Host ""

# Load .env if present
if (Test-Path ".env") {
    Get-Content ".env" | Where-Object { $_ -match "^[A-Z_]+=.*$" -and $_ -notmatch "^\s*#" } | ForEach-Object {
        $name, $value = $_ -split "=", 2
        Set-Item "env:$name" $value
    }
} else {
    Write-Host "[WARN] .env not found. Copy .env.example to .env and fill in API keys." -ForegroundColor Yellow
}

# Check Docker is running
Write-Host "[1/5] Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
} catch {
    Write-Host "[ERR] Docker Desktop is not running. Start Docker Desktop and retry." -ForegroundColor Red
    exit 1
}

# Start Neo4j
Write-Host "[2/5] Starting Neo4j..." -ForegroundColor Yellow
docker compose -f docker/neo4j/docker-compose.yml up -d

# Wait for Neo4j HTTP to respond
Write-Host "       Waiting for Neo4j to be ready..." -ForegroundColor DarkGray
$maxWait = 60
$waited = 0
$ready = $false
do {
    Start-Sleep -Seconds 2
    $waited += 2
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:7474" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
} while ($waited -lt $maxWait)
if (-not $ready) {
    Write-Host "[ERR] Neo4j did not become ready within $maxWait seconds." -ForegroundColor Red
    exit 1
}
Write-Host "       Neo4j ready at http://localhost:7474" -ForegroundColor Green

# Sync Python deps
Write-Host "[3/5] Syncing Python dependencies (uv)..." -ForegroundColor Yellow
uv sync

# Optional: seed demo scenario
if ($Seed) {
    Write-Host "[4/5] Seeding demo scenario (March 2024 Aegean)..." -ForegroundColor Yellow
    uv run python scripts/seed_neo4j.py
} else {
    Write-Host "[4/5] Skipping seed (use -Seed to load demo data)" -ForegroundColor DarkGray
}

# Start backend in a new window
Write-Host "[5/5] Starting backend + frontend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

if (-not $NoFrontend) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location frontend; if (-not (Test-Path node_modules)) { npm install }; npm run dev"
}

Write-Host ""
Write-Host "Damocles is running." -ForegroundColor Green
Write-Host "  Frontend:  http://localhost:5173" -ForegroundColor White
Write-Host "  API:       http://localhost:8000" -ForegroundColor White
Write-Host "  API docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Neo4j:     http://localhost:7474" -ForegroundColor White
Write-Host ""
Write-Host "  LLM Provider: $env:LLM_PROVIDER" -ForegroundColor Magenta
Write-Host "  Demo Mode:    $env:DEMO_MODE" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Primary demo query: 'Aegean — last 7 days'" -ForegroundColor Cyan
Write-Host ""
