# Architecture

## What Damocles is

A **sovereign intelligence-analysis platform**: an analyst types a free-text query (`"Aegean — last 7 days"`), the system fuses satellite radar, vessel tracking, news, and social signals into a knowledge graph, runs a multi-agent LLM reasoning layer over the result, and produces a structured brief where **every sentence traces back to its source**. The system runs entirely on-premise with no external dependencies at runtime — that is the *sovereign* part.

The build is targeted at the **EYP National Security Innovation Challenge 2026** (gold medal, June 2026). The single most important differentiator is the citation chain: a judge clicks any sentence in the brief and the map flies to the source location, the graph highlights the source node, and an evidence modal opens with the raw artefact (SAR tile, news article, Telegram message). No competitor has this.

## System at a glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Analyst's query → Damocles → Brief with cited claims                       │
│                                                                             │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐       │
│  │  WatchInput │ →  │  Sensors   │ →  │  Fusion    │ →  │  Agents    │      │
│  │  (free text)│    │  (4 types) │    │  (corr.)   │    │  (5 LLMs)  │      │
│  └────────────┘    └────────────┘    └────────────┘    └─────┬──────┘      │
│                                                              ↓              │
│                                                       ┌────────────┐        │
│                                                       │  Brief     │        │
│                                                       │  (cited)   │        │
│                                                       └─────┬──────┘        │
│                                                             ↓                │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │  Three-panel UI (Map · Brief · Graph) + Audit log strip         │        │
│  │  Citation click → map flyTo + graph highlight + evidence modal  │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│                                                                             │
│  Every step is hashed into a Merkle-chained audit log (tamper-evident)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## The five-agent reasoning layer

The plan calls for a multi-agent pipeline that institutionalizes skepticism. Each agent has a typed Pydantic output, a citation contract (every claim cites a graph node ID), and a calibrated confidence range. They run sequentially with adversarial review.

```
                                      ┌──────────────────┐
        Composite Event ────────────→ │  Geospatial      │
            +                         │  Agent (Gemini)  │
        Source nodes  ───┬──────────→ └─────────┬────────┘
        (SAR / News /    │                      ↓
         Social /        │              ┌──────────────────┐
         Composite)      └────────────→ │  OSINT Agent     │
                                        │  (Gemini)        │
                                        └─────────┬────────┘
                                                  ↓
                                      ┌──────────────────┐
                                      │  Devil's         │←─┐
                                      │  Advocate        │  │ challenges
                                      │  (Gemini, T=0.3) │  │ the primaries
                                      └─────────┬────────┘  │
                                                ↓           │
                                      ┌──────────────────┐  │
                                      │  Supervisor      │──┘
                                      │  (Gemini, T=0.0) │
                                      └─────────┬────────┘
                                                ↓
                                          ┌────────┐
                                          │ Brief  │ ← every claim cited
                                          └────────┘
```

The **Linguist agent** (sixth in the registry, fifth in the pipeline) handles geocoding of Telegram text via a hardcoded Aegean gazetteer + spaCy. It runs *before* fusion to enrich SocialSignals so they correlate spatially — this is what closes the *Telegram-has-no-native-geocoding* problem documented in [limitations.md §4c.3](limitations.md).

See [agents.md](agents.md) for prompts, validation rules, and the specific role each agent plays.

## The citation chain (the gold-medal moment)

This is the architectural payoff. When the analyst clicks a sentence in the brief:

1. `BriefSection.id` → `GET /api/briefs/{brief_id}/citation/{section_id}`
2. The endpoint runs Cypher: `(BriefSection)-[:CITES]->(SourceNode)`
3. Returns `SourceNode[]` with `properties + raw_evidence + map_highlight + graph_highlight`
4. Frontend store's `activeCitation` updates
5. Three things fire concurrently:
   - **MapPanel** flies to `map_highlight.lat/lon` (~800ms animation)
   - **GraphPanel** dims all nodes, highlights cited ones, animates camera fit
   - **CitationExpansion** drops below the section showing source cards
6. Click a source card → **EvidenceModal** opens with the raw artefact:
   - **Vessel** → cached SAR tile PNG (with detection bounding box drawn on it)
   - **NewsEvent** → article URL + Goldstein scale visualization + open-in-new-tab
   - **SocialSignal** → message text + channel + views/forwards
   - **CompositeEvent** → threat-grade chip + summary + corroboration count

Every step is auditable — the click itself is logged as `brief.citation_accessed` in the Merkle chain.

## Component map

| Layer | Path | Owns |
| --- | --- | --- |
| **Sensors** | [`backend/sensors/`](../backend/sensors/) | Sentinel-1 SAR + CFAR detection, AISStream, GDELT, Telegram, fusion engine |
| **Watch engine** | [`backend/watch_engine/`](../backend/watch_engine/) | LLM-driven query parser, executor (the orchestrator), region GeoJSON loader |
| **Agents** | [`backend/agents/`](../backend/agents/) | BaseAgent + 5 concrete agents, prompts, geocoder for Linguist |
| **Graph** | [`backend/graph/`](../backend/graph/) | Async Neo4j client, schema, Cypher library, ingestion |
| **LLM** | [`backend/llm/`](../backend/llm/) | Provider abstraction (Gemini today, Ollama-ready), fallback chain |
| **Audit** | [`backend/audit/`](../backend/audit/) | Merkle logger, verify_chain |
| **API** | [`backend/api/`](../backend/api/) | FastAPI routers, in-memory event broker, neo4j-time JSON serializer |
| **Models** | [`backend/models/`](../backend/models/) | Watch / Event / Brief / AuditEntry Pydantic shapes |
| **Frontend** | [`frontend/src/`](../frontend/src/) | React + Zustand + MapLibre + Cytoscape; three-panel UI |
| **Tests** | [`tests/`](../tests/) | 140+ unit tests across all layers |
| **Smokes** | [`scripts/`](../scripts/) | Live-data smoke tests (run against the actual sensors and Gemini) |

## Design principles

These are the rules every component obeys. They explain why certain decisions were made.

### 1. Sovereignty above convenience
- **No external runtime calls during the demo.** Gemini is dev-only; production runs Ollama on local hardware. Switching is one env var (`LLM_PROVIDER`). See [`backend/llm/factory.py`](../backend/llm/factory.py).
- **MapLibre GL, not Mapbox.** Same WebGL UX, BSD-3 license, no API key, and the map style is hosted by CARTO today but can be swapped to self-hosted Protomaps for full sovereignty (limitation §6.1).
- **All data sources are free and public.** Sentinel-1 (Copernicus), AISStream, GDELT, OpenSky, Telegram public channels.

### 2. Citation discipline as a contract, not a guideline
- Every agent output type (`AgentOutput`, `DevilsAdvocateOutput`, `SupervisorOutput`) has a **mandatory** `citation_node_ids` field.
- `validate_agent_output()` rejects orphan claims: every cited ID must exist in the supplied context.
- Retry-on-failure: invalid output → second LLM call with the validation error embedded in the correction prompt.
- A claim without a citation is invalid output. There is no "trust me, the model knows" path.

### 3. Tamper-evidence, not just logging
- Every sensor fetch, agent call, and citation click writes a Merkle-chained `AuditEntry`.
- Two-store persistence: Neo4j AuditEntry nodes AND a local append-only JSONL file.
- `verify_chain()` runs O(N) and returns the index of the first tampered entry.
- The frontend's top-bar always shows `audit OK · N` (green) or `TAMPER @ idx` (red) — no need to click.
- See [audit.md](audit.md).

### 4. Pre-fetched context, not LLM tool calling
- Each agent's `fetch_context()` does targeted Cypher queries upfront, formats the result compactly with the explicit list of valid IDs the model may cite, then calls the LLM **once** (twice if retry).
- We rejected tool calling because it adds two failure modes (hallucinated tool names, malformed args) for no practical benefit on a focused 5-agent pipeline.
- The agent's "smarts" come from the prompt + the structured context, not from autonomous graph exploration.

### 5. Pre-seeded historical demo, not live data
- Sentinel-1's 6-day revisit + AISStream's no-historical free tier mean live data may be empty or stale on demo day.
- The plan calls for a March 2024 Aegean scenario seeded into Neo4j; the demo runs against that.
- Operationally: same pipeline, same code paths — only the seed step is different.
- The plan-recommended pitch line: *"This demo runs on a real historical scenario from March 2024. In production deployment the same pipeline runs on live data with a 15-minute lag."*

### 6. Provider abstraction at every external boundary
- LLM: `LLMProvider` interface (`gemini` / `ollama`).
- Map tiles: MapLibre style URL is a config — swap the URL, swap the cartography.
- Audit storage: dual-store with the longer source winning; either can be unavailable.
- Sensor failures degrade gracefully (logged, the rest of the pipeline continues).

### 7. Audit the observation, not the observer
- The audit chain records *that an event happened* and *who/what triggered it*, never the analyst's identity tied to a session token. (Production deployment with real OIDC will tie identities through to the audit `actor` field — see [deployment.md](deployment.md).)
- Sensitive payloads (LLM completions) are hashed, not stored verbatim, in audit entries. The full text lives in the structured Brief / SourceNode that the chain references.

## Data flow: a worked example

Analyst types **"Aegean — last 7 days"** at 12:00 UTC. Here's exactly what happens.

| Time | Action | Where it happens |
| --- | --- | --- |
| 12:00:00 | `POST /api/watches { query }` | [watches.py](../backend/api/watches.py) |
| 12:00:00 | Watch parser turns text → WatchSpec via Gemini in JSON mode | [watch_engine/parser.py](../backend/watch_engine/parser.py) |
| 12:00:01 | Watch ingested as `(:Watch)` node; audit `watch.created` | [graph/ingestion.py](../backend/graph/ingestion.py) |
| 12:00:01 | Pipeline launched as background task; client gets 200 | [watches.py](../backend/api/watches.py) |
| 12:00:01 | Client connects WS `/ws/watches/{id}` for progress events | [ws.py](../backend/api/ws.py) |
| 12:00:01 | Sensors fan out **concurrently** (geospatial, gdelt, ais, telegram) | [executor.py](../backend/watch_engine/executor.py) |
| 12:00:12 | Sentinel-1 IW VV+VH tile fetched (~2500×2500) | [sensors/geospatial.py](../backend/sensors/geospatial.py) |
| 12:00:13 | CFAR detector runs on dB-scaled VV → ~485 vessel candidates | [sensors/cfar.py](../backend/sensors/cfar.py) |
| 12:00:30 | AISStream WebSocket capture finishes (~30s) → ~70 broadcasts | [sensors/ais.py](../backend/sensors/ais.py) |
| 12:00:30 | Cross-reference: SAR vs AIS → vessels marked `BROADCASTING` or `DARK` | [sensors/dark_vessel.py](../backend/sensors/dark_vessel.py) |
| 12:00:30 | GDELT 15-min slots downloaded + filtered → ~160 events | [sensors/gdelt.py](../backend/sensors/gdelt.py) |
| 12:00:30 | Telegram channels iterated → SocialSignals (skipped if no session) | [sensors/telegram_sensor.py](../backend/sensors/telegram_sensor.py) |
| 12:00:32 | Sensor events ingested into graph | [graph/ingestion.py](../backend/graph/ingestion.py) |
| 12:00:33 | Fusion engine runs spatiotemporal correlation → CompositeEvents | [sensors/fusion.py](../backend/sensors/fusion.py) |
| 12:00:33 | Composites linked to Watch; threat grades assigned (GREEN/AMBER/RED) | [graph/ingestion.py](../backend/graph/ingestion.py) |
| 12:00:34 | Top composite picked (highest grade × confidence × corroboration) | [executor.py](../backend/watch_engine/executor.py) |
| 12:00:34 | **Geospatial + OSINT agents run concurrently** | [agents/](../backend/agents/) |
| 12:00:42 | **Devil's Advocate agent** challenges both | [agents/devils_advocate.py](../backend/agents/devils_advocate.py) |
| 12:00:50 | **Supervisor agent** assembles 5-section Brief | [agents/supervisor_agent.py](../backend/agents/supervisor_agent.py) |
| 12:00:53 | Brief ingested into graph (`Brief` + `BriefSection` nodes + `CITES` edges) | [graph/ingestion.py](../backend/graph/ingestion.py) |
| 12:00:53 | WS event `complete` published; client renders the brief | [executor.py](../backend/watch_engine/executor.py) |
| 12:01:00 | Analyst clicks BLUF sentence | [frontend/CitableText.tsx](../frontend/src/components/CitableText.tsx) |
| 12:01:00 | `GET /api/briefs/.../citation/{section_id}` returns 2 source nodes | [api/briefs.py](../backend/api/briefs.py) |
| 12:01:00 | Map flies to coords, graph highlights, citation expansion drops in | [frontend/](../frontend/src/components/) |
| 12:01:01 | Audit chain entry `brief.citation_accessed` written | [audit/logger.py](../backend/audit/logger.py) |

Total: ~53 seconds for the full pipeline. Inside the demo's 60-second budget.

See [pipeline.md](pipeline.md) for the executor walkthrough and [demo-script.md](demo-script.md) for what to say at each stage.

## What we explicitly chose NOT to build

These are intentional scope decisions, not gaps:

- **No fine-tuned model.** All LLM behaviour comes from prompt engineering + structured-output validation. We don't ship model weights.
- **No vector database.** Citations are graph edges, not embeddings. The retrieval pattern is targeted Cypher, not approximate nearest-neighbours.
- **No streaming LLM responses.** Each agent call is request-response. Streaming would complicate the validation pipeline (we can't validate citations until we've seen the whole output).
- **No real-time dark-vessel detection.** The seed pipeline captures live AIS during the seed window; the demo plays back. See [limitations.md §4.1](limitations.md).
- **No multi-watch aggregation.** One Watch produces one Brief. A "watch-level supervisor" that aggregates the top-N composites is documented as future work in [limitations.md §5b.8](limitations.md).
- **No mobile UI.** Three-panel layout assumes a 1920×1080 analyst workstation.

See [limitations.md](limitations.md) for the full ledger.
