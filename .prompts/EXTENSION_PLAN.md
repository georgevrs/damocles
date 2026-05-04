# DAMOCLES — Expansion Plan v3.0
## New Sources + Areas of Interest + Information DNA + UI Overhaul
### Feed to Claude Opus 4.6 in VSCode

---

## READ THIS FIRST — THE PHILOSOPHY CHANGE

The previous expansion plan (v2.0) treated sensors as inputs to analyst-initiated queries.
That model is **replaced**. You are implementing a different architecture.

**The new model:**

```
Standing Scan (heartbeat) → All Sensors fire → Composite Events →
HDBSCAN clustering → Alpha-shape polygons → AoI nodes in graph →
AoI Agent names them → Map renders polygons → Analyst sees clusters
before asking anything
```

**What this means for every decision you make:**

1. Sensors feed the standing scan, not analyst queries. A Watch/query is still
   supported for ad-hoc investigation, but the primary loop is autonomous.

2. AoIs (Areas of Interest) are the primary output visible to the analyst.
   Composite events are the secondary output. Individual sensor events are
   evidence, not display objects.

3. The map opens with polygons already drawn. The analyst didn't ask for them.
   They exist because the data clustered. Every polygon is clickable and fully
   auditable — one click reveals the composite events inside it, another click
   reveals the sensor events that built each composite, another reveals raw evidence.

4. Information DNA visualizes the AoI's internal evidence chain — not the
   global graph. When the analyst clicks an AoI polygon, the DNA panel loads
   that AoI's subgraph: its composite events as nodes, their sensor events
   as organelles, their corroboration links as base pairs.

5. The standing scan runs on a configurable interval (default: every 6 hours).
   After each scan, the AoI inference pipeline runs automatically. AoIs are
   findings, not configuration. They are regenerated, not edited.

---

## AGENT CONTEXT

You are continuing development of Damocles, a live FastAPI + React intelligence
platform. The core pipeline already exists: sensors → fusion → Neo4j knowledge
graph → multi-agent reasoning → brief with citation chain. The Watch system works.

This document instructs you to build the AoI layer on top of that foundation,
add 11 new free data sources, and overhaul the frontend to match the new
polygon-first philosophy.

**Do not break existing functionality.** The Watch system stays. Briefs stay.
The citation chain stays. The Merkle audit log stays. You are extending, not replacing.

**Greece scope for ALL sensors:**
```python
GREECE_SCAN_BBOX = {
    "min_lon": 19.0,   # Western Ionian
    "min_lat": 34.0,   # Southern Crete / Mediterranean
    "max_lon": 30.0,   # Eastern Aegean / Turkish coast
    "max_lat": 43.0,   # Northern border zone
}
# Extended bbox for neighbor context (sensors fetch this, display clips to above)
NEIGHBOR_BBOX = {
    "min_lon": 17.0,   # Albania coast
    "min_lat": 31.0,   # Libya coast
    "max_lon": 37.0,   # Lebanon / Syria coast
    "max_lat": 45.0,   # Southern Bulgaria / Romania
}
```

---

## PART 1: SOURCE AUDIT — FINAL DECISIONS

### Green — Build These (11 sources)

| # | Source | Key? | Latency | AoI contribution |
|---|--------|------|---------|-----------------|
| 1 | USGS Earthquakes | None | Real-time | Physical clustering near fault lines |
| 2 | NASA FIRMS | Free MAP_KEY | <3h | Fire cluster polygons (Attica, Rhodes, Evros) |
| 3 | GDACS | None | 15 min | Multi-source disaster confirmation signal |
| 4 | NASA EONET | None | Near-RT | Polygon-geometry events (fire perimeters) |
| 5 | ACLED | Free acct | Weekly | Conflict cluster polygons near borders |
| 6 | GPSJAM | None (daily scrape) | 24h | Jamming zones → AMBER AoIs over Aegean |
| 7 | IMF PortWatch | None | Weekly | Chokepoint anomaly → port-area AoI |
| 8 | Submarine Cable | None (static GeoJSON) | Static | Infrastructure overlay; triggers when near news cluster |
| 9 | UN OCHA HAPI | Free acct | Weekly | Migration pressure → border AoI context |
| 10 | Cloudflare Radar | Free token | Near-RT | Internet outage → context for existing AoIs |
| 11 | Polymarket | None | Real-time | Probability signal enriches AoI brief, not clustering |

### Red — Skip

All sources from v2.0 "Skip for Now" remain skipped. Additionally:
- **Polymarket** feeds the AoI *brief* as a context signal, not the *clustering*.
  It has no lat/lon and cannot contribute to HDBSCAN. It is fetched separately
  and injected into the AoI Agent's naming/grading prompt.
- **OCHA HAPI** similarly — country-level aggregate with no precise geometry.
  It contributes to the brief, not to clustering. Plotted as a fixed point.

---

## PART 2: THE STANDING SCAN — NEW CORE PIPELINE

### Architecture

```
backend/
  scan/
    __init__.py
    scheduler.py        ← APScheduler: runs scan every N hours
    runner.py           ← ScanRunner: orchestrates one full scan cycle
    state.py            ← ScanState model: tracks scan progress + sensor health

backend/agents/
    aoi_agent.py        ← AoI inference: HDBSCAN → alpha-shape → LLM naming
```

### `backend/scan/runner.py`

```python
import asyncio
import uuid
from datetime import datetime, timedelta
from structlog import get_logger

from backend.sensors.registry import build_sensor_registry
from backend.sensors.fusion import FusionEngine
from backend.graph.ingestion import GraphIngestion
from backend.agents.aoi_agent import AoIAgent
from backend.scan.state import ScanState, ScanStatus
from backend.audit.logger import MerkleAuditLogger

logger = get_logger()

class ScanRunner:
    """
    Executes one full standing scan cycle.

    Pipeline:
    1. All sensors fire in parallel (asyncio.gather with per-sensor timeout)
    2. Sensor events are fused into composite events
    3. Composite events are written to Neo4j
    4. AoI agent runs HDBSCAN → alpha-shape → LLM naming
    5. AoI nodes written to Neo4j with [:CONTAINS] edges
    6. Scan state updated: complete / partial / failed
    7. WebSocket broadcast: scan_complete event to all connected frontends

    The scan does NOT generate briefs. Briefs are generated on-demand when
    the analyst clicks an AoI or runs an explicit Watch. The scan only
    produces composite events and AoIs.
    """

    def __init__(
        self,
        graph_client,
        llm_provider,
        audit_logger: MerkleAuditLogger,
        ws_manager,          # WebSocket broadcast manager
        scan_interval_hours: int = 6,
    ):
        self.graph = graph_client
        self.llm = llm_provider
        self.audit = audit_logger
        self.ws = ws_manager
        self.scan_interval_hours = scan_interval_hours
        self.fusion = FusionEngine()
        self.ingestion = GraphIngestion(graph_client)
        self.aoi_agent = AoIAgent(graph_client, llm_provider, audit_logger)

    async def run_scan(self, triggered_by: str = "scheduler") -> ScanState:
        scan_id = f"scan-{uuid.uuid4().hex[:10]}"
        state = ScanState(
            scan_id=scan_id,
            started_at=datetime.utcnow(),
            triggered_by=triggered_by,
            status=ScanStatus.RUNNING,
        )

        await self.ws.broadcast({"type": "scan_started", "scan_id": scan_id})
        await self.audit.log("scan_started", "scheduler", {"scan_id": scan_id})

        try:
            time_to = datetime.utcnow()
            time_from = time_to - timedelta(hours=self.scan_interval_hours * 4)
            # Fetch 4x the scan interval so the fusion engine has context
            # for temporal correlation (events don't always arrive on time)

            # Step 1: All sensors in parallel
            sensors = build_sensor_registry(domain="multi")
            sensor_tasks = [
                asyncio.wait_for(sensor.fetch(time_from, time_to), timeout=30)
                for sensor in sensors
            ]
            results = await asyncio.gather(*sensor_tasks, return_exceptions=True)

            all_events = []
            sensor_health = []
            for sensor, result in zip(sensors, results):
                if isinstance(result, Exception):
                    sensor_health.append({
                        "name": sensor.name,
                        "icon": sensor.icon,
                        "status": "error",
                        "events_found": 0,
                        "error_message": str(result)[:200],
                    })
                else:
                    all_events.extend(result)
                    sensor_health.append({
                        "name": sensor.name,
                        "icon": sensor.icon,
                        "status": "ok",
                        "events_found": len(result),
                        "error_message": None,
                    })

            state.sensor_health = sensor_health
            await self.ws.broadcast({
                "type": "sensors_complete",
                "scan_id": scan_id,
                "event_count": len(all_events),
                "sensor_health": sensor_health,
            })

            # Step 2: Fusion → composite events
            composite_events = self.fusion.fuse_all(all_events)
            await self.ws.broadcast({
                "type": "fusion_complete",
                "scan_id": scan_id,
                "composite_count": len(composite_events),
            })

            # Step 3: Ingest into Neo4j
            await self.ingestion.ingest_composites(composite_events, scan_id)

            # Step 4: AoI inference
            aois = await self.aoi_agent.infer_aois(
                composite_events=composite_events,
                scan_id=scan_id,
            )
            await self.ws.broadcast({
                "type": "aois_ready",
                "scan_id": scan_id,
                "aoi_count": len(aois),
                "aois": [a.to_geojson_feature() for a in aois],
            })

            state.status = ScanStatus.COMPLETE
            state.completed_at = datetime.utcnow()
            state.aoi_count = len(aois)
            state.composite_count = len(composite_events)

        except Exception as e:
            logger.error("scan_failed", scan_id=scan_id, error=str(e))
            state.status = ScanStatus.FAILED
            state.error_message = str(e)

        await self.audit.log("scan_complete", "scheduler", state.dict())
        return state
```

### `backend/scan/scheduler.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.scan.runner import ScanRunner

def start_scheduler(runner: ScanRunner, interval_hours: int = 6):
    """
    Starts the standing scan scheduler.
    Also adds a FastAPI startup hook so the first scan fires immediately
    (not after the first interval) — the analyst sees AoIs the moment they open the app.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        runner.run_scan,
        trigger="interval",
        hours=interval_hours,
        id="standing_scan",
        max_instances=1,   # Never run two scans simultaneously
        coalesce=True,     # If a run was missed, run once not multiple times
    )
    scheduler.start()
    return scheduler

# In backend/main.py lifespan:
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     await runner.run_scan(triggered_by="startup")   # immediate first scan
#     scheduler = start_scheduler(runner)
#     yield
#     scheduler.shutdown()
```

---

## PART 3: THE AOI AGENT

**File:** `backend/agents/aoi_agent.py`

This is the most important new component. Read it completely before implementing.

```python
import numpy as np
import json
from datetime import datetime
from typing import Optional
from shapely.geometry import MultiPoint, mapping
from shapely.ops import unary_union
import alphashape
from structlog import get_logger

logger = get_logger()

# HDBSCAN — install: pip install hdbscan
# On Windows: pip install hdbscan --no-build-isolation
# If that fails: pip install scikit-learn-extra (has OPTICS as fallback)
try:
    import hdbscan
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False
    from sklearn.cluster import DBSCAN  # fallback

AOI_NAMING_PROMPT = """You are a Greek military geographic intelligence analyst.
You are given a cluster of composite events from the Damocles intelligence platform.

Cluster data:
- Centroid: {centroid_lat:.4f}°N, {centroid_lon:.4f}°E
- Event count: {event_count}
- Dominant threat grade: {dominant_grade}
- Dominant event types: {dominant_types}
- Sample event summaries (first 3):
{sample_summaries}

Your task: name this Area of Interest.

Rules:
1. name_el: Greek name, ≤4 words, using official Greek geographic terminology
   (Λεκάνη, Θαλάσσιο Πεδίο, Ζώνη, Περιοχή, Νησίδες, etc.)
2. name_en: English name, ≤4 words, professional intelligence style
3. description: One sentence. What is notable about this cluster?
   Be specific. Name the dominant event type and its significance.
4. Do NOT use generic names like "Cluster 7" or "Area of Activity"
5. Use the centroid coordinates to infer the nearest geographic feature
   (island, strait, basin, cape, port) if relevant

Output ONLY valid JSON:
{
  "name_el": "...",
  "name_en": "...",
  "description": "..."
}"""

class AoI:
    """One inferred Area of Interest."""
    def __init__(
        self,
        id: str,
        name_el: str,
        name_en: str,
        description: str,
        polygon_wkt: str,
        centroid: tuple[float, float],    # (lon, lat)
        threat_grade: str,
        threat_summary: str,
        citation_event_ids: list[str],    # composite event IDs that built this AoI
        scan_id: str,
        source: str = "ai",
    ):
        self.id = id
        self.name_el = name_el
        self.name_en = name_en
        self.description = description
        self.polygon_wkt = polygon_wkt
        self.centroid = centroid
        self.threat_grade = threat_grade
        self.threat_summary = threat_summary
        self.citation_event_ids = citation_event_ids
        self.scan_id = scan_id
        self.source = source
        self.created_at = datetime.utcnow()

    def to_geojson_feature(self) -> dict:
        """Returns a GeoJSON Feature for the map layer."""
        from shapely import wkt
        geom = wkt.loads(self.polygon_wkt)
        return {
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "id": self.id,
                "name_el": self.name_el,
                "name_en": self.name_en,
                "description": self.description,
                "threat_grade": self.threat_grade,
                "threat_summary": self.threat_summary,
                "event_count": len(self.citation_event_ids),
                "scan_id": self.scan_id,
                "source": self.source,
                "centroid_lon": self.centroid[0],
                "centroid_lat": self.centroid[1],
            },
        }

class AoIAgent:
    """
    Infers Areas of Interest from composite events.
    Runs after every standing scan. Never called directly by the analyst.

    Pipeline per call to infer_aois():
    1. Extract (lon, lat, threat_grade) from composite events
    2. HDBSCAN clustering on (lon, lat) in geographic space
    3. Per cluster: alpha-shape polygon → centroid → grade → LLM naming
    4. Return list of AoI objects → caller writes to Neo4j
    """

    HDBSCAN_PARAMS = {
        "min_cluster_size": 4,
        "min_samples": 2,
        "cluster_selection_epsilon": 0.3,  # degrees (~30km) — merges very close clusters
        "metric": "haversine",             # correct distance for lat/lon
    }
    ALPHA = 0.5   # Alpha-shape parameter (higher = tighter/more concave)
    BUFFER_DEG = 0.05  # ~5km buffer for degenerate clusters

    def __init__(self, graph_client, llm_provider, audit_logger):
        self.graph = graph_client
        self.llm = llm_provider
        self.audit = audit_logger

    async def infer_aois(
        self,
        composite_events: list[dict],
        scan_id: str,
    ) -> list[AoI]:
        if len(composite_events) < self.HDBSCAN_PARAMS["min_cluster_size"]:
            logger.info("aoi_inference_skipped", reason="too_few_events",
                        count=len(composite_events))
            return []

        # Step 1: Extract points
        # NOTE: HDBSCAN with haversine metric expects (lat, lon) in RADIANS
        coords_deg = np.array([
            [e["centroid_lat"], e["centroid_lon"]]
            for e in composite_events
            if e.get("centroid_lat") and e.get("centroid_lon")
        ])
        coords_rad = np.radians(coords_deg)

        # Step 2: Cluster
        if HAS_HDBSCAN:
            clusterer = hdbscan.HDBSCAN(**self.HDBSCAN_PARAMS)
            labels = clusterer.fit_predict(coords_rad)
        else:
            # Fallback to DBSCAN if hdbscan not installed
            clusterer = DBSCAN(
                eps=np.radians(0.3),  # 0.3 degrees in radians
                min_samples=self.HDBSCAN_PARAMS["min_samples"],
                metric="haversine"
            )
            labels = clusterer.fit_predict(coords_rad)

        unique_labels = set(labels) - {-1}  # -1 is noise
        logger.info("hdbscan_complete", clusters=len(unique_labels),
                    noise_points=int(np.sum(labels == -1)))

        # Step 3: Per-cluster processing
        aois = []
        for label in unique_labels:
            mask = labels == label
            cluster_events = [e for e, m in zip(composite_events, mask) if m]
            cluster_coords = coords_deg[mask]  # Back to degrees for shapely

            try:
                aoi = await self._build_aoi(cluster_events, cluster_coords, scan_id, label)
                if aoi:
                    aois.append(aoi)
            except Exception as e:
                logger.error("aoi_build_failed", cluster=label, error=str(e))
                continue

        # Write AoIs to Neo4j
        for aoi in aois:
            await self._persist_aoi(aoi)

        await self.audit.log("aois_inferred", "aoi_agent", {
            "scan_id": scan_id,
            "aoi_count": len(aois),
            "composite_count": len(composite_events),
        })

        return aois

    async def _build_aoi(
        self,
        cluster_events: list[dict],
        cluster_coords: np.ndarray,
        scan_id: str,
        label: int,
    ) -> Optional[AoI]:
        import uuid

        # Polygon: alpha-shape with convex hull fallback
        # Coordinates for shapely: (lon, lat) pairs
        lonlat_coords = [(c[1], c[0]) for c in cluster_coords]  # flip to lon,lat
        try:
            if len(lonlat_coords) >= 4:
                polygon = alphashape.alphashape(lonlat_coords, self.ALPHA)
                if polygon.is_empty or polygon.geom_type not in ("Polygon", "MultiPolygon"):
                    raise ValueError("degenerate alpha-shape")
            else:
                raise ValueError("too few points for alpha-shape")
        except Exception:
            # Fallback: convex hull with buffer
            mp = MultiPoint(lonlat_coords)
            polygon = mp.convex_hull.buffer(self.BUFFER_DEG)

        centroid = polygon.centroid
        centroid_lon, centroid_lat = centroid.x, centroid.y

        # Threat grade: maximum grade among cluster events
        grade_order = {"RED": 3, "AMBER": 2, "GREEN": 1}
        dominant_grade = max(
            (e.get("threat_grade", "GREEN") for e in cluster_events),
            key=lambda g: grade_order.get(g, 0)
        )

        # Dominant event types
        from collections import Counter
        type_counts = Counter(e.get("dominant_type", "unknown") for e in cluster_events)
        dominant_types = [t for t, _ in type_counts.most_common(3)]

        # Sample summaries for LLM prompt
        sample_summaries = "\n".join(
            f"  - {e.get('summary', 'No summary')[:100]}"
            for e in cluster_events[:3]
        )

        # LLM naming
        try:
            from backend.llm.base import LLMMessage
            response = await self.llm.complete(
                messages=[
                    LLMMessage(
                        role="user",
                        content=AOI_NAMING_PROMPT.format(
                            centroid_lat=centroid_lat,
                            centroid_lon=centroid_lon,
                            event_count=len(cluster_events),
                            dominant_grade=dominant_grade,
                            dominant_types=", ".join(dominant_types),
                            sample_summaries=sample_summaries,
                        )
                    )
                ],
                temperature=0.3,
                max_tokens=200,
                json_mode=True,
            )
            naming = json.loads(response.content)
            name_el = naming.get("name_el", f"Συστάδα {label}")
            name_en = naming.get("name_en", f"Cluster {label}")
            description = naming.get("description", "")
        except Exception as e:
            logger.warning("aoi_naming_failed", error=str(e))
            name_el = f"Συστάδα {label}"
            name_en = f"Cluster {label}"
            description = f"{len(cluster_events)} composite events"

        threat_summary = (
            f"{len(cluster_events)} composite events, "
            f"peak threat {dominant_grade}, "
            f"dominant: {', '.join(dominant_types[:2])}"
        )

        return AoI(
            id=f"aoi-{uuid.uuid4().hex[:10]}",
            name_el=name_el,
            name_en=name_en,
            description=description,
            polygon_wkt=polygon.wkt,
            centroid=(centroid_lon, centroid_lat),
            threat_grade=dominant_grade,
            threat_summary=threat_summary,
            citation_event_ids=[e["id"] for e in cluster_events],
            scan_id=scan_id,
            source="ai",
        )

    async def _persist_aoi(self, aoi: AoI):
        """Write AoI to Neo4j with [:CONTAINS] edges to composite events."""
        await self.graph.run("""
            MERGE (a:AreaOfInterest {id: $id})
            SET a.name_el = $name_el,
                a.name_en = $name_en,
                a.description = $description,
                a.polygon_wkt = $polygon_wkt,
                a.centroid_lon = $centroid_lon,
                a.centroid_lat = $centroid_lat,
                a.threat_grade = $threat_grade,
                a.threat_summary = $threat_summary,
                a.scan_id = $scan_id,
                a.source = $source,
                a.created_at = datetime()
        """, **aoi.__dict__ | {
            "centroid_lon": aoi.centroid[0],
            "centroid_lat": aoi.centroid[1],
        })

        # Create [:CONTAINS] edges from AoI to all its composite events
        for event_id in aoi.citation_event_ids:
            await self.graph.run("""
                MATCH (a:AreaOfInterest {id: $aoi_id})
                MATCH (c:CompositeEvent {id: $event_id})
                MERGE (a)-[:CONTAINS {since: datetime()}]->(c)
            """, aoi_id=aoi.id, event_id=event_id)
```

---

## PART 4: USER-DRAWN AOIs — terra-draw INTEGRATION

The analyst can draw their own AoIs on the map. User-drawn AoIs persist across
scans (`scan_id = NULL`). They use the same schema, same graph node, same API.

**New dependency:**
```json
"terra-draw": "^1.0.0"
```

**`backend/api/aoi.py`** — API endpoints

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/aoi", tags=["aoi"])

class UserAoICreate(BaseModel):
    polygon_geojson: dict    # GeoJSON Polygon geometry from terra-draw
    name_el: str
    name_en: str
    description: str = ""

@router.get("/")
async def list_aois(scan_id: str = None) -> list[dict]:
    """
    Returns all current AoIs as GeoJSON features.
    If scan_id is provided, filters to that scan's AI-inferred AoIs.
    Always includes user-drawn AoIs (scan_id = NULL).
    """
    ...

@router.post("/")
async def create_user_aoi(payload: UserAoICreate) -> dict:
    """Creates a user-drawn AoI. Writes to Neo4j with source='user'."""
    ...

@router.delete("/{aoi_id}")
async def delete_aoi(aoi_id: str) -> dict:
    """
    Deletes an AoI. Only source='user' AoIs can be deleted via API.
    AI-inferred AoIs are deleted automatically when a new scan runs.
    """
    ...

@router.get("/{aoi_id}/brief")
async def get_aoi_brief(aoi_id: str) -> dict:
    """
    Generates an intelligence brief scoped to one AoI.
    This is the primary way analysts read briefs in the new model.
    The brief is generated over the AoI's composite events — not a fresh Watch.
    """
    ...

@router.get("/{aoi_id}/dna")
async def get_aoi_dna(aoi_id: str) -> dict:
    """
    Returns the subgraph for Information DNA visualization.
    Scoped to this AoI's composite events and their constituent sensor events.
    """
    ...
```

**`frontend/src/components/DrawingToolbar.tsx`**

```tsx
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawLeafletAdapter } from "terra-draw-leaflet-adapter";

// Toolbar appears top-right of the map panel
// Three buttons: Draw Polygon | Cancel | Save
// When Save is clicked: POST /api/aoi with the drawn polygon
// Analyst must provide name_el and name_en in a small modal before saving

const DrawingToolbar: React.FC<{map: L.Map}> = ({ map }) => {
  const [isDrawing, setIsDrawing] = useState(false);
  const [pendingPolygon, setPendingPolygon] = useState<GeoJSON.Polygon | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);

  const startDrawing = () => {
    drawRef.current = new TerraDraw({
      adapter: new TerraDrawLeafletAdapter({ lib: L, map }),
      modes: [new TerraDrawPolygonMode()],
    });
    drawRef.current.start();
    drawRef.current.setMode("polygon");
    setIsDrawing(true);
  };

  // On polygon complete: store geometry, open naming modal
  // Cyan polygon colour to differentiate from AI-inferred amber polygons
  ...
};
```

---

## PART 5: NEW SENSORS — ALIGNED WITH AOI PIPELINE

All sensors below implement `BaseSensor` and output `SensorEvent` objects.
The fusion engine and graph ingestion work without modification.

**Critical alignment notes:**

- Every `SensorEvent` must have a precise `lat`/`lon` so it can contribute to
  HDBSCAN clustering. Country-level signals (OCHA HAPI, Polymarket) are
  assigned country-centroid coordinates and flagged `is_point_estimate=True`.
  They can still form composites but are weighted lower in the clustering.

- **Submarine cables** output static `CableInfrastructure` nodes, not time-windowed
  `SensorEvent` objects. They do not participate in HDBSCAN. They are overlaid
  on the map independently. When a composite event forms within 20km of a cable
  landing station, the fusion engine adds a `[:NEAR_INFRASTRUCTURE]` edge.

- **GPSJAM** outputs `SensorEvent` objects with precise hex centroids.
  They DO participate in HDBSCAN — jamming zones cluster into AoIs just like
  vessel detections do. A RED GPSJAM AoI over the central Aegean is a legitimate
  operational finding.

### Sensor 1 — USGS Earthquakes

File: `backend/sensors/earthquake.py`

```python
class EarthquakeSensor(BaseSensor):
    name = "USGS Earthquakes"
    icon = "⚡"
    BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

    async def fetch(self, time_from, time_to) -> list[SensorEvent]:
        # Query with precise bbox — events outside Greece bbox return to
        # fusion engine which filters during composite building
        params = {
            "format": "geojson",
            "starttime": time_from.isoformat(),
            "endtime": time_to.isoformat(),
            "minmagnitude": 4.5,
            "minlongitude": 17.0,  # Extended neighbor bbox
            "minlatitude": 31.0,
            "maxlongitude": 37.0,
            "maxlatitude": 45.0,
            "orderby": "time",
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(self.BASE_URL, params=params, timeout=10)
            r.raise_for_status()

        events = []
        for feat in r.json().get("features", []):
            p = feat["properties"]
            c = feat["geometry"]["coordinates"]
            mag = p["mag"]
            events.append(SensorEvent(
                id=feat["id"],
                type="quake",
                strand="physical",
                lat=c[1], lon=c[0],
                timestamp=datetime.utcfromtimestamp(p["time"] / 1000),
                confidence=0.95,
                threat_grade="RED" if mag >= 6.0 else ("AMBER" if mag >= 5.0 else "GREEN"),
                label=f"M{mag:.1f} — {p['place']}",
                source_url=p["url"],
                raw_evidence={"magnitude": mag, "depth_km": c[2],
                              "felt": p.get("felt"), "tsunami": p.get("tsunami")},
                metadata={"magnitude": mag},
                is_point_estimate=False,   # Precise location
            ))
        return events
```

### Sensor 2 — NASA FIRMS (Wildfires)

File: `backend/sensors/wildfire.py`

```python
class WildfireSensor(BaseSensor):
    name = "NASA FIRMS"
    icon = "🔥"
    BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def fetch(self, time_from, time_to) -> list[SensorEvent]:
        days = min(max(1, (time_to - time_from).days), 10)
        bbox = "17.0,31.0,37.0,45.0"  # Extended bbox, west,south,east,north
        url = f"{self.BASE_URL}/{self.api_key}/VIIRS_NOAA20_NRT/{bbox}/{days}"

        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=30)
            r.raise_for_status()

        events = []
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return events

        headers = lines[0].split(",")
        for line in lines[1:]:
            row = dict(zip(headers, line.split(",")))
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
                frp = float(row.get("frp", 0))
                conf = row.get("confidence", "nominal")
                conf_map = {"low": 0.4, "nominal": 0.7, "high": 0.92}
                acq_date = row.get("acq_date", "")
                acq_time = row.get("acq_time", "0000").zfill(4)
                timestamp = datetime.strptime(
                    f"{acq_date} {acq_time[:2]}:{acq_time[2:]}", "%Y-%m-%d %H:%M"
                )
                events.append(SensorEvent(
                    id=f"firms_{lat}_{lon}_{acq_date}",
                    type="fire",
                    strand="physical",
                    lat=lat, lon=lon,
                    timestamp=timestamp,
                    confidence=conf_map.get(conf, 0.7),
                    threat_grade="RED" if frp > 100 else ("AMBER" if frp > 20 else "GREEN"),
                    label=f"Wildfire — FRP {frp:.0f} MW",
                    source_url=f"https://firms.modaps.eosdis.nasa.gov/map/#d:24hrs;@{lon},{lat},10z",
                    raw_evidence={"frp_mw": frp, "confidence": conf, "satellite": row.get("satellite")},
                    metadata={"frp_mw": frp},
                    is_point_estimate=False,
                ))
            except (ValueError, KeyError):
                continue
        return events
```

### Sensor 3 — GDACS

File: `backend/sensors/disaster.py`

```python
class DisasterSensor(BaseSensor):
    name = "GDACS"
    icon = "🌐"
    RSS_URL = "https://www.gdacs.org/xml/rss.xml"

    async def fetch(self, time_from, time_to) -> list[SensorEvent]:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Damocles/1.0 (sovereign-intel-platform)"},
            timeout=15
        ) as client:
            r = await client.get(self.RSS_URL)
            r.raise_for_status()

        import xml.etree.ElementTree as ET
        from email.utils import parsedate_to_datetime

        root = ET.fromstring(r.content)
        ns = {
            "gdacs": "http://www.gdacs.org",
            "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
        }
        events = []
        for item in root.findall(".//item"):
            try:
                lat_el = item.find("geo:lat", ns)
                lon_el = item.find("geo:long", ns)
                if lat_el is None or lon_el is None:
                    continue
                lat, lon = float(lat_el.text), float(lon_el.text)
                # Use extended bbox — GDACS covers the broader region
                if not (31.0 <= lat <= 45.0 and 17.0 <= lon <= 37.0):
                    continue
                alert_el = item.find("gdacs:alertlevel", ns)
                alert = (alert_el.text or "GREEN").upper()
                grade_map = {"GREEN": ("GREEN", 0.5), "ORANGE": ("AMBER", 0.8), "RED": ("RED", 0.95)}
                threat_grade, confidence = grade_map.get(alert, ("GREEN", 0.5))
                pub_date_str = item.findtext("pubDate", "")
                try:
                    timestamp = parsedate_to_datetime(pub_date_str).replace(tzinfo=None)
                except Exception:
                    timestamp = datetime.utcnow()
                if timestamp < time_from or timestamp > time_to:
                    continue
                events.append(SensorEvent(
                    id=f"gdacs_{lat}_{lon}_{pub_date_str[:10]}",
                    type="quake",
                    strand="physical",
                    lat=lat, lon=lon,
                    timestamp=timestamp,
                    confidence=confidence,
                    threat_grade=threat_grade,
                    label=f"GDACS {alert}: {item.findtext('title', '')[:80]}",
                    source_url=item.findtext("link", ""),
                    raw_evidence={"alert": alert, "title": item.findtext("title", "")},
                    metadata={"gdacs_alert": alert},
                    is_point_estimate=False,
                ))
            except (ValueError, AttributeError):
                continue
        return events
```

### Sensor 4 — ACLED

File: `backend/sensors/conflict.py`

```python
class ConflictSensor(BaseSensor):
    name = "ACLED"
    icon = "⚔"
    BASE_URL = "https://api.acleddata.com/acled/read"
    TARGET_COUNTRIES = "Greece|Turkey|Albania|Bulgaria|Macedonia|Libya|Cyprus|Syria"

    def __init__(self, email: str, access_token: str):
        self.email = email
        self.access_token = access_token

    async def fetch(self, time_from, time_to) -> list[SensorEvent]:
        params = {
            "email": self.email,
            "access_token": self.access_token,
            "country": self.TARGET_COUNTRIES,
            "event_date": f"{time_from.strftime('%Y-%m-%d')}|{time_to.strftime('%Y-%m-%d')}",
            "event_date_where": "BETWEEN",
            "limit": 500,
            "fields": "event_id_cnty|event_date|event_type|sub_event_type|actor1|actor2|"
                      "country|admin1|location|latitude|longitude|fatalities|notes|source",
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(self.BASE_URL, params=params, timeout=20)
            r.raise_for_status()

        events = []
        for row in r.json().get("data", []):
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
                fatalities = int(row.get("fatalities", 0))
                event_type = row.get("event_type", "")
                threat_grade = ("RED" if fatalities > 5 else "AMBER") if fatalities > 0 else "GREEN"
                confidence = 0.85 if fatalities > 0 else 0.65
                timestamp = datetime.strptime(row["event_date"], "%Y-%m-%d")
                actors = " vs ".join(filter(None, [row.get("actor1"), row.get("actor2")]))
                events.append(SensorEvent(
                    id=f"acled_{row['event_id_cnty']}",
                    type="conflict",
                    strand="information",
                    lat=lat, lon=lon,
                    timestamp=timestamp,
                    confidence=confidence,
                    threat_grade=threat_grade,
                    label=f"{event_type}: {actors[:50]}" if actors else event_type,
                    source_url=row.get("source", ""),
                    raw_evidence={
                        "event_type": event_type,
                        "actor1": row.get("actor1"),
                        "actor2": row.get("actor2"),
                        "fatalities": fatalities,
                        "notes": row.get("notes", "")[:500],
                        "country": row.get("country"),
                    },
                    metadata={"fatalities": fatalities, "event_type": event_type},
                    is_point_estimate=False,
                ))
            except (ValueError, KeyError):
                continue
        return events
```

### Sensor 5 — GPSJAM

File: `backend/sensors/gps_jamming.py`

```python
class GPSJammingSensor(BaseSensor):
    name = "GPSJAM"
    icon = "📡"
    BASE_URL = "https://gpsjam.org/geo.json"
    CACHE_DIR = Path("data/cache/gpsjam")
    # Greece + Aegean bbox for filtering hexes
    FILTER_BBOX = {"min_lon": 19.0, "min_lat": 34.0, "max_lon": 30.0, "max_lat": 43.0}

    async def fetch(self, time_from, time_to) -> list[SensorEvent]:
        target_date = (time_to - timedelta(days=1)).date()
        cache_file = self.CACHE_DIR / f"{target_date}.json"

        if cache_file.exists():
            geojson = json.loads(cache_file.read_text())
        else:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(headers={"User-Agent": "Damocles/1.0"}, timeout=30) as client:
                r = await client.get(self.BASE_URL, params={"date": target_date.isoformat()})
                r.raise_for_status()
                geojson = r.json()
            cache_file.write_text(json.dumps(geojson))

        events = []
        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            pct_bad = float(props.get("pct_bad", 0))
            if pct_bad < 0.02:
                continue
            coords = feature["geometry"].get("coordinates", [[[]]])[0]
            if not coords:
                continue
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            centroid_lon = sum(lons) / len(lons)
            centroid_lat = sum(lats) / len(lats)
            if not (self.FILTER_BBOX["min_lat"] <= centroid_lat <= self.FILTER_BBOX["max_lat"] and
                    self.FILTER_BBOX["min_lon"] <= centroid_lon <= self.FILTER_BBOX["max_lon"]):
                continue
            threat_grade = "RED" if pct_bad > 0.10 else "AMBER"
            events.append(SensorEvent(
                id=f"gpsjam_{target_date}_{centroid_lat:.2f}_{centroid_lon:.2f}",
                type="gps_jam",
                strand="physical",
                lat=centroid_lat, lon=centroid_lon,
                timestamp=datetime.combine(target_date, datetime.min.time()),
                confidence=0.80 if pct_bad > 0.10 else 0.60,
                threat_grade=threat_grade,
                label=f"GPS jamming — {pct_bad*100:.0f}% aircraft affected",
                source_url=f"https://gpsjam.org/?lat={centroid_lat:.2f}&lon={centroid_lon:.2f}&z=8",
                raw_evidence={"pct_bad": pct_bad, "pct_yellow": float(props.get("pct_yellow", 0)),
                              "date": target_date.isoformat()},
                metadata={"pct_bad": pct_bad},
                is_point_estimate=False,  # Hex centroid is a real location
            ))
        return events
```

### Sensors 6-11 — Abbreviated (same pattern, implement in order)

**Sensor 6 — IMF PortWatch** (`backend/sensors/portwatch.py`):
- Fetch `Daily_Chokepoints_Data` for chokepoint4 (Turkish Straits) and chokepoint1 (Suez)
- Compute deviation from rolling mean, flag >30% change as AMBER
- Fixed coordinates for known chokepoints
- `is_point_estimate=False` (chokepoints are precise geographic features)

**Sensor 7 — NASA EONET** (`backend/sensors/eonet.py`):
- Fetch wildfire, severe storm, earthquake, volcano events for extended bbox
- For Polygon geometries: compute centroid for HDBSCAN, preserve full polygon in `raw_evidence`
- `is_point_estimate=False`

**Sensor 8 — UN OCHA HAPI** (`backend/sensors/migration.py`):
- Fetch refugee population for GRC, TUR, CYP
- Fixed country centroid coordinates
- `is_point_estimate=True` — country-level aggregate, lower HDBSCAN weight
- Does NOT form standalone AoIs; enriches existing ones as context

**Sensor 9 — Cloudflare Radar** (`backend/sensors/internet_outage.py`):
- Traffic anomaly for GR, TR, CY
- Fixed country centroid coordinates
- `is_point_estimate=True`
- Feeds AoI brief as context, lower clustering weight

**Sensor 10 — Submarine Cable** (`backend/sensors/submarine_cable.py`):
- Static GeoJSON download from TeleGeography GitHub
- Returns `CableInfrastructureEvent` subtype — NOT standard `SensorEvent`
- Does NOT participate in HDBSCAN
- Fusion engine adds `[:NEAR_INFRASTRUCTURE]` edges when composites form within 20km

**Sensor 11 — Polymarket** (`backend/sensors/prediction_markets.py`):
- Fetch active markets tagged with relevant geopolitical terms
- Fixed coordinate (Athens centroid — abstract signal)
- `is_point_estimate=True`
- Explicitly excluded from HDBSCAN (flagged `participates_in_clustering=False`)
- Injected directly into AoI Agent naming prompt as context signal

---

## PART 6: UPDATED NEO4J SCHEMA

Add to existing schema. All existing node types unchanged.

```cypher
-- New node type
(:AreaOfInterest {
    id: string,           -- "aoi-b25d041daf"
    name_el: string,      -- "Λεκάνη Λήμνου"
    name_en: string,      -- "Lemnos Basin"
    description: string,
    polygon_wkt: string,  -- Full WKT polygon
    centroid_lon: float,
    centroid_lat: float,
    threat_grade: string, -- GREEN | AMBER | RED
    threat_summary: string,
    scan_id: string,      -- null for user-drawn
    source: string,       -- "ai" | "user"
    created_at: datetime,
    updated_at: datetime
})

-- New edge types
(:AreaOfInterest)-[:CONTAINS {since: datetime}]->(:CompositeEvent)
(:CompositeEvent)-[:NEAR_INFRASTRUCTURE {distance_km: float}]->(:CableInfrastructure)
(:AreaOfInterest)-[:SUPERSEDES {reason: string}]->(:AreaOfInterest)
-- SUPERSEDES: when a new scan's AoI covers approximately the same area
-- as a prior scan's AoI, link them for temporal tracking

-- New node types for new sensors
(:CableInfrastructure {
    id: string,
    landing_name: string,
    lat: float, lon: float,
    cable_count: integer,
    cables: list[string],
    is_static: boolean
})

(:EarthquakeEvent {id, lat, lon, timestamp, magnitude, depth_km, place, threat_grade, confidence, source_url})
(:WildfireEvent {id, lat, lon, timestamp, frp_mw, confidence_level, threat_grade, source_url})
(:ConflictEvent {id, lat, lon, timestamp, event_type, actor1, actor2, fatalities, country, threat_grade})
(:GPSJammingEvent {id, lat, lon, date, pct_bad, threat_grade})
(:PortEvent {id, port_id, port_name, lat, lon, timestamp, call_sign_count, deviation_pct, threat_grade})
```

**New Cypher queries to implement in `backend/graph/queries.py`:**

```cypher
-- Get all AoIs for the map layer (most recent scan)
MATCH (a:AreaOfInterest)
WHERE a.scan_id = $scan_id OR a.source = 'user'
RETURN a
ORDER BY a.threat_grade DESC, a.created_at DESC

-- Get AoI subgraph for Information DNA
MATCH (a:AreaOfInterest {id: $aoi_id})-[:CONTAINS]->(c:CompositeEvent)
OPTIONAL MATCH (c)-[:COMPOSED_OF]->(source)
RETURN a, collect(c) as composites, collect(source) as sources

-- The analyst's power query: dark vessels in an AoI
MATCH (a:AreaOfInterest {name_el: $name})-[:CONTAINS]->(c:CompositeEvent)
      -[:COMPOSED_OF]->(v:Vessel)
WHERE v.ais_status = 'dark'
RETURN v.mmsi, v.timestamp, v.lat, v.lon, c.threat_grade
ORDER BY c.threat_grade DESC

-- AoI temporal tracking: same area across scans
MATCH (a1:AreaOfInterest)-[:SUPERSEDES]->(a2:AreaOfInterest)
WHERE a1.name_en = $name
RETURN a1, a2 ORDER BY a1.created_at DESC
```

---

## PART 7: FRONTEND — AoI-FIRST LAYOUT

### Layout change

The interface no longer opens on a "run a Watch" prompt. It opens showing the map
with AoI polygons already rendered from the most recent scan.

```
┌─────────────────────────────────────────────────────────────────┐
│  DAMOCLES  [Scan: 14 min ago] [11 sensors] [SENSOR STATUS BAR]  │
├────────────────────────┬─────────────────────────────────────────┤
│                        │                                         │
│    MAP (full left)     │    RIGHT PANEL (context-dependent)      │
│                        │                                         │
│  AoI polygons render   │    Default: AoI LIST                    │
│  here immediately on   │    (when no AoI is selected)            │
│  load from last scan   │                                         │
│                        │    AoI selected: BRIEF + DNA            │
│  [Draw] button top-R   │    (two tabs: Brief | Information DNA)  │
│                        │                                         │
│  Layer controls        │    Watch tab: free-text query           │
│                        │    (original Watch functionality)        │
├────────────────────────┴─────────────────────────────────────────┤
│  SENSOR STATUS BAR — 11 sensors, coverage %, last updated        │
└─────────────────────────────────────────────────────────────────┘
```

The Watch input is now a **tab in the right panel**, not the primary interface.
It's for ad-hoc investigation after the analyst has reviewed the AoIs.

### AoI polygon visual language

```typescript
const AOI_COLORS = {
  ai: {
    GREEN:  { fill: "rgba(34,197,94,0.12)",  stroke: "#22c55e", strokeWidth: 1.5 },
    AMBER:  { fill: "rgba(245,158,11,0.15)", stroke: "#f59e0b", strokeWidth: 2 },
    RED:    { fill: "rgba(239,68,68,0.18)",  stroke: "#ef4444", strokeWidth: 2.5 },
  },
  user: {
    GREEN:  { fill: "rgba(0,212,255,0.12)",  stroke: "#00d4ff", strokeWidth: 1.5 },
    AMBER:  { fill: "rgba(0,212,255,0.15)",  stroke: "#00d4ff", strokeWidth: 2 },
    RED:    { fill: "rgba(0,212,255,0.18)",  stroke: "#00d4ff", strokeWidth: 2.5 },
  },
};
// AI-inferred: amber/red/green based on threat grade
// User-drawn: always cyan (same hue regardless of threat grade)
// Pulsing animation on RED AoIs: CSS keyframes on stroke-opacity 0.5→1→0.5
```

### AoI polygon interaction

```
Click polygon:
  → Right panel switches to "AoI Detail" view
  → Shows: name_el, name_en, threat_grade, description, event_count
  → Two buttons: "Read Brief" | "View DNA"
  → Polygon highlights (fill opacity increases)
  → Other polygons dim to 30% opacity

"Read Brief":
  → POST /api/aoi/{id}/brief
  → Brief generates over that AoI's composite events
  → Same brief format as before but scoped to AoI
  → Citation chain still works — clicks still highlight DNA

"View DNA":
  → GET /api/aoi/{id}/dna
  → Information DNA panel loads with AoI's subgraph
  → The helix shows only the nodes inside this AoI
  → Composite events = large nodes centered between strands
  → Sensor events = smaller nodes on appropriate strand
  → Organelles = raw evidence (same as before)

Hover polygon:
  → Tooltip: name_el | name_en | threat_grade badge | event count
  → No click required to see this
```

### AoI list panel (default right panel view)

```tsx
const AoIListPanel: React.FC<{aois: AoI[]}> = ({ aois }) => {
  const sorted = [...aois].sort((a, b) => {
    const gradeOrder = { RED: 3, AMBER: 2, GREEN: 1 };
    return gradeOrder[b.threat_grade] - gradeOrder[a.threat_grade];
  });

  return (
    <div className="aoi-list">
      <div className="aoi-list-header">
        <span className="aoi-count">{aois.length} Areas of Interest</span>
        <span className="scan-age">Scan: {formatDistanceToNow(lastScanAt)} ago</span>
      </div>
      {sorted.map(aoi => (
        <div
          key={aoi.id}
          className={`aoi-card aoi-card--${aoi.threat_grade.toLowerCase()}`}
          onClick={() => selectAoI(aoi)}
        >
          <div className="aoi-card-header">
            <ThreatGradeBadge grade={aoi.threat_grade} />
            <span className="aoi-name-el">{aoi.name_el}</span>
            <span className="aoi-name-en">{aoi.name_en}</span>
          </div>
          <div className="aoi-description">{aoi.description}</div>
          <div className="aoi-meta">
            <span>{aoi.event_count} events</span>
            <span>{aoi.source === "ai" ? "AI-inferred" : "User-drawn"}</span>
          </div>
        </div>
      ))}
    </div>
  );
};
```

---

## PART 8: INFORMATION DNA — SCOPED TO AOI

The DNA visualization is unchanged in its visual language (Interpretation A: double
helix with nodes on strands). What changes is its scope and data source.

**Before:** DNA showed the global knowledge graph from a Watch run.
**After:** DNA shows the subgraph of one selected AoI.

```
AoI selected → GET /api/aoi/{id}/dna →
{
  "nodes": [
    // CompositeEvent nodes — larger, centered between strands
    { "id": "ce-001", "type": "composite", "strand": "center",
      "threat_grade": "RED", "label": "AIS-dark vessel + news corroboration",
      "confidence": 0.88, "organelles": [...] },

    // Sensor event nodes — smaller, on appropriate strand
    { "id": "vessel-007", "type": "vessel", "strand": "physical",
      "threat_grade": "AMBER", "label": "AIS-dark vessel 36.2°N",
      "confidence": 0.87, "organelles": [
        { "id": "sar-tile-001", "source_type": "SAR_TILE",
          "label": "Sentinel-1 tile 2024-03-14 03:22 UTC" }
      ]},
    { "id": "news-023", "type": "news", "strand": "information",
      "label": "Kathimerini: Turkish vessel near Rhodes",
      "confidence": 0.75, "organelles": [...] },
  ],
  "edges": [
    // [:CONTAINS] from composite to sensor events — renders as node grouping
    { "source": "ce-001", "target": "vessel-007", "edge_type": "composed_of",
      "is_base_pair": false },
    // [:CORROBORATES] between events on different strands — renders as base pairs
    { "source": "vessel-007", "target": "news-023", "edge_type": "corroborates",
      "corr_score": 0.81, "is_base_pair": true },
  ],
  "aoi_meta": {
    "name_el": "Λεκάνη Λήμνου",
    "threat_grade": "AMBER",
    "event_count": 17,
  }
}
```

**Empty state when no AoI is selected:**
Show the animated idle helix with placeholder nodes and the text:
"Select an Area of Interest to decode its signal"

**New helix visual for AoI scope:** Add a subtle polygon outline at the top of the
DNA panel showing the AoI's shape as a geographic minimap — so the analyst always
knows which polygon they're looking at while scrolling through the helix.

---

## PART 9: DEMO SCRIPT — REWRITTEN FOR AOI-FIRST

This is now a fundamentally better demo. The analyst never has to ask a question.

**[0:00]** "Good morning. Intelligence analysts today ask a question, then wait for an answer. Damocles removes the question. When you open it, the answer is already there."

**[0:20]** Open browser. The map is already showing three polygons — one RED over the northern Aegean, two AMBER over the Evros border zone and off Rhodes. "These polygons appeared automatically at 6am. No analyst ran a query. Damocles's standing scan ran while everyone was asleep."

**[0:45]** Click the RED polygon. Right panel opens: "Λεκάνη Λήμνου — Lemnos Basin. 17 composite events. Peak threat RED." Click "Read Brief." Brief generates in ~8 seconds.

**[1:15]** Brief appears. BLUF: "AIS-dark vessel detected north of Lemnos, corroborated by three independent sources." Click the BLUF sentence. Map highlights the vessel position. DNA panel lights up showing the helix for this AoI. "Every claim traces to its source. One click."

**[2:00]** Switch to "View DNA" tab. The bioluminescent helix renders — two strands, nodes as cells, base pairs connecting corroborated events. "This is the Information DNA of this Area of Interest. Physical signals on the left strand, information signals on the right. Every base pair is a corroboration link." Click a vessel node — organelles orbit revealing SAR tile evidence.

**[2:45]** Click the Devil's Advocate section. "Damocles argues against itself before it tells you anything. The counter-probability is 31% — the vessel may be a fishing boat with a technical AIS failure. The analyst decides, not the machine."

**[3:15]** Back to map. Click "Draw" button. Draw a small polygon around a quiet area of the Ionian. "The analyst can add their own Areas of Interest — same plumbing, same audit trail, their name on it." Type a name. Save. The new cyan polygon appears instantly alongside the AI-inferred amber ones.

**[3:45]** Sensor status bar at the bottom. "Eleven sensors. Nine green, one amber (ACLED 3h stale), one grey (Cloudflare key not set). The analyst always knows exactly what she can and cannot see. No false confidence."

**[4:15]** Audit log panel. "Every scan event, every model call, every analyst action — hash-chained. Any parliamentary committee can verify this log. We are not asking EYP to trust a black box. We are handing them the keys."

**[4:35]** "Palantir requires analysts to ask the right question. Damocles asks the questions for them. That is the difference between a tool and a partner."

**[5:00]** Stop.

---

## PART 10: IMPLEMENTATION ORDER

Do not deviate from this sequence. Each step gates the next.

### Week 1: Standing scan + AoI agent

**Day 1:** Install APScheduler (`pip install apscheduler`). Install HDBSCAN
(`pip install hdbscan` — on Windows use `pip install hdbscan --no-build-isolation`
or build from conda-forge). Install alphashape (`pip install alphashape`).
Install terra-draw (`npm install terra-draw terra-draw-leaflet-adapter`).

**Day 2:** Build `backend/scan/runner.py` and `backend/scan/scheduler.py`.
Wire into FastAPI lifespan. Verify the scheduler fires on startup and the
WebSocket broadcasts `scan_started`.

**Day 3:** Build `backend/agents/aoi_agent.py` with the full HDBSCAN → alpha-shape
→ LLM naming pipeline. Test with synthetic composite events first — create 50 fake
events with Greece coordinates, verify HDBSCAN produces 3-5 meaningful clusters,
verify alpha-shapes look right, verify LLM names are sensible.

**Day 4:** Neo4j schema additions (AoI node, [:CONTAINS] edges, cable infrastructure).
`backend/api/aoi.py` endpoints: GET /, POST /, DELETE /{id}, GET /{id}/brief, GET /{id}/dna.

**Day 5:** No-key sensors: USGS Earthquakes, GDACS, NASA EONET, IMF PortWatch,
Submarine Cable static load. Register NASA FIRMS key (instant). Verify each sensor
returns Greece-scoped events. Verify all events have valid lat/lon for HDBSCAN.

### Week 2: All sensors + frontend AoI layer

**Day 6:** ACLED, NASA FIRMS, GPSJAM, UN OCHA HAPI, Cloudflare Radar, Polymarket.
Sensor registry: `build_sensor_registry()`. Sensor health tracking in scan state.

**Day 7:** Full scan run with all 11 sensors. Verify composite events form correctly.
Verify HDBSCAN produces AoIs. Verify AoIs persist in Neo4j with [:CONTAINS] edges.
Fix any coordinate issues (sensors returning points outside bbox, etc.).

**Day 8-9:** Frontend AoI map layer. GeoJSON polygon rendering with Leaflet
(use `L.geoJSON` with style function for threat-grade colours). Click handlers.
AoI list panel in right panel. Sensor status bar.

**Day 10:** terra-draw integration for user-drawn AoIs. POST /api/aoi endpoint.
Cyan polygon visual differentiation from AI-inferred.

### Week 3: DNA + brief + demo polish

**Day 11-12:** Information DNA D3 implementation scoped to AoI subgraph.
GET /api/aoi/{id}/dna returns the correct node/edge structure.
D3 renders helix with correct strand assignment for new node types.

**Day 13:** AoI brief generation. POST /api/aoi/{id}/brief.
Supervisor agent receives AoI's composite events instead of Watch results.
Citation chain works on AoI-scoped brief.

**Day 14:** Full end-to-end live test. Real scan runs. Real AoIs appear.
Click AoI → brief generates → citation click → DNA highlights. 5-minute demo run.

**Day 15:** Demo rehearsal x3. Fix what breaks under pressure.

---

## PART 11: TESTS

```python
# tests/test_aoi_pipeline.py

async def test_hdbscan_produces_clusters_from_greece_events():
    """Synthetic events across Greece should produce 3-8 clusters."""
    import numpy as np
    synthetic = [
        # Aegean cluster
        {"centroid_lat": 39.0 + np.random.normal(0, 0.3), "centroid_lon": 25.0 + np.random.normal(0, 0.3),
         "threat_grade": "AMBER", "id": f"ce-{i}", "summary": "test", "dominant_type": "vessel"}
        for i in range(10)
    ] + [
        # Evros cluster
        {"centroid_lat": 41.5 + np.random.normal(0, 0.15), "centroid_lon": 26.3 + np.random.normal(0, 0.15),
         "threat_grade": "GREEN", "id": f"ce-ev-{i}", "summary": "test", "dominant_type": "conflict"}
        for i in range(6)
    ] + [
        # Rhodes cluster
        {"centroid_lat": 36.2 + np.random.normal(0, 0.2), "centroid_lon": 28.0 + np.random.normal(0, 0.2),
         "threat_grade": "RED", "id": f"ce-rh-{i}", "summary": "test", "dominant_type": "fire"}
        for i in range(5)
    ]
    aoi_agent = AoIAgent(mock_graph, mock_llm, mock_audit)
    aois = await aoi_agent.infer_aois(synthetic, "test-scan-001")
    assert 2 <= len(aois) <= 5, f"Expected 2-5 clusters, got {len(aois)}"

async def test_aoi_polygon_covers_its_events():
    """Every composite event cited by an AoI must be inside its polygon."""
    from shapely import wkt
    from shapely.geometry import Point
    for aoi in test_aois:
        polygon = wkt.loads(aoi.polygon_wkt)
        for event_id in aoi.citation_event_ids:
            event = get_event(event_id)
            point = Point(event["centroid_lon"], event["centroid_lat"])
            # Buffer 0.1° to account for alpha-shape edge cases
            assert polygon.buffer(0.1).contains(point), f"Event {event_id} outside AoI polygon"

async def test_aoi_has_neo4j_contains_edges():
    """Every AoI must have [:CONTAINS] edges to all its cited composite events."""
    for aoi in test_aois:
        result = await graph.run("""
            MATCH (a:AreaOfInterest {id: $id})-[:CONTAINS]->(c:CompositeEvent)
            RETURN count(c) as count
        """, id=aoi.id)
        db_count = result[0]["count"]
        assert db_count == len(aoi.citation_event_ids)

async def test_user_drawn_aoi_persists_across_scans():
    """User-drawn AoIs must survive the AI AoI cleanup between scans."""
    user_aoi = create_user_aoi(polygon=test_polygon, name_el="Ζώνη Δοκιμής", name_en="Test Zone")
    await run_scan()   # New scan should NOT delete user-drawn AoIs
    surviving = await get_aoi(user_aoi.id)
    assert surviving is not None

async def test_citation_chain_works_through_aoi():
    """Brief section → AoI → CompositeEvent → SensorEvent → raw evidence."""
    aoi = test_aois[0]
    brief = await generate_aoi_brief(aoi.id)
    for section in brief.all_sections():
        for citation_id in section.citation_node_ids:
            chain = await get_citation_chain(brief.id, section.id)
            assert any(n.node_id == citation_id for n in chain.source_nodes)
            assert all(n.map_highlight.lat is not None for n in chain.source_nodes)
```

---

## PART 12: NEW DEPENDENCIES TO ADD

```toml
# Add to pyproject.toml
"hdbscan==0.8.38.post1",         # HDBSCAN clustering
"alphashape==1.3.1",              # Alpha-shape polygon generation
"shapely==2.0.6",                 # Already included — confirms needed
"apscheduler==3.10.4",            # Standing scan scheduler
"scipy==1.13.1",                  # Required by hdbscan + alphashape
```

```json
// Add to package.json
"terra-draw": "^1.0.0",
"terra-draw-leaflet-adapter": "^1.0.0"
```

Windows note: hdbscan on Windows requires:
```powershell
pip install hdbscan --no-build-isolation
# If that fails:
conda install -c conda-forge hdbscan
# Alternative that always works:
pip install scikit-learn-extra  # installs OPTICS as functional fallback
```

---

*Build document version: 3.0*
*Core change: AoI polygon-first philosophy throughout. Standing scan replaces query-first model.*
*11 new sensors all contribute to HDBSCAN clustering or AoI enrichment.*
*Information DNA scoped to selected AoI, not global graph.*
*Demo script rewritten: polygons appear before analyst asks.*
*Gold medal or nothing.*