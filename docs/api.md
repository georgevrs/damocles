# API reference

REST + WebSocket endpoints exposed by the FastAPI backend at `localhost:8000` (dev) or behind nginx in production. Interactive Swagger UI: **http://localhost:8000/docs**.

## Conventions

- All JSON responses use `application/json` UTF-8.
- Datetimes are ISO 8601 UTC.
- Errors are `{detail: "..."}` with `4xx`/`5xx` status codes (FastAPI defaults).
- Optional fields default to `null`, not omitted.
- IDs are UUIDs (v4 generated, v5 deterministic for source-derived IDs like NewsEvent).

CORS is enabled for `http://localhost:5173` (the Vite dev server). Production will narrow to the deployed origin.

## System

### `GET /health`
Liveness + dependency probe.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",                 // "ok" | "degraded"
  "env": "development",
  "demo_mode": true,
  "neo4j": { "ok": true, "uri": "bolt://localhost:7687" },
  "llm":   { "ok": true, "provider": "gemini", "model": "gemini-3-flash-preview" }
}
```

`status = "degraded"` if either `neo4j.ok` or `llm.ok` is false. The frontend top-bar `SystemBadges` polls this every 30s.

### `GET /`
Service identity (used by health checks and load balancers):
```json
{ "service": "damocles", "version": "0.1.0", "docs": "/docs", "health": "/health" }
```

## Watches

### `GET /api/watches/templates`
Quick-launch chips for the WatchInput component. Returns `WatchTemplate[]`:
```json
[
  { "id": "aegean_maritime", "label": "Aegean Maritime", "query": "Aegean - last 7 days", "icon": "anchor" },
  { "id": "evros_border",    "label": "Evros Border",    "query": "Evros border activity - last 14 days", "icon": "map-pin" },
  { "id": "eastern_med_airspace", "label": "E. Med Airspace", "query": "Eastern Mediterranean airspace - last 72 hours", "icon": "plane" },
  { "id": "info_ops_greece", "label": "Information Ops", "query": "Information operations targeting Greece - last 30 days", "icon": "radio" },
  { "id": "custom",          "label": "Custom Watch",    "query": "", "icon": "search" }
]
```

### `POST /api/watches`
Parse a free-text query, persist the Watch, kick off the pipeline as a background task. **Returns immediately** — the pipeline runs detached; clients track progress via `WS /ws/watches/{id}`.

```bash
curl -X POST http://localhost:8000/api/watches \
  -H "Content-Type: application/json" \
  -d '{"query": "Aegean - last 7 days"}'
```

Request body:
```json
{ "query": "Aegean - last 7 days" }    // free-text
```

Response (`Watch` model):
```json
{
  "id": "0f5f3514-...",
  "raw_query": "Aegean - last 7 days",
  "spec": {
    "region": "aegean",
    "custom_bbox": null,
    "domain": "multi",
    "time_window_days": 7,
    "keywords": ["aegean"],
    "threat_indicators": [],
    "confidence": 1.0,
    "parse_notes": "Region defaults to Aegean for the maritime domain"
  },
  "created_at": "2026-05-02T17:30:00Z",
  "status": "pending",
  "brief_id": null,
  "error": null
}
```

Errors:
- `400 {detail: "query is required"}` — empty query
- `503 {detail: "WatchExecutor not initialized..."}` — backend's LLM/Neo4j unavailable at startup

### `GET /api/watches?limit=20`
List recent watches, newest first. Returns the raw Neo4j Watch nodes (with `created_at` ISO-stringified).

### `GET /api/watches/{watch_id}`
Watch metadata + the most recent progress event from the in-memory broker.
```json
{
  "watch": { "id": "...", "raw_query": "...", "status": "complete", ... },
  "is_done": true,
  "last_event": { "stage": "complete", "status": "complete", "progress_pct": 100, "detail": "..." },
  "event_count": 16
}
```

`is_done` flips true when the broker receives a `stage=complete` event; `event_count` is the number of progress events buffered (default ~5-min retention).

## Briefs

### `GET /api/briefs?watch_id=<watch_id>`
List briefs for a watch, newest first. Returns brief summaries (no sections):
```json
[
  {
    "id": "5da06b56-...",
    "watch_id": "0f5f3514-...",
    "created_at": "2026-05-02T17:30:50Z",
    "metadata": {
      "agents_consulted": ["geospatial_agent", "osint_agent", "devils_advocate", "supervisor"],
      "processing_duration_seconds": 18.4,
      "sources_count": 2,
      "supervisor_metadata": {}
    }
  }
]
```

### `GET /api/briefs/{brief_id}`
Full brief with all sections, ordered BLUF → Key Judgments → Supporting Evidence → Devil's Advocate → Recommendation.

```json
{
  "id": "5da06b56-...",
  "watch_id": "0f5f3514-...",
  "created_at": "2026-05-02T17:30:50Z",
  "metadata": { ... },
  "sections": [
    {
      "id": "...",
      "section_type": "BLUF",
      "text": "A single 80-meter vessel is operating with a disabled AIS transponder...",
      "citation_node_ids": ["323a15c5-...", "20369694-..."],
      "confidence": 0.65,
      "agent_source": "fused",
      "extra": {}
    },
    {
      "section_type": "KEY_JUDGMENT",
      "text": "...",
      "agent_source": "geospatial",
      "confidence": 0.85,
      ...
    },
    ...
    {
      "section_type": "DEVILS_ADVOCATE",
      "text": "Civil unrest is not a maritime threat indicator absent vessel telemetry.",
      "extra": { "devil_confidence": 0.75 },
      ...
    },
    {
      "section_type": "RECOMMENDATION",
      "text": "Downgrade monitoring priority for maritime transit...",
      "extra": { "urgency": "ROUTINE" },
      ...
    }
  ]
}
```

Errors: `404 {detail: "brief {id} not found"}`.

### `GET /api/briefs/{brief_id}/citation/{section_id}` — the gold-medal endpoint
Resolves the BriefSection's CITES edges to source nodes. **This is what fires when the analyst clicks a sentence.**

```json
{
  "section": {
    "id": "...", "section_type": "BLUF", "text": "...", "citation_node_ids": [...], ...
  },
  "source_nodes": [
    {
      "node_id": "323a15c5-...",
      "node_type": "Vessel",
      "cites_via": "Vessel",
      "properties": {
        "id": "...", "lat": 36.502, "lon": 26.974,
        "ais_status": "dark", "mmsi": null, "length_m": 80, "dark_vessel_score": 0.95,
        "sar_tile_id": "1abb28c4-...", "timestamp": "2026-04-25T12:00:00Z", ...
      },
      "raw_evidence": {
        "type": "SAR_TILE",
        "tile_id": "1abb28c4-...",
        "metadata": { "mmsi": null, "vessel_name": null, "ais_status": "dark", "length_m": 80, ... }
      },
      "map_highlight": { "lat": 36.502, "lon": 26.974, "radius_km": 5.0 },
      "graph_highlight": { "node_id": "323a15c5-..." }
    },
    {
      "node_id": "ed0a8157-...",
      "node_type": "NewsEvent",
      "raw_evidence": {
        "type": "ARTICLE_URL",
        "url": "https://lbcgroup.tv/news/...",
        "metadata": { "headline": "...", "goldstein_scale": -6.5, "cameo_code": "141", "language": "en", "mentions": 16 }
      },
      "map_highlight": { "lat": 35.12, "lon": 32.81, "radius_km": 50.0 },
      ...
    }
  ],
  "corroboration_chain": [
    // sibling sources of the same parent CompositeEvent (other-than-cited)
  ],
  "confidence_breakdown": {
    "section_confidence": 0.65,
    "source_count": 2,
    "corroboration_count": 0
  }
}
```

**Side effect:** writes a `brief.citation_accessed` audit entry. Every analyst click is on the chain.

`raw_evidence.type` values:
- `"SAR_TILE"` — `tile_id` resolves to `/static/sar/<tile_id>.png` (the cached SAR PNG with detection bounding box drawn on)
- `"ARTICLE_URL"` — `url` opens in a new tab
- `"TELEGRAM_MESSAGE"` — `content` is the message text rendered inline
- `"COMPOSITE"` — composite-level metadata only

`map_highlight` is `null` if the node has no lat/lon (e.g., a SocialSignal not yet enriched by the Linguist agent).

## Graph

### `GET /api/graph/{watch_id}?limit=1500`
Returns the subgraph for a watch as `{nodes, edges}` shaped for Cytoscape consumption.

```json
{
  "nodes": [
    {
      "id": "watch-id",
      "type": "Watch",
      "label": "Watch",
      "lat": null,
      "lon": null,
      "props": { "id": "...", "raw_query": "...", "region": "aegean", ... }
    },
    {
      "id": "vessel-id",
      "type": "Vessel",
      "label": "...",
      "lat": 36.502,
      "lon": 26.974,
      "props": { ... }
    },
    ...
  ],
  "edges": [
    { "source": "watch-id", "target": "ce-id", "type": "TRIGGERED" },
    { "source": "ce-id",    "target": "vessel-id", "type": "COMPOSED_OF" },
    { "source": "bs-id",    "target": "vessel-id", "type": "CITES" },
    ...
  ]
}
```

Soft-capped at `limit` nodes (default 1500). Edges referencing dropped nodes are filtered out.

The `MapPanel` consumes this same payload to plot vessel/news/composite markers (it filters `nodes` by type), and the `GraphPanel` consumes it for the Cytoscape visualization. TanStack Query dedupes the fetch.

## Audit

### `GET /api/audit?hours_back=24&limit=200`
Recent audit entries + chain verification verdict. The verdict is for the **entire** chain, not the slice — partial-window verification is meaningless (an attacker would just edit entries outside the window).

```json
{
  "entries": [
    {
      "id": "...",
      "timestamp": "2026-05-02T17:30:50Z",
      "action_type": "brief.ingested",
      "actor": "supervisor_agent",
      "payload_hash": "5c217fde...",
      "previous_hash": "f76f1d87...",
      "chain_hash": "b404f323...",
      "chain_valid": true
    },
    ...
  ],
  "count": 41,
  "hours_back": 24,
  "verified": true,
  "chain_total": 41,
  "first_bad_index": null,
  "note": null
}
```

If `verified` is false, `first_bad_index` is the zero-indexed position of the first tampered entry.

### `GET /api/audit/verify`
Run the chain verifier and return a single demo-friendly verdict.

```json
{
  "verified": true,
  "chain_total": 41,
  "first_bad_index": null,
  "verdict": "OK — every chain link rehashes correctly"
}
```

This is what the demo's `[3:30]` script calls live: *"Any parliamentary committee can verify this log has not been tampered with."*

## WebSocket — pipeline progress

### `WS /ws/watches/{watch_id}`
Streams progress events as the pipeline runs. Buffered events arrive first (so a late-joining client catches up), then live events follow until the pipeline emits `stage=complete` or the client disconnects.

Each frame is a JSON object:
```json
{
  "stage": "geospatial_sensor",
  "status": "complete",        // "started" | "progress" | "complete" | "failed" | "skipped"
  "detail": "geospatial: 485 events",
  "progress_pct": 30
}
```

Stages in order (see [pipeline.md](pipeline.md) for the full table):

| stage | progress_pct |
| --- | --- |
| `watch_created` | 5 |
| `sensors` | 10 |
| `geospatial_sensor`, `gdelt_sensor`, `ais_sensor`, `telegram_sensor` | 25-70 |
| `ais_cross_ref` | 75 |
| `graph_ingest` | 78-82 |
| `fusion` | 85-90 |
| `agent_layer` | 90 |
| `brief` | 98 |
| `complete` | 100 |

The connection closes server-side after the `complete` event. Buffered events are retained for ~5 minutes for late joiners.

**JS example:**
```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/watches/${watchId}`);
ws.onmessage = (m) => {
  const event = JSON.parse(m.data);
  console.log(`${event.progress_pct}% ${event.stage} ${event.status} - ${event.detail}`);
  if (event.stage === "complete") ws.close();
};
```

The frontend `ProgressStream` does this idiomatically — see [`frontend/src/components/ProgressStream.tsx`](../frontend/src/components/ProgressStream.tsx).

## Static evidence files

### `GET /static/sar/<tile_id>.png`
Cached SAR tile preview, with red bounding boxes drawn on detected vessels. Mounted via `StaticFiles(directory=settings.cache_dir)` in [`backend/main.py`](../backend/main.py).

```bash
# resolves a Vessel's sar_tile_id field
curl -o tile.png http://localhost:8000/static/sar/1abb28c4-f3fb-4c4d-b... .png
```

The frontend `EvidenceModal` loads these directly via `<img src="/static/sar/...">`. Vite proxies `/static` to the backend in dev.

**Production caveat**: this mount has no auth in dev. Production needs an auth dependency that (a) checks the operator's session, (b) writes a `evidence.served` audit entry, (c) optionally rate-limits per-operator. See [limitations.md §6.12](limitations.md).

## Generated docs

FastAPI auto-generates OpenAPI:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Raw OpenAPI JSON**: http://localhost:8000/openapi.json

The OpenAPI schema is good enough for codegen — drop it into `openapi-typescript` if you want auto-generated TS types, though we keep them hand-written today (see [data-model.md](data-model.md)).

## Calling the API end-to-end

The [`scripts/test_e2e.py`](../scripts/test_e2e.py) script demonstrates the full happy path: POST a watch → stream the WS → poll for the brief → fetch each section's citation chain → verify the audit. 22 assertions in one place. See [testing.md](testing.md).
