# Operations

How to start, debug, and troubleshoot Damocles in development. For production deployment see [deployment.md](deployment.md).

## Quickstart

Three terminals, three commands:

```powershell
# Terminal 1 — Neo4j (Docker Desktop must be running)
docker compose -f docker/neo4j/docker-compose.yml up -d

# Terminal 2 — Backend (FastAPI on :8000)
.\start.ps1 -NoFrontend
# OR manually: uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 3 — Frontend (Vite on :5173)
npm --prefix frontend run dev
```

Then open **http://localhost:5173** in your browser.

The combined `.\start.ps1` (without `-NoFrontend`) attempts to do all three but spawns separate windows; the manual approach gives clearer logs.

## First-time setup

Once per machine:

```powershell
# Tooling
pip install uv
choco install nodejs                       # or download from nodejs.org
# Docker Desktop                           # download from docker.com

# Project deps
uv sync --extra dev                        # backend Python (.venv/)
npm --prefix frontend install              # frontend (~170 packages)

# Configuration
Copy-Item .env.example .env                # then edit .env per docs/credentials.md

# Verify everything connects
uv run python scripts/verify_sources.py
# expect 7/7 sources reachable once .env is filled
```

See [credentials.md](credentials.md) for step-by-step API key acquisition.

## Daily run

```powershell
# Sanity check before starting work
uv run pytest -q                           # ~5s, 140+ tests

# If tests pass, start the dev environment:
docker compose -f docker/neo4j/docker-compose.yml up -d
.\start.ps1 -NoFrontend                    # OR uvicorn directly
npm --prefix frontend run dev
```

When done:
- Frontend: Ctrl+C in the `npm run dev` terminal
- Backend: Ctrl+C in the uvicorn terminal
- Neo4j: leave running (Docker Desktop keeps it suspended-without-cost when idle)

## What's running where

| Process | Port | Purpose |
| --- | --- | --- |
| **Neo4j** | 7474 (browser), 7687 (Bolt) | Graph database. Login: `neo4j` / `CHANGE_ME_neo4j_password` |
| **uvicorn** | 8000 | FastAPI backend, REST + WS |
| **Vite** | 5173 | React dev server with HMR |

`http://localhost:7474` opens the Neo4j Browser — useful for ad-hoc Cypher inspection, debugging citation chains, etc.
`http://localhost:8000/docs` is the auto-generated Swagger UI.

## Probing health

```powershell
# Backend + dependencies
Invoke-RestMethod http://localhost:8000/health | ConvertTo-Json -Depth 4

# All credential connections
uv run python scripts/verify_sources.py

# Audit chain integrity
Invoke-RestMethod http://localhost:8000/api/audit/verify
```

The first two are read-only and free. The third walks the full audit chain (~50ms for ~100 entries).

## Common problems

### `127.0.0.1` connection-refused on Vite
The Vite dev server binds `localhost` (IPv6 `::1`) only on Windows. Use `http://localhost:5173`, not `http://127.0.0.1:5173`. Documented in [limitations.md §6.5](limitations.md).

### Backend "degraded" status, LLM badge red
Most likely cause: `GEMINI_API_KEY` is invalid or quota-exhausted.

```powershell
uv run python -c "from backend.llm.factory import get_provider; import asyncio; print(asyncio.run(get_provider().health_check()))"
```

If False:
1. Check `.env` has a valid `GEMINI_API_KEY`
2. Check the model in `GEMINI_MODEL` is available — the chain `gemini-3-flash-preview,gemini-2.5-flash,gemini-2.0-flash` will auto-fallback on per-day quota errors but not on bad keys
3. Verify the key works at https://aistudio.google.com directly

If you've burned through the daily quota: wait until midnight Pacific or swap to a model with headroom — see [credentials.md §1](credentials.md).

### Backend "degraded" status, Neo4j badge red
Docker Desktop probably isn't running or the container isn't up.

```powershell
docker ps                                  # is damocles-neo4j listed?
docker compose -f docker/neo4j/docker-compose.yml up -d
# wait ~15 s for Neo4j to initialize
Invoke-WebRequest http://localhost:7474 -UseBasicParsing
```

If port 7474 is reachable but Bolt (7687) isn't, Neo4j is still booting. Wait another 5-10 seconds.

### Brief never appears after "Run watch"
Check the WebSocket progress stream (bottom-left panel). What was the last event?

- **Stuck at `geospatial_sensor / started`** → Sentinel Hub is slow or returning empty. Check the Sentinel Hub OAuth token endpoint:
  ```powershell
  Invoke-RestMethod -Method Post `
    -Uri "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token" `
    -Body @{ grant_type="client_credentials"; client_id=$env:SENTINELHUB_CLIENT_ID; client_secret=$env:SENTINELHUB_CLIENT_SECRET }
  ```
  Should return an `access_token`. If 401, your client secret is wrong (or got truncated/whitespace-pasted).

- **Stuck at `gdelt_sensor / started`** → GDELT publish lag. Recent slots (within ~30 minutes) may not yet be downloadable. Wait, or pass a slightly older time window.

- **`telegram_sensor / skipped` is normal** if you haven't run `setup_telegram.py`. The pipeline degrades gracefully.

- **`agent_layer / failed`** → check the audit log for the exact error:
  ```cypher
  MATCH (a:AuditEntry)
  WHERE a.action_type ENDS WITH '.failed' AND a.timestamp >= datetime() - duration('PT15M')
  RETURN a ORDER BY a.timestamp DESC
  ```
  Most likely a Gemini quota error (`429 PerDay...`) or a JSON-parse error. The agent retries once, but a double-failure raises.

### Citation click does nothing
Most likely: the active section has no citations resolvable in the current graph. Check the browser DevTools console for `fetchCitationChain` errors.

If `404 section not found` — the BriefSection isn't in Neo4j. Possibly a stale frontend showing an old brief that was deleted. Refresh the page.

If empty `source_nodes`: the brief's `citation_node_ids` reference nodes that don't exist (e.g., they were on a previous run's seed and the current Neo4j is empty). Run `seed_neo4j.py` again to repopulate.

### "Cannot read properties of undefined" in browser console
Almost always a React Query response shape mismatch. The frontend uses defensive optional chaining everywhere — if you see this on a NEW component, add `?.` between every `.` access on store/query data.

### CFAR returns way too many detections
A 2500×2500 SAR tile of central Aegean produces ~280-500 detections during normal operations. Some are real vessels, some are coastal artifacts, some are azimuth-ambiguity ghosts.

Tune `CFARParams`:
```python
# Higher alpha → fewer false positives (and a few missed dim targets)
CFARParams(alpha=4.5)

# Larger guard ring → handles bigger vessels without leak
CFARParams(guard_cells=6, training_cells=10)

# Stricter min_size → drops single-pixel speckle
CFARParams(min_size_pixels=5)
```

The defaults (`alpha=4.0, guard=4, training=8, min_size=3`) are tuned for Sentinel-1 IW GRD at 10 m/px.

### EvidenceModal SAR image doesn't load
The PNG path is `/static/sar/<sar_tile_id>.png`. The image is cached when `GeospatialSensor.fetch()` runs and writes to `data/cache/sar/`.

Check:
1. Does the file exist? `ls data/cache/sar/<tile_id>.png`
2. Is the backend's `/static` mount up? `Invoke-WebRequest http://localhost:8000/static/sar/<tile_id>.png -UseBasicParsing -Method Head`
3. If Vite proxy is the issue: hit the backend directly (`http://localhost:8000/static/...`) — if that works, the proxy isn't routing correctly, restart Vite.

### Audit chain shows TAMPER but I didn't tamper
Almost always means the JSONL ↔ Neo4j stores have drifted. The "longer-store-wins" logic in `read_chain()` should pick the more complete one, but if Day-13's smoke (JSONL-only) still has entries and Day-14+ has been writing to both, you might be in a state where:

- JSONL has entries 1-5 (Day 13) + 6-20 (Day 14)
- Neo4j has entries 6-20 only (started on Day 14)
- `read_chain()` correctly picks JSONL (longer)

If this STILL fails, the JSONL itself may have been corrupted by a partial write (rare). Reset:

```powershell
# DESTRUCTIVE — clears the audit log entirely. Use with care in dev only.
Remove-Item data\audit_log.jsonl
# Optional: clear Neo4j AuditEntry nodes too
# In Neo4j Browser:  MATCH (a:AuditEntry) DETACH DELETE a
```

The next pipeline run will start a fresh chain from GENESIS.

### Pipeline takes way longer than 60 s
Usual suspects, in order of likelihood:

1. **Gemini rate-limited** — check the audit log for `agent.*.run` entries and their durations. If each call is taking 20+ seconds, the model chain is per-minute throttled. Either wait or switch to a higher-quota model in `GEMINI_MODEL`.
2. **Sentinel Hub slow** — first-tile fetch can take 30-60 s if the tile isn't pre-warmed. Subsequent runs are faster.
3. **AIS capture is fixed at 30 s** — `enable_ais=False` skips it, dropping pipeline time to ~20 s but losing dark-vessel detection.
4. **GDELT downloads on slow connections** — 15-min slot ZIPs are 1-3 MB each; a 24-hour window is ~150 MB.

### Frontend shows blank panels but no errors
Check the Vite dev server log — sometimes a TypeScript error during HMR leaves the page in a half-broken state without a console error. A hard refresh (Ctrl+F5) usually fixes it. If not, restart Vite.

## Resetting the demo state

To clean everything and start fresh:

```powershell
# 1. Wipe Neo4j
docker compose -f docker/neo4j/docker-compose.yml down -v   # -v removes volumes
docker compose -f docker/neo4j/docker-compose.yml up -d

# 2. Clear caches
Remove-Item -Recurse -Force data\cache\*

# 3. Clear audit log
Remove-Item data\audit_log.jsonl -ErrorAction SilentlyContinue

# 4. Re-seed
uv run python scripts/seed_neo4j.py
```

After this you have a clean Watch + Brief + audit chain to demo against.

## Reading logs

### Backend (uvicorn)
Stdout shows everything. The most useful log lines:
```
INFO backend.main — Damocles starting (env=development, llm=gemini, demo=True)
INFO backend.graph.client — Neo4j connected: bolt://localhost:7687
INFO backend.main — LLM provider gemini — health=True, model=gemini-3-flash-preview
INFO backend.audit.logger — MerkleAuditLogger bootstrapped: last_hash=... (jsonl=N entries, neo4j=M entries)
```

If the JSONL count and Neo4j count differ, see "Audit chain shows TAMPER" above.

```
INFO backend.sensors.fusion — Fusion: 599 nodes, 0 edges, 599 composites (RED=0 AMBER=236 GREEN=363)
```

`0 edges` is normal when the fusion timestamps aren't aligned (today's executor uses window-midpoint for SAR). Documented in [limitations.md §3.1](limitations.md). The "edges" count is the number of cross-sensor pairs that scored above `min_corr_score`.

```
INFO google_genai.models — AFC is enabled with max remote calls: 10.
```

This is harmless — Gemini's "Automatic Function Calling" infrastructure log. We don't use FC, but the SDK logs the configuration.

### Frontend (Vite)
HMR updates, type errors, asset reloads. Most useful when troubleshooting the UI directly:
```
8:46:04 PM [vite] hmr update /src/components/MapPanel.tsx
8:46:05 PM [vite] page reload src/components/MapPanel.tsx (no exports)
```

`page reload` happens on changes that can't be hot-replaced (top-level signature changes, etc.) — your browser will refresh automatically.

### Neo4j
`docker logs damocles-neo4j` for container-level logs. The `neo4j.notifications` lines about constraints already existing are harmless (we apply the schema idempotently on every backend startup).

## Helpful Cypher snippets

In Neo4j Browser at http://localhost:7474:

```cypher
// Watches by recency
MATCH (w:Watch) RETURN w ORDER BY w.created_at DESC LIMIT 10

// Latest brief and its sections
MATCH (b:Brief)-[:CONTAINS]->(bs:BriefSection)
RETURN b.id, bs.section_type, bs.text
ORDER BY b.created_at DESC, bs.section_type
LIMIT 20

// Citation chain for a specific section
MATCH (bs:BriefSection {id: $section_id})-[:CITES]->(s)
RETURN labels(s)[0] AS type, s

// All AMBER+ composites for a watch
MATCH (w:Watch {id: $watch_id})-[:TRIGGERED]->(ce:CompositeEvent)
WHERE ce.threat_grade IN ['AMBER', 'RED']
RETURN ce ORDER BY ce.confidence DESC

// Audit chain (Merkle)
MATCH (a:AuditEntry)
WHERE a.timestamp >= datetime() - duration('PT1H')
RETURN a.timestamp, a.action_type, a.actor, a.chain_hash[0..12] AS hash_prefix
ORDER BY a.timestamp DESC

// Wipe everything (DESTRUCTIVE)
MATCH (n) DETACH DELETE n
```

## Updating dependencies

```powershell
# Backend (pyproject.toml)
uv sync --extra dev --upgrade        # respects ranges in pyproject.toml
# OR specific package:
uv add httpx@latest

# Frontend (package.json)
npm --prefix frontend update
# OR specific package:
npm --prefix frontend install maplibre-gl@latest
```

After bumping, run the full unit suite + the e2e regression (`scripts/test_e2e.py`) to confirm nothing regressed.

## Performance debugging

### Slow pipeline?
Read the WebSocket events in the bottom-left panel — the `progress_pct` jumps tell you which stage took how long. Cross-reference with the audit log for hard durations (`duration_ms` in `sensor.*.fetched` payloads).

### Slow page load?
Vite reports bundle sizes after `npm run build`. The MapLibre chunk dominates at ~218 KB gzipped. Code-splitting via dynamic import on first map interaction is the next lever.

### Slow citation click?
The endpoint runs one Cypher query (~10 ms) + the audit log write (~5 ms). The 800 ms most users perceive is the map fly-to animation. Increasing `duration` in `MapPanel.flyTo` slows it intentionally for visual clarity; reducing it makes the demo feel snappier but less impressive.

## Where to look when something's wrong

| Symptom | First place to check |
| --- | --- |
| 500 from any endpoint | Backend stdout — there's a Python traceback |
| Audit chain TAMPER unexpectedly | `data/audit_log.jsonl` row count vs. `MATCH (a:AuditEntry) RETURN count(a)` |
| Brief renders empty | Citations point at nodes that don't exist (run `seed_neo4j.py`) |
| Map markers don't appear | `/api/graph/{watch_id}` returns nodes with null `lat/lon` (sensor-side) |
| Citation click silently fails | Browser DevTools network tab — what status did `/api/briefs/.../citation/...` return? |
| LLM quota exhausted | Backend log shows `429 PerDay...` — wait or swap `GEMINI_MODEL` |

## Where this fits

For development, this doc + [credentials.md](credentials.md) + [testing.md](testing.md) cover everything. Production deployment hardening is in [deployment.md](deployment.md). The full known-limitations ledger is [limitations.md](limitations.md).
