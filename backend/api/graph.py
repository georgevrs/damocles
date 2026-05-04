"""Graph endpoint — feeds the Cytoscape panel with nodes + edges for a watch.

GET /api/graph/{watch_id}
    Returns the subgraph reachable from the watch: composites, sources,
    brief sections. Each node has a stable id, type, label, and lat/lon
    where available; edges have a type.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ._serialize import jsonable

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/{watch_id}")
async def get_watch_graph(watch_id: str, request: Request, limit: int = 1500) -> dict:
    """Return the subgraph for a watch as ``{nodes: [...], edges: [...]}``.

    ``limit`` caps the total number of nodes returned to keep the Cytoscape
    panel responsive. The cap applies after filtering — composites first,
    then their sources, then brief sections.
    """
    graph = request.app.state.executor.graph
    rows = await graph.run(
        """
        MATCH (w:Watch {id: $id})
        OPTIONAL MATCH (w)-[:TRIGGERED]->(ce:CompositeEvent)
        OPTIONAL MATCH (ce)-[r1:COMPOSED_OF]->(source)
        OPTIONAL MATCH (w)-[:PRODUCED]->(b:Brief)-[:CONTAINS]->(bs:BriefSection)
        OPTIONAL MATCH (bs)-[r2:CITES]->(target)
        RETURN w,
               collect(DISTINCT ce)               AS composites,
               collect(DISTINCT source)           AS sources,
               collect(DISTINCT b)                AS briefs,
               collect(DISTINCT bs)               AS sections,
               collect(DISTINCT {a: ce, rel: 'COMPOSED_OF', b: source})    AS composed_of,
               collect(DISTINCT {a: bs, rel: 'CITES',       b: target})    AS cites
        """,
        id=watch_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"watch {watch_id} not found")

    row = rows[0]
    nodes: list[dict] = []
    seen: set[str] = set()

    def _add(n: Any, kind: str) -> None:
        if not n:
            return
        nid = n.get("id")
        if not nid or nid in seen:
            return
        seen.add(nid)
        nodes.append(_node_payload(nid, kind, dict(n)))

    _add(row["w"], "Watch")
    for ce in row["composites"] or []:    _add(ce, "CompositeEvent")
    for s  in row["sources"]    or []:    _add(s,  _label(s))
    for b  in row["briefs"]     or []:    _add(b,  "Brief")
    for bs in row["sections"]   or []:    _add(bs, "BriefSection")

    edges: list[dict] = []

    def _edge(a: Any, rel: str, b: Any) -> None:
        if not a or not b: return
        aid, bid = a.get("id"), b.get("id")
        if not aid or not bid: return
        edges.append({"source": aid, "target": bid, "type": rel})

    # Watch -> CompositeEvent (TRIGGERED)
    for ce in row["composites"] or []:
        _edge(row["w"], "TRIGGERED", ce)
    # Watch -> Brief (PRODUCED)
    for b in row["briefs"] or []:
        _edge(row["w"], "PRODUCED", b)
    # Brief -> BriefSection (CONTAINS)
    for b in row["briefs"] or []:
        for bs in row["sections"] or []:
            _edge(b, "CONTAINS", bs)
    # CompositeEvent -> source (COMPOSED_OF)
    for e in row["composed_of"] or []:
        _edge(e.get("a"), e.get("rel"), e.get("b"))
    # BriefSection -> target (CITES)
    for e in row["cites"] or []:
        _edge(e.get("a"), e.get("rel"), e.get("b"))

    if len(nodes) > limit:
        kept_ids = {n["id"] for n in nodes[:limit]}
        nodes = nodes[:limit]
        edges = [e for e in edges if e["source"] in kept_ids and e["target"] in kept_ids]

    return jsonable({"nodes": nodes, "edges": edges})


def _label(n: dict | None) -> str:
    if not n:
        return "Unknown"
    if "ais_status" in n:    return "Vessel"
    if "headline"   in n:    return "NewsEvent"
    if "channel"    in n:    return "SocialSignal"
    return "Unknown"


def _node_payload(nid: str, kind: str, p: dict) -> dict:
    label_text = (
        p.get("vessel_name") or p.get("headline") or p.get("summary") or
        p.get("channel") or p.get("section_type") or kind
    )
    return {
        "id":    nid,
        "type":  kind,
        "label": str(label_text)[:60],
        "lat":   p.get("lat") or p.get("centroid_lat"),
        "lon":   p.get("lon") or p.get("centroid_lon"),
        "props": p,
    }
