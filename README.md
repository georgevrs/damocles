# Damocles

**Sovereign Intelligence Analysis Platform** — built for the EYP National Security Innovation Challenge 2026.

Damocles fuses Sentinel-1 SAR imagery, AIS vessel tracks, GDELT news events, Telegram signals, and OpenSky flight data into a knowledge graph. A multi-agent reasoning layer (with an adversarial Devil's Advocate) produces intelligence briefs in which **every sentence traces to its source**. A Merkle-chained audit log makes every model call tamper-evident.

The full design lives in [`.prompts/PLAN.md`](.prompts/PLAN.md). Companion docs:
- [`docs/credentials.md`](docs/credentials.md) — step-by-step instructions for obtaining every API key and credential.
- [`docs/limitations.md`](docs/limitations.md) — candid ledger of known limitations, workarounds, and engineering debt, organized by component with severity tags.

## Quickstart — Windows

```powershell
# One-time setup
.\scripts\setup_windows.ps1

# Edit .env and add your GEMINI_API_KEY (free at https://aistudio.google.com)

# Start Neo4j + backend + frontend
.\start.ps1 -Seed

# Open http://localhost:5173
```

## Quickstart — Linux / GCP

```bash
./scripts/setup_linux.sh
# edit .env
./start.sh --seed
```

## LLM provider — one env var, two backends

`LLM_PROVIDER=gemini` (development) or `LLM_PROVIDER=ollama` (demo / production). Switching requires zero code changes — the entire agent layer goes through `backend.llm.LLMProvider`.

| | Gemini (dev) | Ollama (demo / prod) |
| --- | --- | --- |
| Cost | free tier sufficient | zero (local) |
| Hardware | none | 8 GB VRAM, 16 GB RAM |
| Sovereignty | dev only | full — no external calls |
| Latency | ~500 ms | ~3-5 s on consumer GPU |

## Verify the install

```powershell
uv run python scripts/verify_sources.py
```

This pings the LLM, Neo4j, Sentinel Hub, GDELT, OpenSky, AISStream, and Telegram credentials, and prints a status table.

## Repository layout

```
backend/
  llm/             provider abstraction (base · gemini · ollama · factory)
  models/          Pydantic shapes for Watch · Event · Brief · Audit
  graph/           Neo4j schema · client · queries · ingestion
  watch_engine/    NL query parser · template registry · pipeline executor
  sensors/         (Week 1) Sentinel-1 · AIS · GDELT · Telegram · OpenSky · fusion
  agents/          (Week 2) geospatial · OSINT · linguist · devil's advocate · supervisor
  audit/           Merkle-chained audit log
  api/             FastAPI routers + WebSocket progress stream
frontend/          React + Vite + Leaflet + Cytoscape (three-panel UI)
docker/neo4j/      Neo4j 5.24 docker-compose (dev convenience)
scripts/           setup · verify_sources · seed_neo4j · download_models
data/              GeoJSON regions and pre-seeded demo scenario
```

## The three-week build

- **Week 1** — sensors → fusion → graph (`scripts/seed_neo4j.py` populates the demo)
- **Week 2** — agents → audit → API (full citation chain end-to-end)
- **Week 3** — frontend → demo polish (citation click in <200 ms)

## The demo moment

A judge clicks any sentence in the brief → the map flies to the source location, the graph highlights the source nodes, the evidence modal opens with the raw SAR tile / news article / Telegram message. **No competitor will have this.** Implementation lives across `backend/api/briefs.py` (citation chain endpoint) and `frontend/src/components/BriefPanel.tsx` (CitableText).

---

*Build target: gold medal at the June 2026 EYP final pitch.*
