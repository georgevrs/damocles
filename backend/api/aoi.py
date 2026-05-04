"""Area-of-Interest endpoints.

GET /api/aoi             — list as GeoJSON FeatureCollection (AI + user merged or filtered)
POST /api/aoi            — create an analyst polygon (Day 25 user-drawn flow)
PATCH /api/aoi/{id}      — rename / update description (user only)
DELETE /api/aoi/{id}     — delete (user only — AI AoIs are managed by the agent)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from backend.models.aoi import AoI, AoISource
from backend.store import get_store

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/aoi", tags=["aoi"])


# ────────────────────────── request bodies ──────────────────────────

class CreateAoIBody(BaseModel):
    name_el: str = Field(min_length=1, max_length=80)
    name_en: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=400)
    geometry_geojson: dict[str, Any]


class PatchAoIBody(BaseModel):
    name_el: str | None = Field(default=None, max_length=80)
    name_en: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=400)


# ────────────────────────────── routes ──────────────────────────────

@router.get("")
async def list_aoi(
    source: Literal["ai", "user", "all"] = Query("all"),
) -> dict[str, Any]:
    """List as a GeoJSON FeatureCollection — what the map AoI layer consumes."""
    store = get_store()
    src = None if source == "all" else source
    items = store.list_aoi(source=src)
    features = [_to_feature(a) for a in items]
    return {"type": "FeatureCollection", "features": features}


@router.post("", status_code=201)
async def create_aoi(body: CreateAoIBody) -> dict[str, Any]:
    polygon_wkt = _geojson_to_wkt(body.geometry_geojson)
    if polygon_wkt is None:
        raise HTTPException(status_code=400, detail="geometry_geojson must be a Polygon or MultiPolygon")
    centroid = _centroid_of_wkt(polygon_wkt)
    now = datetime.now(timezone.utc)
    aoi = AoI(
        source=AoISource.USER,
        name_el=body.name_el,
        name_en=body.name_en or body.name_el,
        description=body.description,
        polygon_wkt=polygon_wkt,
        centroid_lat=centroid[1],
        centroid_lon=centroid[0],
        created_at=now,
        updated_at=now,
    )
    get_store().upsert_aoi([aoi])
    return _to_feature(aoi)


@router.patch("/{aoi_id}")
async def patch_aoi(aoi_id: str, body: PatchAoIBody) -> dict[str, Any]:
    store = get_store()
    existing = store.get_aoi(aoi_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="AoI not found")
    if existing.source != AoISource.USER:
        raise HTTPException(status_code=403, detail="Only user-drawn AoIs are editable")
    if body.name_el is not None:
        existing.name_el = body.name_el
    if body.name_en is not None:
        existing.name_en = body.name_en
    if body.description is not None:
        existing.description = body.description
    existing.updated_at = datetime.now(timezone.utc)
    store.upsert_aoi([existing])
    return _to_feature(existing)


@router.delete("/{aoi_id}", status_code=204, response_class=Response)
async def delete_aoi(aoi_id: str) -> Response:
    store = get_store()
    existing = store.get_aoi(aoi_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="AoI not found")
    if existing.source != AoISource.USER:
        raise HTTPException(status_code=403, detail="Only user-drawn AoIs are deletable")
    store.delete_aoi(aoi_id, only_user=True)
    return Response(status_code=204)


# ─────────────────────────── explore ──────────────────────────────────
# Fully self-contained drill-down for the analyst. Returns:
#   - AoI metadata (same as the FeatureCollection entry)
#   - Member composite events with their source-node IDs
#   - Source events (vessels / news / social) referenced by any composite
#   - Graph edges: AoI -[CONTAINS]-> Composite, Composite -[COMPOSED_OF]-> Source
# The frontend uses this to power both BriefPanel and GraphPanel without
# hitting Neo4j (everything reads from DuckDB — fast, sub-second).

import json as _json


@router.get("/{aoi_id}/explore")
async def explore_aoi(aoi_id: str) -> dict[str, Any]:
    store = get_store()
    aoi = store.get_aoi(aoi_id)
    if aoi is None:
        raise HTTPException(status_code=404, detail="AoI not found")

    conn = store.connect()

    # 1. Member composites (filtered by the AoI's citation_event_ids)
    composite_ids = list(aoi.citation_event_ids or [])
    composites: list[dict[str, Any]] = []
    source_id_set: set[str] = set()
    if composite_ids:
        placeholders = ",".join(["?"] * len(composite_ids))
        rows = conn.execute(
            f"""
            SELECT id, threat_grade, confidence, summary,
                   centroid_lat, centroid_lon,
                   time_window_start, time_window_end,
                   source_node_ids_json, created_at, scan_id
              FROM composite_events
             WHERE id IN ({placeholders})
             ORDER BY threat_grade DESC, confidence DESC
            """,
            composite_ids,
        ).fetchall()
        for r in rows:
            try:
                src_ids = _json.loads(r[8] or "[]")
            except (TypeError, ValueError):
                src_ids = []
            source_id_set.update(src_ids)
            composites.append({
                "id":             r[0],
                "threat_grade":   r[1] or "GREEN",
                "confidence":     r[2],
                "summary":        r[3] or "",
                "centroid_lat":   r[4],
                "centroid_lon":   r[5],
                "time_window_start": r[6].isoformat() if r[6] else None,
                "time_window_end":   r[7].isoformat() if r[7] else None,
                "source_node_ids":   src_ids,
                "created_at":     r[9].isoformat() if r[9] else None,
                "scan_id":        r[10],
            })

    # 2. Source events — vessels / news / social — by event_id
    sources: list[dict[str, Any]] = []
    if source_id_set:
        sids = list(source_id_set)
        ph = ",".join(["?"] * len(sids))

        ais_rows = conn.execute(
            f"""
            SELECT event_id, mmsi, ts, lat, lon, vessel_name, ais_status, length_m, payload_json
              FROM raw_ais WHERE event_id IN ({ph})
            """,
            sids,
        ).fetchall()
        for r in ais_rows:
            sources.append({
                "id":      r[0],
                "type":    "Vessel",
                "label":   r[5] or r[1] or r[0][:8],
                "lat":     r[3],
                "lon":     r[4],
                "props": {
                    "mmsi":       r[1],
                    "ts":         r[2].isoformat() if r[2] else None,
                    "ais_status": r[6],
                    "length_m":   r[7],
                },
            })

        news_rows = conn.execute(
            f"""
            SELECT event_id, ts, lat, lon, headline, source_url, source_name, goldstein_scale, mentions
              FROM raw_news WHERE event_id IN ({ph})
            """,
            sids,
        ).fetchall()
        for r in news_rows:
            sources.append({
                "id":      r[0],
                "type":    "NewsEvent",
                "label":   (r[4] or r[6] or r[0][:8])[:64],
                "lat":     r[2],
                "lon":     r[3],
                "props": {
                    "ts":              r[1].isoformat() if r[1] else None,
                    "source_url":      r[5],
                    "source_name":     r[6],
                    "goldstein_scale": r[7],
                    "mentions":        r[8],
                },
            })

        social_rows = conn.execute(
            f"""
            SELECT event_id, channel, ts, lat, lon, text, language, views
              FROM raw_social WHERE event_id IN ({ph})
            """,
            sids,
        ).fetchall()
        for r in social_rows:
            sources.append({
                "id":      r[0],
                "type":    "SocialSignal",
                "label":   r[1] or r[0][:8],
                "lat":     r[3],
                "lon":     r[4],
                "props": {
                    "channel":  r[1],
                    "ts":       r[2].isoformat() if r[2] else None,
                    "text":     (r[5] or "")[:200],
                    "language": r[6],
                    "views":    r[7],
                },
            })

    # 3. Graph nodes + edges (a self-contained subgraph for GraphPanel)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # AoI root node
    nodes.append({
        "id":    aoi.id,
        "type":  "AreaOfInterest",
        "label": aoi.name_el or aoi.name_en or aoi.id[:10],
        "lat":   aoi.centroid_lat,
        "lon":   aoi.centroid_lon,
        "props": {
            "source":       aoi.source.value if hasattr(aoi.source, "value") else str(aoi.source),
            "threat_grade": aoi.threat_grade,
            "name_en":      aoi.name_en,
            "description":  aoi.description,
        },
    })

    for c in composites:
        nodes.append({
            "id":    c["id"],
            "type":  "CompositeEvent",
            "label": (c["summary"][:36] or "composite") if c["summary"] else "composite",
            "lat":   c["centroid_lat"],
            "lon":   c["centroid_lon"],
            "props": {
                "threat_grade":        c["threat_grade"],
                "confidence":          c["confidence"],
                "corroboration_count": len(c["source_node_ids"]),
                "summary":             c["summary"],
            },
        })
        edges.append({"source": aoi.id, "target": c["id"], "type": "CONTAINS"})

    for s in sources:
        nodes.append({
            "id":    s["id"],
            "type":  s["type"],
            "label": s["label"],
            "lat":   s["lat"],
            "lon":   s["lon"],
            "props": s["props"],
        })

    # Composite -[COMPOSED_OF]-> source
    src_ids_seen = {s["id"] for s in sources}
    for c in composites:
        for sid in c["source_node_ids"]:
            if sid in src_ids_seen:
                edges.append({"source": c["id"], "target": sid, "type": "COMPOSED_OF"})

    return {
        "aoi": _to_feature(aoi),
        "composites": composites,
        "sources": sources,
        "graph": {"nodes": nodes, "edges": edges},
    }


# ─────────────────────────── DNA subgraph ──────────────────────────────
# Same shape as /explore's `graph` field but augmented with strand assignment
# (physical | information | center) and base-pair markers between nodes that
# corroborate across strands. Consumed by the InformationDNA frontend component.

@router.get("/{aoi_id}/dna")
async def aoi_dna(aoi_id: str) -> dict[str, Any]:
    explore = await explore_aoi(aoi_id)

    STRAND_FOR_TYPE = {
        "Vessel":         "physical",
        "NewsEvent":      "information",
        "SocialSignal":   "information",
        "CompositeEvent": "center",
        "AreaOfInterest": "center",
    }

    nodes_out: list[dict[str, Any]] = []
    for n in explore["graph"]["nodes"]:
        n2 = dict(n)
        n2["strand"] = STRAND_FOR_TYPE.get(n2.get("type", ""), "center")
        nodes_out.append(n2)

    # Build base-pair markers: a base pair is any pair of source nodes that
    # share a composite parent AND sit on different strands (physical ↔ info).
    composite_to_sources: dict[str, list[dict[str, Any]]] = {}
    for c in explore["composites"]:
        sources = [s for s in explore["sources"] if s["id"] in c["source_node_ids"]]
        composite_to_sources[c["id"]] = sources

    base_pairs: list[dict[str, Any]] = []
    for cid, srcs in composite_to_sources.items():
        physical = [s for s in srcs if STRAND_FOR_TYPE.get(s["type"]) == "physical"]
        info     = [s for s in srcs if STRAND_FOR_TYPE.get(s["type"]) == "information"]
        for p in physical:
            for i in info:
                base_pairs.append({
                    "source":     p["id"],
                    "target":     i["id"],
                    "via":        cid,
                    "type":       "BASE_PAIR",
                })

    return {
        "aoi":         explore["aoi"],
        "nodes":       nodes_out,
        "edges":       explore["graph"]["edges"],
        "base_pairs":  base_pairs,
        "stats": {
            "physical_count":    sum(1 for n in nodes_out if n["strand"] == "physical"),
            "information_count": sum(1 for n in nodes_out if n["strand"] == "information"),
            "composite_count":   sum(1 for n in nodes_out if n["type"] == "CompositeEvent"),
            "base_pair_count":   len(base_pairs),
        },
    }


# ─────────────────────────── AoI-scoped brief ──────────────────────────
# Triggers the existing 4-agent pipeline (Geospatial / OSINT / Devil's
# Advocate / Supervisor) over the AoI's top composite event, with the
# AoI ID injected into the Supervisor context so the BLUF cites aoi://<id>.

@router.post("/{aoi_id}/brief")
async def generate_aoi_brief(aoi_id: str, request: Request) -> dict[str, Any]:
    """Generate (or re-generate) an intelligence brief scoped to this AoI.

    Picks the top composite by (threat_grade × confidence) and runs the
    full agent pipeline. The supervisor receives the AoI id so the BLUF's
    first citation is the polygon itself.
    """
    store = get_store()
    aoi = store.get_aoi(aoi_id)
    if aoi is None:
        raise HTTPException(status_code=404, detail="AoI not found")

    composite_ids = list(aoi.citation_event_ids or [])
    if not composite_ids:
        raise HTTPException(status_code=409, detail="AoI has no member composites")

    # Resolve top composite (highest grade, then highest confidence)
    conn = store.connect()
    placeholders = ",".join(["?"] * len(composite_ids))
    rows = conn.execute(
        f"""
        SELECT id, threat_grade, confidence
          FROM composite_events
         WHERE id IN ({placeholders})
         ORDER BY CASE threat_grade
            WHEN 'RED' THEN 3 WHEN 'AMBER' THEN 2 WHEN 'GREEN' THEN 1 ELSE 0 END DESC,
            confidence DESC
         LIMIT 1
        """,
        composite_ids,
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=409, detail="AoI composites missing from store")
    top_composite_id = rows[0][0]

    executor = getattr(request.app.state, "executor", None)
    if executor is None or executor.llm is None:
        raise HTTPException(status_code=503, detail="LLM provider unavailable")

    # Run the 4-agent layer end-to-end. We mirror what
    # WatchExecutor._run_agent_layer does, but with aoi_id wired into the
    # supervisor and a synthetic watch_id so the brief lands properly.
    import asyncio as _asyncio
    from backend.agents.base import AgentOutput
    from backend.agents.devils_advocate import DevilsAdvocateAgent
    from backend.agents.geospatial_agent import GeospatialAgent
    from backend.agents.osint_agent import OSINTAgent
    from backend.agents.supervisor_agent import SupervisorAgent, run_supervisor_and_assemble
    from backend.graph.ingestion import ingest_brief
    from backend.llm.factory import get_devil_provider

    prior_outputs: list[tuple[str, AgentOutput]] = []
    geo  = _asyncio.create_task(GeospatialAgent(llm=executor.llm, graph=executor.graph).run(composite_event_id=top_composite_id))
    osi  = _asyncio.create_task(OSINTAgent(llm=executor.llm, graph=executor.graph).run(composite_event_id=top_composite_id))
    geo_res, osi_res = await _asyncio.gather(geo, osi, return_exceptions=True)
    if not isinstance(geo_res, BaseException): prior_outputs.append(("geospatial_agent", geo_res))
    if not isinstance(osi_res, BaseException): prior_outputs.append(("osint_agent", osi_res))

    if prior_outputs:
        try:
            devil = await DevilsAdvocateAgent(llm=get_devil_provider(), graph=executor.graph).run(
                composite_event_id=top_composite_id, prior_outputs=prior_outputs,
            )
            prior_outputs.append(("devils_advocate", devil))
        except Exception as exc:
            log.warning("devils_advocate failed for AoI %s: %s", aoi_id, exc)

    supervisor = SupervisorAgent(llm=executor.llm, graph=executor.graph)
    watch_id = f"aoi-watch-{aoi_id}"
    try:
        brief = await run_supervisor_and_assemble(
            agent=supervisor,
            composite_event_id=top_composite_id,
            watch_id=watch_id,
            prior_outputs=prior_outputs,
            sources_count=len(composite_ids),
            aoi_id=aoi_id,
        )
    except Exception as exc:
        log.exception("Supervisor failed for AoI %s", aoi_id)
        raise HTTPException(status_code=500, detail=f"brief generation failed: {exc}") from exc

    try:
        await ingest_brief(executor.graph, brief)
    except Exception:
        log.exception("ingest_brief failed for AoI %s (returning brief anyway)", aoi_id)

    return brief.model_dump(mode="json")


# ──────────────────────────── helpers ──────────────────────────────

def _to_feature(a: AoI) -> dict[str, Any]:
    geom = _wkt_to_geojson(a.polygon_wkt)
    return {
        "type": "Feature",
        "id": a.id,
        "geometry": geom,
        "properties": {
            "id": a.id,
            "source": a.source.value if isinstance(a.source, AoISource) else a.source,
            "name_el": a.name_el,
            "name_en": a.name_en,
            "description": a.description,
            "centroid_lat": a.centroid_lat,
            "centroid_lon": a.centroid_lon,
            "threat_grade": a.threat_grade,
            "threat_summary": a.threat_summary,
            "citation_event_ids": a.citation_event_ids,
            "scan_id": a.scan_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        },
    }


def _geojson_to_wkt(geom: dict[str, Any]) -> str | None:
    if "geometry" in geom and isinstance(geom["geometry"], dict):
        geom = geom["geometry"]
    if geom.get("type") not in {"Polygon", "MultiPolygon"}:
        return None
    try:
        from shapely.geometry import shape
        return shape(geom).wkt
    except Exception as exc:
        log.warning("geojson->wkt failed: %s", exc)
        return None


def _wkt_to_geojson(wkt: str) -> dict[str, Any]:
    try:
        from shapely import wkt as shp_wkt
        from shapely.geometry import mapping
        return mapping(shp_wkt.loads(wkt))
    except Exception:
        return {"type": "Polygon", "coordinates": []}


def _centroid_of_wkt(wkt: str) -> tuple[float, float]:
    try:
        from shapely import wkt as shp_wkt
        c = shp_wkt.loads(wkt).centroid
        return (c.x, c.y)
    except Exception:
        return (0.0, 0.0)
