# Pipeline

The orchestration layer that turns a free-text query into a Brief with cited claims. Owned by [`backend/watch_engine/executor.py`](../backend/watch_engine/executor.py).

## Stages

```
┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
│ 1. parse   │→ │ 2. sensors │→ │ 3. fusion  │→ │ 4. agents  │→ │ 5. brief   │
│    query   │  │  (parallel)│  │    +ingest │  │  (4 LLMs)  │  │   ingest   │
└────────────┘  └────────────┘  └────────────┘  └────────────┘  └────────────┘
   ~1s              ~30s            ~3s            ~15s            ~1s
```

Total ~50-65 seconds end-to-end, comfortably inside the demo's 60-second budget.

Every stage emits a progress event over the WebSocket and writes an `AuditEntry` to the Merkle chain. The frontend `ProgressStream` shows them live.

## Stage 1 — Parse query

**Input:** raw free-text query (`"Aegean — last 7 days"`)
**Output:** `Watch` with structured `WatchSpec`
**LLM cost:** 1 call (parse + json_mode)
**Code:** [`backend/watch_engine/parser.py`](../backend/watch_engine/parser.py)

The parser uses the LLM with `json_mode=True` and a strict schema. Examples it handles:

| Input | Parsed `WatchSpec` |
| --- | --- |
| `"Aegean — last 7 days"` | `region=aegean, domain=multi, time_window_days=7` |
| `"Turkish military activity near Rhodes last 2 weeks"` | `region=aegean, domain=maritime, keywords=["turkish","military","rhodes"], time_window_days=14` |
| `"Coordinated social media campaigns about Cyprus"` | `region=eastern_med, domain=information, keywords=["cyprus","social","coordinated"]` |
| `"Maritime incidents Eastern Mediterranean Q1 2024"` | `region=eastern_med, domain=maritime, time_window_days=90` |

**Retry on JSON failure:** if the model returns invalid JSON, the parser retries once with the bad output + error message in the correction prompt. This is the same retry pattern every agent uses.

After parsing, `Watch` is ingested into Neo4j as a `(:Watch)` node and the audit log records `watch.created`.

## Stage 2 — Sensor fan-out

**Input:** `WatchSpec.bbox`, `time_window_days`
**Output:** lists of `Vessel`, `NewsEvent`, `SocialSignal`, `AirspaceEvent`
**Concurrency:** all sensors run in parallel via `asyncio.gather`
**Code:** `WatchExecutor._run_geospatial`, `_run_gdelt`, `_run_ais`, `_run_telegram`

Each sensor is wrapped in try/except. A sensor failure logs a warning, emits a `stage=*_failed` WebSocket event, audit-logs `sensor.{name}.failed`, and the pipeline continues with the survivors. This is deliberate — a transient AISStream disconnect or a Sentinel Hub quota error should degrade the brief, not kill it.

Sensor-specific behavior:

| Sensor | What it does | Free-tier ceiling | Failure mode |
| --- | --- | --- | --- |
| **Geospatial** ([sensors/geospatial.py](../backend/sensors/geospatial.py)) | Sentinel-1 IW VV+VH GRD tile → CFAR detection → `Vessel[]` | 30k PU/month, ~5-10 PU per tile | Quota / no scenes → empty list |
| **GDELT** ([sensors/gdelt.py](../backend/sensors/gdelt.py)) | Last-N-hours master file → ZIP/TSV stream → `NewsEvent[]` | unlimited public CSVs | 404s on individual slots are tolerated |
| **AIS** ([sensors/ais.py](../backend/sensors/ais.py)) | AISStream WebSocket capture for ~30s → `AISRecord[]` (raw, not yet `Vessel`) | 1 connection, ~1k msg/min | WS disconnect → return what we have |
| **Telegram** ([sensors/telegram_sensor.py](../backend/sensors/telegram_sensor.py)) | Telethon iter_messages over public channels → `SocialSignal[]` | per-app rate limits | No session → `RuntimeError` caught, logged, sensor skipped |

See [sensors.md](sensors.md) for protocol-level detail on each.

### AIS cross-reference

After the geospatial + AIS sensors return, the dark-vessel cross-reference runs:

```python
vessels = cross_reference(sar_vessels, ais_records, config)
```

For each SAR detection:
1. Find AIS broadcasts within `±30 min` and `≤2 km` (haversine)
2. If found → mark `BROADCASTING`, copy MMSI/name/flag, set `ais_match_distance_km`
3. If none → mark `DARK`, compute `dark_vessel_score`:
   - Base 0.7
   - +0.1 if length > 100m
   - +0.1 if in a contested zone (e.g., eastern Aegean median line)
   - +0.1 if 00:00-06:00 UTC (nighttime evasion pattern)

Cap at 1.0. The score is what the frontend renders as "85% dark" in the EvidenceModal.

See [`backend/sensors/dark_vessel.py`](../backend/sensors/dark_vessel.py) and the 13 unit tests in [`tests/test_dark_vessel.py`](../tests/test_dark_vessel.py).

## Stage 3 — Fusion + graph ingest

**Input:** lists of `Vessel`, `NewsEvent`, `SocialSignal`, `AirspaceEvent`
**Output:** `CompositeEvent[]` linking corroborated sensor events
**Code:** [`backend/sensors/fusion.py`](../backend/sensors/fusion.py)

The fusion engine creates a spatiotemporal "bubble" around each event. Pairs from *different sensors* with overlapping bubbles get a correlation score; pairs above `min_corr_score` (default 0.5) form clusters.

**Bubble sizes** (defaults from the plan):

| Sensor | Spatial radius | Temporal window |
| --- | --- | --- |
| Geospatial (SAR) | 5 km | ±2 h |
| GDELT (news) | 50 km | ±12 h |
| Telegram | 100 km | ±24 h |
| OpenSky (airspace) | 10 km | ±1 h |

The looser tolerances on GDELT and Telegram reflect their inherently imprecise geocoding — a Reuters article tagged "Aegean" might have lat/lon at Athens even when the actual incident is 200 km away.

**Correlation score**:
```
spatial_score  = 1 - (distance_km / max_radius)
temporal_score = 1 - (time_diff_h / max_window)
corr_score     = 0.6 * spatial_score + 0.4 * temporal_score
```

Pairs above threshold form connected components via union-find. Each component becomes a `CompositeEvent` with:
- `source_node_ids` — every constituent sensor event
- `corroboration_count` — distinct sensors in the component
- `confidence` — weighted blend (boosted by multi-sensor presence)
- `centroid_lat/lon` — average of constituent positions
- `threat_grade` — GREEN / AMBER / RED per the rules in [data-model.md](data-model.md)

Then ingestion: sensor events first (so they exist before composites reference them), then composites with `(Watch)-[:TRIGGERED]->(CompositeEvent)-[:COMPOSED_OF]->(source)`. Audit log records `fusion.complete` with the stats.

### Why every sensor event becomes a composite, even singletons

The fusion engine emits one composite per *connected component*. A sensor event with no cross-sensor matches becomes a single-member component → still a composite, marked GREEN. This means:

- Every sensor event is reachable from a CompositeEvent → uniform downstream code
- The agent layer always has a CompositeEvent to reason over, even when fusion didn't fuse much
- Cost: graph noise. A 645-event Watch produces 645 composites if 0 cross-sensor edges materialize. The frontend filters to AMBER/RED for display.

See [limitations.md §5.1](limitations.md#51-every-solo-sensor-event-becomes-a-single-member-compositeevent--debt) for the planned fix.

## Stage 4 — Agent layer

**Input:** the top composite (`_pick_top_composite`)
**Output:** `Brief` Pydantic
**LLM cost:** 4 calls (Geo, OSINT, Devil, Supervisor) — each may retry once on validation failure
**Code:** `WatchExecutor._run_agent_layer`

### Composite selection

Today's executor runs the agents on **one composite per watch** — the highest-priority one:

```python
def _pick_top_composite(composites):
    def rank(ce):
        grade_score = {"RED": 2, "AMBER": 1, "GREEN": 0}[ce.threat_grade.value]
        return (grade_score, ce.corroboration_count, ce.confidence)
    return max(composites, key=rank)
```

Multi-composite aggregation (the "watch-level supervisor" pattern) is documented as future work. See [limitations.md §5b.8](limitations.md).

### Agent execution order

```python
# 1. Primaries run concurrently
geo_task   = asyncio.create_task(GeospatialAgent(...).run(composite_id))
osint_task = asyncio.create_task(OSINTAgent(...).run(composite_id))
results    = await asyncio.gather(geo_task, osint_task, return_exceptions=True)

# 2. Devil's Advocate runs on the primaries' outputs
devil_out  = await DevilsAdvocateAgent(...).run(
    composite_event_id=composite_id,
    prior_outputs=[(name, out) for ...],
)

# 3. Supervisor synthesizes
brief = await run_supervisor_and_assemble(
    agent=SupervisorAgent(...),
    composite_event_id=composite_id,
    watch_id=watch.id,
    prior_outputs=[("geospatial_agent", geo), ("osint_agent", osint), ("devils_advocate", devil)],
    sources_count=...,
)
```

Each agent run produces an audit entry:
- `agent.{name}.run` (success) — payload includes confidence, finding_count, model name
- `agent.{name}.failed` (exception) — payload includes the error message

See [agents.md](agents.md) for the prompt + schema design of each agent.

## Stage 5 — Brief ingestion

**Input:** `Brief` Pydantic
**Output:** persisted graph nodes + edges
**Code:** [`backend/graph/ingestion.py`](../backend/graph/ingestion.py) `ingest_brief()`

Cypher writes (in order):

```cypher
// 1. Brief node
MERGE (b:Brief {id: $id}) SET b.watch_id = $watch_id, ...

// 2. Watch -> Brief edge
MATCH (w:Watch {id: $watch_id})
MERGE (w)-[:PRODUCED]->(b)

// 3. Each BriefSection
MERGE (bs:BriefSection {id: $id}) SET bs.section_type = ..., bs.text = ..., ...

// 4. Brief -> BriefSection edge
MERGE (b)-[:CONTAINS]->(bs)

// 5. The gold-medal CITES edges
MATCH (bs:BriefSection {id: $section_id})
MATCH (s {id: $source_id})
MERGE (bs)-[r:CITES]->(s)
SET r.node_type = labels(s)[0]
```

The CITES edges are what the citation chain endpoint walks at click time. Once they exist in Neo4j, the demo's gold-medal moment is fully wired.

Audit log records `brief.ingested` with section count, agents consulted, and BLUF confidence.

## Progress events (the WebSocket protocol)

The executor yields events in this order. The frontend `ProgressStream` renders them live.

| stage | status | progress_pct | What it means |
| --- | --- | --- | --- |
| `watch_created` | complete | 5 | Watch ingested, ID minted |
| `sensors` | started | 10 | Concurrent fan-out begins |
| `geospatial_sensor` | complete \| failed | ~25 | SAR fetch + CFAR done |
| `gdelt_sensor` | complete \| failed | ~40 | News slots fetched + filtered |
| `ais_sensor` | complete \| failed | ~55 | WS capture finished |
| `telegram_sensor` | complete \| skipped \| failed | ~70 | Channels iterated |
| `ais_cross_ref` | complete | 75 | Dark vessels marked |
| `graph_ingest` | started → complete | 78 → 82 | Sensor events written |
| `fusion` | started → complete | 85 → 90 | Composites assembled |
| `graph_ingest` | complete | 95 | Composites linked to watch |
| `agent_layer` | started → complete \| failed | 90 → 98 | All 4 agents ran |
| `brief` | complete | 98 | Brief ingested with CITES edges |
| `complete` | complete | 100 | Pipeline finished |

The WS connection closes after `complete`. Late-joining clients replay buffered events from the broker (limit ~5 minutes of retention).

## Failure handling

The pipeline degrades gracefully at every stage:

- **Sensor failure** → continues with survivors, logged as `*_failed` event + audit entry. Brief still produced if at least one sensor returned data.
- **Agent validation failure** → retry once with correction prompt embedded. Second failure raises and the agent layer aborts (but graph is still in a consistent state).
- **Graph write failure** → propagates up; the WebSocket gets a `pipeline / failed` event then `complete / failed` so subscribers exit cleanly.
- **No composites at all** → emits `agent_layer / skipped` and finishes with no Brief. The frontend shows the existing graph data + an empty brief panel.

The WebSocket always closes via a `complete` event, even on failure. Subscribers never block forever.

## End-to-end timing budget

From the e2e test on a typical Aegean watch:

| Phase | Wall-clock | Notes |
| --- | --- | --- |
| Parse query | ~0.5 s | Single Gemini call, json_mode |
| Sensor fan-out (parallel) | ~30 s | Dominated by AIS 30s capture |
| AIS cross-reference | ~0.05 s | In-memory haversine match |
| Graph ingest (sensors) | ~1 s | Bulk Cypher |
| Fusion | ~0.1 s | Pure Python, ~600 nodes |
| Graph ingest (composites) | ~2 s | One Cypher per composite + edges |
| Agent layer | ~15 s | 4 Gemini calls, primaries parallel |
| Graph ingest (brief) | ~0.5 s | 9 sections |
| **Total** | **~50 s** | Inside 60s demo budget |

The slowest path is **Gemini round-trips** (4 × ~3-5s = ~15s) and **AIS capture** (fixed 30s). Faster fall-throughs:
- Skip AIS in the executor (`enable_ais=False`) → ~20s total but no dark-vessel detection
- Switch to a smaller LLM model → ~2-3s per agent → ~10s agent layer → ~40s total

For the demo, we ship the full pipeline at ~50s. The Brief includes a Loading skeleton during this window so the analyst sees coherent UI from second 0.

## Reproducing a pipeline run

The seed script reuses the executor:

```powershell
uv run python scripts/seed_neo4j.py
```

Runs the full pipeline against `"Aegean - last 7 days"` and prints a Cypher-queryable summary at the end. Use it to debug stage-specific issues:
- Sensor failures → check the WS event detail
- Agent crashes → check the audit chain entry for the error message
- Brief shape problems → query Neo4j directly with the Cypher in [data-model.md](data-model.md)

The same pipeline runs through the public API via `POST /api/watches`. The executor code path is identical.
