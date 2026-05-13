"""Brief endpoints — including the gold-medal citation chain.

GET /api/briefs/{brief_id}                          full brief, all sections
GET /api/briefs/{brief_id}/citation/{section_id}    citation chain (the demo click)
GET /api/briefs?watch_id=...                         briefs for a watch
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ._serialize import jsonable

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/briefs", tags=["briefs"])


@router.get("")
async def list_briefs_for_watch(watch_id: str, request: Request) -> list[dict]:
    rows = await request.app.state.executor.graph.run(
        """
        MATCH (w:Watch {id: $watch_id})-[:PRODUCED]->(b:Brief)
        RETURN b ORDER BY b.created_at DESC
        """,
        watch_id=watch_id,
    )
    return [_brief_summary(r["b"]) for r in rows]


@router.get("/{brief_id}")
async def get_brief(brief_id: str, request: Request) -> dict[str, Any]:
    """Return the Brief plus all of its BriefSections, ordered by section type.

    Two-store lookup: Neo4j first, then DuckDB. Canonical briefs (W2-T3,
    pre-baked for each RED AoI) live only in DuckDB because Neo4j may
    not be running in the demo box's network configuration. Without the
    DuckDB fallback, ``GET /api/briefs/{canonical_id}`` 404s even though
    the same brief is served fine by ``POST /api/aoi/{aoi_id}/brief``.
    """
    try:
        rows = await request.app.state.executor.graph.run(
            """
            MATCH (b:Brief {id: $brief_id})-[:CONTAINS]->(bs:BriefSection)
            RETURN b, collect(bs) AS sections
            """,
            brief_id=brief_id,
        )
    except Exception as exc:
        log.info("Neo4j unavailable (%s) — using DuckDB canonical-brief fallback",
                 type(exc).__name__)
        rows = []

    if rows and rows[0].get("b"):
        b = dict(rows[0]["b"])
        sections = [dict(s) for s in (rows[0]["sections"] or []) if s]
        sections = [_section_to_dict(s) for s in sections]
        sections.sort(key=_section_order)
        return {**_brief_summary(b), "sections": sections}

    # DuckDB fallback — scan the canonical-brief cache by brief id.
    from backend.store import get_store
    store = get_store()
    conn = store.connect()
    rows_d = conn.execute(
        "SELECT aoi_id, brief_json FROM aoi_canonical_brief"
    ).fetchall()
    for _aoi_id, payload in rows_d:
        try:
            d = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            continue
        if d.get("id") == brief_id:
            return d

    raise HTTPException(status_code=404, detail=f"brief {brief_id} not found")


@router.get("/{brief_id}/citation/{section_id}")
async def citation_chain(
    brief_id: str, section_id: str, request: Request,
) -> dict[str, Any]:
    """The gold-medal demo path.

    Resolves the BriefSection's CITES edges to source nodes, attaches each
    source's properties + map-highlight + graph-highlight payloads, and
    returns the corroboration chain (sibling sources of the parent
    CompositeEvent).

    Tries Neo4j first (richest path), falls back to the DuckDB canonical
    brief cache when Neo4j is unavailable. The fallback covers the demo
    path: any canonical-cached brief has all its citations resolvable from
    DuckDB alone.
    """
    section_dict: dict[str, Any] | None = None
    sources: list[dict] = []
    siblings: list[dict] = []

    try:
        rows = await request.app.state.executor.graph.run(
            """
            MATCH (b:Brief {id: $brief_id})-[:CONTAINS]->(bs:BriefSection {id: $section_id})
            OPTIONAL MATCH (bs)-[r:CITES]->(source)
            OPTIONAL MATCH (source)<-[:COMPOSED_OF]-(ce:CompositeEvent)
            OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(sibling)
            WHERE sibling <> source
            RETURN bs, b,
                   collect(DISTINCT {type: labels(source)[0], cites: r.node_type, props: source}) AS sources,
                   collect(DISTINCT {type: labels(sibling)[0], props: sibling}) AS siblings
            """,
            brief_id=brief_id, section_id=section_id,
        )
        if rows and rows[0].get("bs"):
            row = rows[0]
            section_dict = _section_to_dict(dict(row["bs"]))
            sources = [s for s in (row["sources"] or []) if s and s.get("type")]
            siblings = [s for s in (row["siblings"] or []) if s and s.get("type")]
    except Exception as exc:
        log.info("citation_chain: Neo4j unreachable (%s) — falling back to DuckDB cache",
                 type(exc).__name__)

    if section_dict is None:
        # DuckDB-only fallback path
        section_dict, sources, siblings = _resolve_citation_chain_from_duckdb(brief_id, section_id)
        if section_dict is None:
            raise HTTPException(
                status_code=404,
                detail=f"section {section_id} not found in brief {brief_id}",
            )

    # Audit the analyst's read access — every citation click is on the chain.
    audit_logger = getattr(request.app.state, "audit", None)
    if audit_logger is not None:
        try:
            await audit_logger.log("brief.citation_accessed", "analyst", {
                "brief_id":      brief_id,
                "section_id":    section_id,
                "section_type":  section_dict.get("section_type"),
                "source_count":  len(sources),
            })
        except Exception:
            # Don't fail the read on audit hiccups — but we'd want to alert in prod.
            pass

    return jsonable({
        "section":             section_dict,
        "source_nodes":        [_source_payload(s["type"], dict(s["props"]), cites=s.get("cites"))
                                for s in sources],
        "corroboration_chain": [_source_payload(s["type"], dict(s["props"]))
                                for s in siblings],
        "confidence_breakdown": {
            "section_confidence": section_dict.get("confidence", 0.0),
            "source_count":       len(sources),
            "corroboration_count": len(siblings),
        },
    })


# ─── helpers ────────────────────────────────────────────────────────────────
def _brief_summary(b: dict) -> dict:
    """Top-level brief metadata (sans sections)."""
    raw_md = b.get("metadata")
    metadata = json.loads(raw_md) if isinstance(raw_md, str) else (raw_md or {})
    return {
        "id":         b.get("id"),
        "watch_id":   b.get("watch_id"),
        "created_at": str(b.get("created_at", "")),
        "metadata":   jsonable(metadata),
    }


def _section_to_dict(s: dict) -> dict:
    raw_extra = s.get("extra")
    extra = json.loads(raw_extra) if isinstance(raw_extra, str) else (raw_extra or {})
    return {
        "id":                s.get("id"),
        "section_type":      s.get("section_type"),
        "text":              s.get("text"),
        "citation_node_ids": list(s.get("citation_node_ids") or []),
        "confidence":        float(s.get("confidence", 0.0)),
        "agent_source":      s.get("agent_source", ""),
        "extra":             jsonable(extra),
    }


def _resolve_citation_chain_from_duckdb(
    brief_id: str, section_id: str,
) -> tuple[dict[str, Any] | None, list[dict], list[dict]]:
    """DuckDB-only citation-chain resolver. Powers the demo when Neo4j is down.

    Strategy: every canonical brief in the cache has a flat ``sections``
    array, each with citation_node_ids. We scan all canonical briefs for
    the one containing this brief_id (or section_id), then resolve each
    citation to a Vessel / NewsEvent / SocialSignal / AreaOfInterest /
    CompositeEvent row in DuckDB.
    """
    from backend.store import get_store
    store = get_store()
    conn = store.connect()

    # Find the canonical brief that contains this section
    cached_briefs = conn.execute(
        "SELECT aoi_id, brief_json FROM aoi_canonical_brief"
    ).fetchall()
    target_section: dict[str, Any] | None = None
    parent_aoi_id: str | None = None
    parent_brief: dict[str, Any] | None = None
    for aoi_id, brief_json in cached_briefs:
        try:
            b = json.loads(brief_json) if isinstance(brief_json, str) else brief_json
        except (TypeError, json.JSONDecodeError):
            continue
        if b.get("id") != brief_id:
            continue
        for s in (b.get("sections") or []):
            if s.get("id") == section_id:
                target_section = s
                parent_aoi_id = aoi_id
                parent_brief = b
                break
        if target_section: break
    if target_section is None or parent_aoi_id is None:
        return None, [], []

    cite_ids = target_section.get("citation_node_ids", []) or []

    # Resolve each citation_id to a typed source-event row.
    # The IDs cover three classes:
    #   - aoi-* : the parent AoI
    #   - composite IDs (UUIDs) : composite_events rows
    #   - source event IDs : raw_ais / raw_news / raw_social
    source_nodes: list[dict] = []

    # Pull the AoI if cited
    for cid in cite_ids:
        if cid.startswith("aoi-"):
            aoi = store.get_aoi(cid)
            if aoi:
                source_nodes.append({
                    "type":  "AreaOfInterest",
                    "cites": "aoi",
                    "props": {
                        "id": aoi.id, "name_el": aoi.name_el, "name_en": aoi.name_en,
                        "description": aoi.description,
                        "centroid_lat": aoi.centroid_lat, "centroid_lon": aoi.centroid_lon,
                        "threat_grade": aoi.threat_grade,
                        "threat_summary": aoi.threat_summary,
                        "source": aoi.source.value if hasattr(aoi.source, "value") else str(aoi.source),
                        "polygon_wkt": aoi.polygon_wkt,
                        "citation_event_ids": aoi.citation_event_ids,
                    },
                })

    # Composites
    non_aoi_ids = [c for c in cite_ids if not c.startswith("aoi-")]
    if non_aoi_ids:
        ph = ",".join(["?"] * len(non_aoi_ids))
        for r in conn.execute(
            f"SELECT id, threat_grade, confidence, summary, centroid_lat, centroid_lon, "
            f"       source_node_ids_json "
            f"FROM composite_events WHERE id IN ({ph})", non_aoi_ids,
        ).fetchall():
            # corroboration_count isn't a DuckDB column; derive it from source_node_ids_json
            try:
                src_count = len(json.loads(r[6] or "[]"))
            except (TypeError, json.JSONDecodeError):
                src_count = 0
            source_nodes.append({
                "type":  "CompositeEvent",
                "cites": "composite",
                "props": {
                    "id": r[0], "threat_grade": r[1], "confidence": r[2],
                    "summary": r[3], "centroid_lat": r[4], "centroid_lon": r[5],
                    "corroboration_count": src_count,
                },
            })
        # Vessel / News / Social by event_id
        for r in conn.execute(
            f"SELECT event_id, mmsi, lat, lon, vessel_name, flag, length_m, ais_status, ts, "
            f"       NULL as sar_tile_id, NULL as dark_vessel_score "
            f"FROM raw_ais WHERE event_id IN ({ph})", non_aoi_ids,
        ).fetchall():
            source_nodes.append({
                "type":  "Vessel",
                "cites": "vessel",
                "props": {
                    "id": r[0], "mmsi": r[1], "lat": r[2], "lon": r[3],
                    "vessel_name": r[4], "flag": r[5], "length_m": r[6],
                    "ais_status": r[7], "ts": r[8].isoformat() if r[8] else None,
                },
            })
        for r in conn.execute(
            f"SELECT event_id, lat, lon, headline, source_url, source_name, "
            f"       goldstein_scale, mentions, language, ts "
            f"FROM raw_news WHERE event_id IN ({ph})", non_aoi_ids,
        ).fetchall():
            source_nodes.append({
                "type":  "NewsEvent",
                "cites": "news",
                "props": {
                    "id": r[0], "lat": r[1], "lon": r[2],
                    "headline": r[3], "source_url": r[4], "source_name": r[5],
                    "goldstein_scale": r[6], "mentions": r[7], "language": r[8],
                    "ts": r[9].isoformat() if r[9] else None,
                },
            })
        for r in conn.execute(
            f"SELECT event_id, channel, lat, lon, text, language, ts "
            f"FROM raw_social WHERE event_id IN ({ph})", non_aoi_ids,
        ).fetchall():
            source_nodes.append({
                "type":  "SocialSignal",
                "cites": "social",
                "props": {
                    "id": r[0], "channel": r[1], "lat": r[2], "lon": r[3],
                    "text": r[4], "language": r[5],
                    "ts": r[6].isoformat() if r[6] else None,
                },
            })

    # Build corroboration chain — the parent AoI's other composites
    aoi = store.get_aoi(parent_aoi_id)
    siblings: list[dict] = []
    if aoi and aoi.citation_event_ids:
        sibling_composite_ids = [c for c in aoi.citation_event_ids if c not in non_aoi_ids]
        if sibling_composite_ids:
            # Cap at 12 to keep the modal scannable
            ph = ",".join(["?"] * min(12, len(sibling_composite_ids)))
            for r in conn.execute(
                f"SELECT id, threat_grade, confidence, summary, centroid_lat, centroid_lon "
                f"FROM composite_events WHERE id IN ({ph}) LIMIT 12",
                sibling_composite_ids[:12],
            ).fetchall():
                siblings.append({
                    "type":  "CompositeEvent",
                    "props": {
                        "id": r[0], "threat_grade": r[1], "confidence": r[2],
                        "summary": r[3], "centroid_lat": r[4], "centroid_lon": r[5],
                    },
                })

    return target_section, source_nodes, siblings


_SECTION_ORDER = {
    "BLUF":             0,
    "KEY_JUDGMENT":     1,
    "SUPPORTING":       2,
    "DEVILS_ADVOCATE":  3,
    "RECOMMENDATION":   4,
}


def _section_order(s: dict) -> tuple[int, str]:
    return (_SECTION_ORDER.get(s.get("section_type", ""), 99), s.get("id", ""))


def _source_payload(node_type: str, p: dict, *, cites: str | None = None) -> dict:
    """Shape source nodes for the frontend: properties + map_highlight + graph_highlight."""
    lat = p.get("lat") if "lat" in p else p.get("centroid_lat")
    lon = p.get("lon") if "lon" in p else p.get("centroid_lon")
    raw_evidence: dict[str, Any] = {}
    if node_type == "Vessel":
        raw_evidence = {
            "type":     "SAR_TILE",
            "tile_id":  p.get("sar_tile_id"),
            "metadata": {k: p.get(k) for k in ("mmsi", "vessel_name", "flag", "ais_status",
                                                "length_m", "dark_vessel_score", "confidence")},
        }
    elif node_type == "NewsEvent":
        raw_evidence = {
            "type":     "ARTICLE_URL",
            "url":      p.get("source_url"),
            "metadata": {k: p.get(k) for k in ("source_name", "headline", "goldstein_scale",
                                                "cameo_code", "language", "mentions")},
        }
    elif node_type == "SocialSignal":
        raw_evidence = {
            "type":     "TELEGRAM_MESSAGE",
            "content":  p.get("text"),
            "metadata": {k: p.get(k) for k in ("channel", "language", "views", "forwards",
                                                "matched_place")},
        }
    elif node_type == "CompositeEvent":
        raw_evidence = {
            "type":     "COMPOSITE",
            "metadata": {k: p.get(k) for k in ("threat_grade", "confidence", "summary",
                                                "corroboration_count")},
        }
    elif node_type == "AreaOfInterest":
        raw_evidence = {
            "type":     "AOI_CLUSTER",
            "metadata": {
                "name_el":        p.get("name_el"),
                "name_en":        p.get("name_en"),
                "threat_grade":   p.get("threat_grade"),
                "threat_summary": p.get("threat_summary"),
                "description":    p.get("description"),
                "source":         p.get("source"),
                "polygon_wkt":    p.get("polygon_wkt"),
                "member_count":   len(p.get("citation_event_ids") or []) if p.get("citation_event_ids") else None,
            },
        }

    # Map highlight radius — AoIs render as polygons on the map, so the
    # citation chain just centres there at a wider zoom.
    map_radius_km = 5.0 if node_type == "Vessel" else (60.0 if node_type == "AreaOfInterest" else 50.0)

    return {
        "node_id":   p.get("id"),
        "node_type": node_type,
        "cites_via": cites,
        "properties": dict(p),
        "raw_evidence": raw_evidence,
        "map_highlight": {
            "lat":        lat,
            "lon":        lon,
            "radius_km":  map_radius_km,
        } if (lat is not None and lon is not None) else None,
        "graph_highlight": {"node_id": p.get("id")},
    }
