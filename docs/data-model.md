# Data model

The single source of truth for **shapes** in Damocles. Pydantic models on the server side, mirrored TypeScript types on the client side, persisted as Neo4j graph nodes + edges. Read this before changing any sensor, agent, or API endpoint.

## Layers of typing

| Layer | Source of truth | When it's enforced |
| --- | --- | --- |
| Server runtime | Pydantic models in [`backend/models/`](../backend/models/) | At construction; FastAPI rejects malformed requests |
| Storage | Neo4j schema constraints in [`backend/graph/schema.py`](../backend/graph/schema.py) | Idempotent constraint application on startup |
| Wire | Same Pydantic models serialized to JSON via FastAPI | Per-response |
| Client | Hand-written TypeScript in [`frontend/src/types.ts`](../frontend/src/types.ts) | At React Query consumer level (best-effort, no runtime validation) |

The client-side types are kept hand-written rather than openapi-generated so the file reads cleanly and we can comment domain-specific fields. They are checked against the actual server responses by the e2e test ([`scripts/test_e2e.py`](../scripts/test_e2e.py)).

## Watch — the analyst's query

[`backend/models/watch.py`](../backend/models/watch.py)

```python
class WatchDomain(str, Enum):
    MARITIME = "maritime"; BORDER = "border"; AIRSPACE = "airspace"
    INFORMATION = "information"; MULTI = "multi"

class WatchRegion(str, Enum):
    AEGEAN = "aegean"; IONIAN = "ionian"; EVROS = "evros"
    EASTERN_MED = "eastern_med"; CUSTOM = "custom"

class WatchStatus(str, Enum):
    PENDING = "pending"; PROCESSING = "processing"
    COMPLETE = "complete"; ERROR = "error"

class WatchSpec(BaseModel):
    region: WatchRegion = WatchRegion.AEGEAN
    custom_bbox: list[float] | None = None
    domain: WatchDomain = WatchDomain.MULTI
    time_window_days: int = 7
    keywords: list[str] = []
    threat_indicators: list[str] = []
    confidence: float = 1.0           # parser's confidence in the parse
    parse_notes: str | None = None

    def get_bbox(self) -> tuple[float, float, float, float]:
        # Returns (min_lon, min_lat, max_lon, max_lat)
        ...

class Watch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_query: str
    spec: WatchSpec
    created_at: datetime
    status: WatchStatus = WatchStatus.PENDING
    brief_id: str | None = None
    error: str | None = None
```

**Key invariant:** `WatchSpec.get_bbox()` always returns a tuple. Custom bboxes fall back to the Aegean default if malformed. Region-bbox lookup table is hardcoded in the same file.

## Sensor events

[`backend/models/event.py`](../backend/models/event.py)

These are what sensors *produce*. Each has a unique ID, lat/lon, timestamp. They become nodes in the graph (one node type per Pydantic class).

### Vessel
```python
class AISStatus(str, Enum):
    BROADCASTING = "broadcasting"; DARK = "dark"; UNKNOWN = "unknown"

class Vessel(BaseModel):
    id: str
    lat: float; lon: float; timestamp: datetime
    detection_source: str            # "SAR" | "AIS" | "both"
    ais_status: AISStatus = AISStatus.UNKNOWN
    confidence: float = 0.0          # CFAR detection confidence
    sar_tile_id: str | None = None   # FK into the cached SAR PNG store
    mmsi: str | None = None
    vessel_name: str | None = None
    flag: str | None = None
    length_m: float | None = None
    # Filled in by the dark-vessel cross-reference (Day 5 of the build)
    dark_vessel_score: float | None = None
    ais_match_distance_km: float | None = None
```

### NewsEvent
```python
class NewsEvent(BaseModel):
    id: str
    source_url: str
    source_name: str
    headline: str
    timestamp: datetime
    lat: float; lon: float
    goldstein_scale: float = 0.0     # -10 (conflictual) to +10 (cooperative)
    cameo_code: str = ""             # CAMEO event code, see GDELT codebook
    language: str = "en"
    mentions: int = 1
```

### SocialSignal
```python
class SocialSignal(BaseModel):
    id: str
    channel: str                     # e.g. "@aegeanwatch"
    channel_verified: bool = False
    message_id: str
    text: str
    timestamp: datetime
    language: str = "und"            # langdetect result
    views: int = 0
    forwards: int = 0
    has_media: bool = False
    lat: float | None = None         # filled by Linguist agent (gazetteer match)
    lon: float | None = None
```

### AirspaceEvent
```python
class AirspaceEvent(BaseModel):
    id: str
    icao24: str
    callsign: str | None = None
    lat: float; lon: float
    altitude_m: float | None = None
    velocity_ms: float | None = None
    heading: float | None = None
    timestamp: datetime
    origin_country: str | None = None
    suspicious_patterns: list[str] = []
```

(Wired in `backend/sensors/` but not yet on the executor's hot path — flagged as future work.)

### CompositeEvent — the fusion output
```python
class ThreatGrade(str, Enum):
    GREEN = "GREEN"; AMBER = "AMBER"; RED = "RED"

class CompositeEvent(BaseModel):
    id: str
    threat_grade: ThreatGrade = ThreatGrade.GREEN
    confidence: float = 0.0
    corroboration_count: int = 1     # number of distinct SENSORS contributing
    summary: str = ""
    created_at: datetime
    source_node_ids: list[str] = []  # IDs of constituent sensor events
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    time_window_start: datetime | None = None
    time_window_end: datetime | None = None
```

**Threat-grade rules** (in [`backend/sensors/fusion.py`](../backend/sensors/fusion.py)):
- `GREEN` — single source AND no high-conflict signal
- `AMBER` — 2+ sensors OR a high-conflict signal (Goldstein ≤ -5 OR a dark vessel with `dark_vessel_score >= 0.85`)
- `RED` — 3+ sensors AND a dark vessel AND high-conflict signal

## Brief — the analyst-readable output

[`backend/models/brief.py`](../backend/models/brief.py)

```python
class SectionType(str, Enum):
    BLUF = "BLUF"
    KEY_JUDGMENT = "KEY_JUDGMENT"
    SUPPORTING = "SUPPORTING"
    DEVILS_ADVOCATE = "DEVILS_ADVOCATE"
    RECOMMENDATION = "RECOMMENDATION"

class Urgency(str, Enum):
    ROUTINE = "ROUTINE"; PRIORITY = "PRIORITY"; IMMEDIATE = "IMMEDIATE"

class BriefSection(BaseModel):
    id: str
    section_type: SectionType
    text: str
    citation_node_ids: list[str]     # MANDATORY — the gold-medal contract
    confidence: float = 0.0
    agent_source: str = ""           # "geospatial" | "osint" | "fused" | "supervisor" | "devils_advocate"
    extra: dict[str, Any] = {}        # devil_confidence (Devil), urgency (Recommendation)

class Brief(BaseModel):
    id: str
    watch_id: str
    bluf: BriefSection
    key_judgments: list[BriefSection] = []
    supporting_evidence: list[BriefSection] = []
    devils_advocate: BriefSection | None = None
    recommendation: BriefSection | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime
```

**Critical rule:** `citation_node_ids` is non-empty for every text-bearing section. The Supervisor's validation rejects any output where it's empty.

## SourceNode — the citation chain payload

[`backend/models/brief.py`](../backend/models/brief.py)

Returned by `GET /api/briefs/{brief_id}/citation/{section_id}`. This is what the frontend renders as a source card.

```python
class SourceNode(BaseModel):
    node_id: str
    node_type: str                   # "Vessel" | "NewsEvent" | "SocialSignal" | "CompositeEvent"
    properties: dict[str, Any]       # the full Neo4j node properties
    raw_evidence: dict[str, Any]     # type-specific artefact reference
    map_highlight: dict[str, Any]    # { lat, lon, radius_km } | None
    graph_highlight: dict[str, Any]  # { node_id, connected_node_ids }
```

`raw_evidence` shape varies by `node_type`:
- `Vessel` → `{ type: "SAR_TILE", tile_id, metadata }` — frontend resolves to `/static/sar/<tile_id>.png`
- `NewsEvent` → `{ type: "ARTICLE_URL", url, metadata }` — opens in a new tab
- `SocialSignal` → `{ type: "TELEGRAM_MESSAGE", content, metadata }` — rendered inline
- `CompositeEvent` → `{ type: "COMPOSITE", metadata }`

## AuditEntry — the Merkle chain

[`backend/models/audit.py`](../backend/models/audit.py)

```python
GENESIS_HASH = "GENESIS"

class AuditEntry(BaseModel):
    id: str
    timestamp: datetime
    action_type: str                 # e.g. "watch.created", "agent.geospatial.run"
    actor: str                       # which component / analyst
    payload_hash: str                # sha256 of canonical JSON of the payload
    previous_hash: str = GENESIS_HASH
    chain_hash: str                  # sha256(payload_hash + previous_hash)
    chain_valid: bool = True
```

Verification: walk entries in timestamp order, recompute `chain_hash` from each entry's `payload_hash + previous_hash`, compare. First mismatch = first tampered entry. See [audit.md](audit.md).

## Neo4j graph schema

[`backend/graph/schema.py`](../backend/graph/schema.py)

### Node types

| Label | Created by | Properties (key ones) |
| --- | --- | --- |
| `Watch` | `ingest_watch` | `id, raw_query, region, domain, created_at, status` |
| `Vessel` | `ingest_vessel` | `id, lat, lon, timestamp, ais_status, mmsi, length_m, sar_tile_id, dark_vessel_score` |
| `NewsEvent` | `ingest_news` | `id, source_url, headline, lat, lon, goldstein_scale, cameo_code` |
| `SocialSignal` | `ingest_social` | `id, channel, text, timestamp, language, views, lat, lon` |
| `AirspaceEvent` | `ingest_airspace` | `id, icao24, callsign, lat, lon, altitude_m` |
| `CompositeEvent` | `ingest_composite` | `id, threat_grade, confidence, corroboration_count, centroid_lat, centroid_lon` |
| `Brief` | `ingest_brief` | `id, watch_id, created_at, metadata` |
| `BriefSection` | `ingest_brief_section` | `id, section_type, text, citation_node_ids, confidence, agent_source, extra` |
| `AuditEntry` | `MerkleAuditLogger.log` | `id, timestamp, action_type, actor, payload_hash, previous_hash, chain_hash` |

### Edge types

| Edge | Direction | Created by | Meaning |
| --- | --- | --- | --- |
| `TRIGGERED` | `Watch -> CompositeEvent` | `ingest_composite` | "this watch produced this composite" |
| `PRODUCED` | `Watch -> Brief` | `ingest_brief` | "this watch produced this brief" |
| `COMPOSED_OF` | `CompositeEvent -> source` | `ingest_composite` | "this composite fuses these source events" |
| `CORROBORATES` | `source -> source` | (Day 7+ optional) | pairwise spatiotemporal correlation edge |
| `CITES` | `BriefSection -> source` | `ingest_brief_section` | the gold-medal edge — every cited claim has one |
| `CONTAINS` | `Brief -> BriefSection` | `ingest_brief` | structural |
| `FOLLOWS` | `AuditEntry -> AuditEntry` | `MerkleAuditLogger.log` | Merkle chain link |

### Constraints + indexes (idempotent)

- Uniqueness on `id` for every primary node label
- `RANGE` indexes on `(timestamp)` for `Vessel`, `NewsEvent`, `SocialSignal`, `AuditEntry`
- `RANGE` indexes on `(lat, lon)` for `Vessel`, `NewsEvent`

These are applied via `Neo4jClient.apply_schema()` on app startup. Re-running is a no-op.

## The gold-medal Cypher query

The single query that powers every citation click in the demo:

```cypher
MATCH (b:Brief {id: $brief_id})-[:CONTAINS]->(bs:BriefSection {id: $section_id})
OPTIONAL MATCH (bs)-[r:CITES]->(source)
OPTIONAL MATCH (source)<-[:COMPOSED_OF]-(ce:CompositeEvent)
OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(sibling)
WHERE sibling <> source
RETURN bs, b,
       collect(DISTINCT {type: labels(source)[0], cites: r.node_type, props: source}) AS sources,
       collect(DISTINCT {type: labels(sibling)[0], props: sibling}) AS siblings
```

Lives in [`backend/api/briefs.py`](../backend/api/briefs.py). Returns:
- The clicked BriefSection
- All sources it cites (the *direct* chain)
- Sibling sources of the same parent CompositeEvent (the *corroboration* chain)

The frontend renders `sources` as the inline expansion cards and would use `siblings` to draw "this evidence is corroborated by N other sensors" badges — that secondary view is currently shown only as a count, not full cards.

## TypeScript mirror

[`frontend/src/types.ts`](../frontend/src/types.ts) hand-mirrors the Pydantic shapes. Key examples:

```typescript
export interface SourceNode {
  node_id: string;
  node_type: SourceNodeType;       // "Vessel" | "NewsEvent" | ...
  properties: Record<string, unknown>;
  raw_evidence: {
    type: "SAR_TILE" | "ARTICLE_URL" | "TELEGRAM_MESSAGE" | "COMPOSITE";
    url?: string;
    tile_id?: string;
    content?: string;
    metadata?: Record<string, unknown>;
  };
  map_highlight: { lat: number; lon: number; radius_km: number } | null;
  graph_highlight: { node_id: string };
}
```

If the backend Pydantic shape changes, **update the TypeScript here in the same commit** to keep the mirror honest. The e2e test ([`scripts/test_e2e.py`](../scripts/test_e2e.py)) catches schema drift via its assertions.

## When to extend this

- **New sensor type** → add a Pydantic class in `backend/models/event.py`, add ingestion in `backend/graph/ingestion.py`, add label + constraint in `backend/graph/schema.py`. The fusion engine and agents pick it up automatically through node-label dispatch.
- **New agent type** → add an output Pydantic class (subclass of `AgentOutput` if it adds fields), add `output_model = MyOutputClass` on the agent class. `BaseAgent._parse` handles the rest.
- **New brief section** → add to `SectionType` enum, add the rendering branch in `frontend/src/components/BriefPanel.tsx`, update the Supervisor prompt to teach it the new section.

Cross-references: [pipeline.md](pipeline.md) for how these flow through the executor, [agents.md](agents.md) for the agent contract, [api.md](api.md) for the wire format.
