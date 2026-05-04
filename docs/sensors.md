# Sensors

Damocles consumes five free, public data sources. Each sensor lives in [`backend/sensors/`](../backend/sensors/), implements the `BaseSensor[T]` contract, and produces typed Pydantic events the rest of the pipeline can ingest.

| Sensor | Source | Output | Free-tier ceiling |
| --- | --- | --- | --- |
| **Geospatial** | Sentinel-1 SAR (Copernicus Data Space) | `Vessel[]` | 30k processing units / month |
| **AIS** | AISStream WebSocket | `AISRecord[]` (raw) | 1 connection, ~1k msg/min |
| **GDELT** | GDELT 2.0 Events public CSV | `NewsEvent[]` | unlimited |
| **Telegram** | Telethon (MTProto) | `SocialSignal[]` | per-app rate limits |
| **OpenSky** | ADS-B REST | `AirspaceEvent[]` | 100 calls/day anon, 4k registered |

Every sensor's free-tier signup is documented in [credentials.md](credentials.md).

## The base contract

[`backend/sensors/base.py`](../backend/sensors/base.py)

```python
class BaseSensor(ABC, Generic[T]):
    name: str = "base"

    @abstractmethod
    async def fetch(
        self,
        bbox: BBox,                    # (min_lon, min_lat, max_lon, max_lat)
        time_from: datetime,
        time_to: datetime,
        **kwargs: Any,
    ) -> SensorResult[T]:
        """Fetch + process. Returns a SensorResult; never raises on no-data —
        empty list is a valid outcome. Raises only on hard errors (auth,
        network failure, malformed response)."""
```

Returns:
```python
@dataclass
class SensorResult(Generic[T]):
    sensor_name: str
    events: list[T]                   # typed Pydantic events
    bbox: BBox
    time_from: datetime
    time_to: datetime
    metadata: dict[str, Any]          # what the audit log hashes
    duration_ms: float
```

`metadata` carries everything the audit log needs to reproduce the fetch (tile IDs, query parameters, response sizes, durations). The hash of this metadata is what makes the citation chain auditable down to the raw fetch.

## Geospatial sensor — Sentinel-1 + CFAR

[`backend/sensors/geospatial.py`](../backend/sensors/geospatial.py) + [`backend/sensors/cfar.py`](../backend/sensors/cfar.py)

### Pipeline

```
bbox + time window
    ↓
SentinelHubRequest → IW VV+VH GRD tile → numpy float32 (2500×2500 max)
    ↓
CFAR (cfar.py) on dB-scaled VV → list[CFARDetection] in pixel space
    ↓
pixel→geo conversion → list[Vessel] in lat/lon
    ↓
cache PNG preview to data/cache/sar/<tile_id>.png (with bounding boxes drawn on)
```

### CFAR (Constant False Alarm Rate) — the detection algorithm

The standard operational algorithm used by coast guards worldwide. For each pixel:
1. Estimate clutter mean + std from a ring of *training cells* around it
2. Separate target from training with a *guard ring* (so target energy doesn't pollute the clutter estimate)
3. Flag pixel if `value > mean + alpha * std` (alpha = 4.0 for ~3e-5 false-alarm rate)
4. Connected-component labeling clusters flagged pixels into vessel candidates
5. Filter by size (`min=3px ≈ small vessel, max=2000px ≈ rejects land/clouds`)

**Default knobs** (in `CFARParams`):
```python
guard_cells = 4         # half-width of the guard ring
training_cells = 8      # half-width of the training ring
alpha = 4.0             # threshold std-multiplier
min_size_pixels = 3
max_size_pixels = 2000
```

**Implementation** uses `scipy.ndimage.uniform_filter` for the box-filtered mean and mean-of-squares (separable, O(N) per axis). Std follows from `E[X²] - E[X]²`. A 1024×1024 patch runs in ~150 ms on a Windows CPU.

**Confidence score** combines (a) cluster size and (b) excess over the local CFAR threshold. A 3-pixel cluster barely crossing threshold gets ~0.55; a 50-pixel cluster well above threshold (a freighter) maxes out near 0.99.

### Sentinel Hub authentication

OAuth2 client credentials. Tokens are auto-refreshed by `sentinelhub-py`. The provider URL is the **new Copernicus Data Space**, not the deprecated SciHub:

```python
config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
config.sh_base_url  = "https://sh.dataspace.copernicus.eu"
```

### Cost budget

A 0.5°×0.5° patch at 10 m/px (2500×2500 pixels) costs ~5-10 PU. The full Aegean tiled at the same resolution costs ~150-200 PU. Free tier is 30k/month — comfortable.

### Limitations

- **Tile timestamp is window midpoint**, not actual acquisition time. The Process API path doesn't expose per-scene metadata. See [limitations.md §3.1](limitations.md). Fixed by switching to the Catalog API in the seed pipeline.
- **No land mask** — coastal rocks, breakwaters, and oil platforms can register as vessels. AIS cross-reference filters most.
- **No tile cache yet** — each fetch re-spends PUs.

## AIS sensor — AISStream WebSocket

[`backend/sensors/ais.py`](../backend/sensors/ais.py)

### Protocol

WebSocket to `wss://stream.aisstream.io/v0/stream`. First frame must be a JSON subscription:

```json
{
  "APIKey": "<your-key>",
  "BoundingBoxes": [[[35.0, 22.0], [42.0, 28.0]]],
  "FilterMessageTypes": ["PositionReport"]
}
```

**Critical gotcha:** AISStream uses `[[lat, lon]]` order in BoundingBoxes — the OPPOSITE of GeoJSON. This is the #1 source of "no messages" complaints. Doubly nested: outer = list of boxes, each box = `[[sw_lat, sw_lon], [ne_lat, ne_lon]]`.

### Output

Raw `PositionReport` messages parsed into `AISRecord`:
```python
@dataclass
class AISRecord:
    mmsi: str
    lat: float; lon: float
    timestamp: datetime
    name: str | None = None
    sog_knots: float | None = None
    cog_deg: float | None = None
    flag: str | None = None
```

The cross-reference function ([`backend/sensors/dark_vessel.py`](../backend/sensors/dark_vessel.py)) takes SAR `Vessel[]` + AIS `AISRecord[]` and produces enriched `Vessel[]` with `ais_status` set.

### Limitations

- **No historical replay on free tier.** Live only. Sentinel-1's 6-day revisit means a fresh SAR tile may be 5 days stale; cross-referencing today's live AIS against that is meaningless. The seed pipeline captures live AIS during the seed window and pickles it for replay.
- **Only `PositionReport` parsed.** Static data (type 5) carries vessel name, callsign, IMO, dimensions — would let us populate `flag` and exact lengths. Easy follow-up; documented in [limitations.md §4.2](limitations.md).
- **MMSI → flag (MID code) lookup not implemented.** Half-day work, big agent-reasoning impact. Documented in [limitations.md §4.3](limitations.md).

## GDELT sensor — public events database

[`backend/sensors/gdelt.py`](../backend/sensors/gdelt.py)

### Protocol

GDELT 2.0 publishes a 15-minute master file index at:
```
http://data.gdeltproject.org/gdeltv2/masterfilelist.txt
```

Each line: `<size> <sha1> <url>`. URLs come in three flavors per slot — `*.export.CSV.zip` (events), `*.mentions.CSV.zip`, `*.gkg.csv.zip`. We fetch only events.

We **stream-parse** the master file to filter URLs by date (no need to load the 123 MB index into memory), download each slot ZIP, parse the inner TSV, filter rows.

### Schema gotcha — GDELT 2.0 has 61 fields, not 58

This caught us during Day 6 of the build. v2 added `Actor1/2/Action_Geo_ADM2Code` fields. The v1 documentation has `ActionGeo_Lat=field 55`; v2 has it at field **56**. Off-by-one across the geo blocks.

Critical field offsets we use:
```
[0]  GLOBALEVENTID
[1]  SQLDATE
[7]  Actor1CountryCode      ← CAMEO codes (mostly ISO 3166-1 alpha-3, e.g. GRC)
[17] Actor2CountryCode      ← same scheme
[26] EventCode              ← CAMEO event code (4 digits)
[28] EventRootCode          ← CAMEO root (2 digits)
[30] GoldsteinScale         ← -10 to +10
[31] NumMentions
[53] ActionGeo_CountryCode  ← FIPS 10-4 (e.g. GR for Greece)
[55] ActionGeo_ADM2Code     ← v2 addition; the off-by-one trap
[56] ActionGeo_Lat
[57] ActionGeo_Long
[58] ActionGeo_FeatureID
[59] DATEADDED              ← 14-digit YYYYMMDDHHMMSS
[60] SOURCEURL
```

### Country code dual-scheme — the second gotcha

`Actor1/2CountryCode` use **CAMEO codes (mostly ISO 3166-1 alpha-3)**: `GRC` Greece, `TUR` Turkey, `CYP` Cyprus.

`ActionGeo_CountryCode` uses **FIPS 10-4**: `GR`, `TU`, `CY`.

Same country, different code. A row about Greek-Turkish events might have `Actor1=GRC` and `ActionGeo=GR`. We accept both representations in `DEFAULT_ACTOR_COUNTRIES`:

```python
DEFAULT_ACTOR_COUNTRIES = (
    "GRC", "TUR", "CYP",   # CAMEO / ISO alpha-3 — fields 7, 17
    "GR",  "TU",  "CY",    # FIPS 10-4 — field 53
)
```

If you add a new country, add **both** code variants.

### CAMEO event roots we filter to

```python
DEFAULT_THREAT_CAMEO_ROOTS = (
    "11", "12",  # Disapprove, Reject
    "13", "14",  # Threaten, Protest
    "15", "16",  # Exhibit force posture, Reduce relations
    "17",        # Coerce (sanctions, blockades)
    "18", "19",  # Assault, Fight
    "20",        # Use unconventional mass violence
)
```

For broader contextual events, pass `cameo_roots=()` or a custom set. The full CAMEO codebook is at http://data.gdeltproject.org/documentation/CAMEO.Manual.1.1b3.pdf.

### Bbox filtering

Because GDELT geocodes events to **where the action happened**, not where the actors are based, a Greek-Turkish dispute discussed at the UN geocodes to Geneva. The executor's GDELT fetch widens the bbox by ±2° to catch surrounding contextual events; the standalone smoke test (`scripts/test_gdelt.py`) uses a global bbox.

### Cost

Each 15-min slot ZIP is ~1-3 MB compressed. A 24-hour window = 96 slots = ~150 MB of downloads. Free, but slow on a bad connection.

## Telegram sensor — Telethon over MTProto

[`backend/sensors/telegram_sensor.py`](../backend/sensors/telegram_sensor.py)

### Protocol

Telethon (MTProto Python client) iterates messages from public channels. Authentication is phone-number-based — Telegram sends a code via SMS or the in-app login flow, the user pastes it into the terminal once, Telethon pickles a session file at `data/cache/telegram/damocles.session` for subsequent runs.

The first-run interactive auth is a CLI script ([`scripts/setup_telegram.py`](../scripts/setup_telegram.py)). Subsequent runs are non-interactive.

### Channel curation

`DEFAULT_CHANNELS` is a placeholder list of plausible Aegean OSINT channels. The user must replace these with channels they've actually verified exist and joined in their Telegram client (Telethon needs to be a member to read).

### Keyword matching — the diacritic-tolerant matcher

```python
def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold()
    s = s.replace("ς", "σ")          # unify Greek final sigma
    return s
```

Handles two language gotchas:
- **Greek monotonic orthography**: uppercase letters drop the tonos. `"ΑΙΓΑΙΟ"` doesn't substring-match `"Αιγαίο"` under plain `casefold()` because the final sigma forms differ. NFD + strip-Mn + sigma-unify fixes this.
- **Turkish dotted I**: `İ`/`I`/`ı`/`i` collapse correctly under casefold (no extra work).

Greek inflection (`Σάμος` nominative vs `Σάμο` accusative) is handled by the geocoder's alias-variant generator, not the keyword matcher.

### Output

```python
class SocialSignal(BaseModel):
    channel: str                     # "@aegeanwatch"
    message_id: str
    text: str
    timestamp: datetime
    language: str                    # langdetect result
    views: int; forwards: int
    has_media: bool
    lat: float | None                # filled by Linguist agent
    lon: float | None
```

Note `lat/lon` are None at sensor time. The Linguist agent (Day 9) runs before fusion, geocodes the message text via the Aegean gazetteer, and writes lat/lon back. See [agents.md](agents.md).

### Limitations

- **Public channels only.** Reading restricted channels needs membership and is out of scope.
- **First-run interactive auth.** The plan is to wrap this in a UI flow during deployment hardening — see [limitations.md §4c.1](limitations.md).
- **No type-5 static-data parsing.** Today only `PositionReport` is parsed. Static data would carry IMO numbers, dimensions, etc.

## OpenSky sensor — ADS-B (placeholder, not on hot path)

The plan calls for an airspace sensor consuming OpenSky Network's ADS-B feed. Implementation is sketched in `backend/sensors/` but not yet on the executor's hot path.

When wired:
- **Live state vectors** — anonymous endpoint (`/api/states/all?lamin=...&lamax=...`), 100 calls/day.
- **Historical state vectors** — registered endpoint (`/api/flights/all?...`), 4k calls/day.
- Suspicious patterns: no callsign (military often suppress), rapid heading change, rapid altitude drop, orbit pattern (circular flight = ISR/surveillance).

Documented in [credentials.md §6](credentials.md).

## Fusion engine

[`backend/sensors/fusion.py`](../backend/sensors/fusion.py)

Not a sensor strictly speaking — it's the operator that turns sensor outputs into corroborated `CompositeEvent`s. See [pipeline.md §Stage 3](pipeline.md#stage-3--fusion--graph-ingest) for the algorithm and [data-model.md](data-model.md) for the threat-grade rules.

Tested in [`tests/test_fusion.py`](../tests/test_fusion.py) — 14 deterministic tests covering pair correlation, cross-sensor isolation, three-sensor chains, all four threat-grade rules, custom thresholds.

## Adding a new sensor

1. **Define the event Pydantic class** in [`backend/models/event.py`](../backend/models/event.py).
2. **Add a Neo4j label + uniqueness constraint** in [`backend/graph/schema.py`](../backend/graph/schema.py).
3. **Write an ingestion function** in [`backend/graph/ingestion.py`](../backend/graph/ingestion.py).
4. **Implement `BaseSensor[T]`** in `backend/sensors/<your_sensor>.py`. Use `asyncio` for I/O. Return empty list on no-data; raise only on hard errors.
5. **Wire it into the fusion engine**: add an entry to `DEFAULT_SPATIAL_RADIUS_KM` and `DEFAULT_TEMPORAL_WINDOW_H` in [`backend/sensors/fusion.py`](../backend/sensors/fusion.py).
6. **Add it to `WatchExecutor.execute()`** in [`backend/watch_engine/executor.py`](../backend/watch_engine/executor.py): create a task in the sensor fan-out, accumulate the events into the fusion call.
7. **Write unit tests** with synthetic data + a live smoke test in `scripts/test_<sensor>.py`.
8. **Document credentials** in [credentials.md](credentials.md) and any quirks in this file.

The agent layer picks up the new event type automatically through node-label dispatch — `OSINTAgent` matches any node with label `NewsEvent` or `SocialSignal`, etc. Add a domain-specific agent if needed, otherwise existing ones can read the new node type as long as the property names match conventions (`lat`, `lon`, `timestamp`, `id`).
