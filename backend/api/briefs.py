"""Brief endpoints — including the gold-medal citation chain.

GET /api/briefs/{brief_id}                          full brief, all sections
GET /api/briefs/{brief_id}/citation/{section_id}    citation chain (the demo click)
GET /api/briefs?watch_id=...                         briefs for a watch
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ._serialize import jsonable

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
    """Return the Brief plus all of its BriefSections, ordered by section type."""
    rows = await request.app.state.executor.graph.run(
        """
        MATCH (b:Brief {id: $brief_id})-[:CONTAINS]->(bs:BriefSection)
        RETURN b, collect(bs) AS sections
        """,
        brief_id=brief_id,
    )
    if not rows or not rows[0].get("b"):
        raise HTTPException(status_code=404, detail=f"brief {brief_id} not found")

    b = dict(rows[0]["b"])
    sections = [dict(s) for s in (rows[0]["sections"] or []) if s]
    sections = [_section_to_dict(s) for s in sections]
    sections.sort(key=_section_order)
    return {**_brief_summary(b), "sections": sections}


@router.get("/{brief_id}/citation/{section_id}")
async def citation_chain(
    brief_id: str, section_id: str, request: Request,
) -> dict[str, Any]:
    """The gold-medal demo path.

    Resolves the BriefSection's CITES edges to source nodes, attaches each
    source's properties + map-highlight + graph-highlight payloads, and
    returns the corroboration chain (sibling sources of the parent
    CompositeEvent).
    """
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
    if not rows or not rows[0].get("bs"):
        raise HTTPException(
            status_code=404,
            detail=f"section {section_id} not found in brief {brief_id}",
        )

    row = rows[0]
    section_dict = _section_to_dict(dict(row["bs"]))
    sources = [s for s in (row["sources"] or []) if s and s.get("type")]
    siblings = [s for s in (row["siblings"] or []) if s and s.get("type")]

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
