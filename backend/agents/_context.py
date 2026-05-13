"""Shared context-fetch utility for agents.

All three reasoning agents (Geospatial, OSINT, Supervisor) need the same
shape of input: a CompositeEvent plus its COMPOSED_OF sources (Vessel /
NewsEvent / SocialSignal). They prefer Neo4j (richer cross-watch edges)
but must work without it — Neo4j requires Docker, and the demo box
shouldn't depend on docker running.

This module provides one helper:

    fetch_ce_with_sources(graph, composite_id) -> (ce_dict, [{type, props}, …])

Returns the data via Neo4j when reachable; falls back to DuckDB
transparently when it isn't. Same return shape either way so the caller
doesn't branch.
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


async def fetch_ce_with_sources(
    graph: Any,
    composite_event_id: str,
) -> tuple[dict, list[dict]]:
    """Return ``(ce_dict, sources_list)`` for one CompositeEvent.

    ``ce_dict`` is a flat dict (id, threat_grade, confidence, summary,
    centroid_lat, centroid_lon). ``sources_list`` items are
    ``{"type": "Vessel"|"NewsEvent"|"SocialSignal", "props": {...}}``.

    Tries Neo4j first; falls back to DuckDB. Raises ValueError only if
    BOTH paths return nothing.
    """
    ce: dict | None = None
    sources_raw: list[dict] = []
    neo4j_error: Exception | None = None

    try:
        rows = await graph.run(
            """
            MATCH (ce:CompositeEvent {id: $id})
            OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(source)
            RETURN ce, collect({type: labels(source)[0], props: source}) AS sources
            """,
            id=composite_event_id,
        )
        if rows and rows[0].get("ce"):
            ce_raw = rows[0]["ce"]
            ce = {
                "id":           ce_raw["id"],
                "threat_grade": ce_raw.get("threat_grade"),
                "confidence":   ce_raw.get("confidence"),
                "summary":      ce_raw.get("summary"),
                "centroid_lat": ce_raw.get("centroid_lat"),
                "centroid_lon": ce_raw.get("centroid_lon"),
            }
            sources_raw = [
                {"type": s["type"], "props": dict(s["props"])}
                for s in (rows[0]["sources"] or [])
                if s and s.get("type") and s.get("props")
            ]
    except Exception as exc:
        neo4j_error = exc
        log.info("agent context: Neo4j unavailable (%s) — falling back to DuckDB",
                 type(exc).__name__)

    if ce is None:
        ce, sources_raw = _fetch_ce_from_duckdb(composite_event_id)
        if ce is None:
            if neo4j_error is not None:
                raise ValueError(
                    f"CompositeEvent {composite_event_id!r}: Neo4j failed "
                    f"({neo4j_error}) and DuckDB has no row"
                )
            raise ValueError(f"CompositeEvent {composite_event_id!r} not found")

    return ce, sources_raw


def _fetch_ce_from_duckdb(composite_event_id: str) -> tuple[dict | None, list[dict]]:
    """DuckDB equivalent of the Cypher query above. Reads from
    composite_events + raw_ais + raw_news + raw_social."""
    from backend.store import get_store
    store = get_store()
    conn = store.connect()

    row = conn.execute(
        """
        SELECT id, threat_grade, confidence, summary, centroid_lat, centroid_lon,
               source_node_ids_json
          FROM composite_events WHERE id = ?
        """,
        [composite_event_id],
    ).fetchone()
    if not row:
        return None, []
    ce = {
        "id":           row[0],
        "threat_grade": row[1],
        "confidence":   row[2],
        "summary":      row[3],
        "centroid_lat": row[4],
        "centroid_lon": row[5],
    }
    try:
        source_ids = json.loads(row[6] or "[]")
    except (TypeError, json.JSONDecodeError):
        source_ids = []

    sources_raw: list[dict] = []
    if source_ids:
        ph = ",".join(["?"] * len(source_ids))
        # Vessels
        for r in conn.execute(
            f"SELECT event_id, mmsi, lat, lon, vessel_name, flag, length_m, ais_status, ts "
            f"FROM raw_ais WHERE event_id IN ({ph})",
            source_ids,
        ).fetchall():
            sources_raw.append({
                "type":  "Vessel",
                "props": {
                    "id": r[0], "mmsi": r[1], "lat": r[2], "lon": r[3],
                    "vessel_name": r[4], "flag": r[5], "length_m": r[6],
                    "ais_status": r[7], "timestamp": r[8].isoformat() if r[8] else None,
                },
            })
        # News
        for r in conn.execute(
            f"SELECT event_id, lat, lon, headline, source_url, source_name, "
            f"       goldstein_scale, mentions, language, ts "
            f"FROM raw_news WHERE event_id IN ({ph})",
            source_ids,
        ).fetchall():
            sources_raw.append({
                "type":  "NewsEvent",
                "props": {
                    "id": r[0], "lat": r[1], "lon": r[2],
                    "headline": r[3], "source_url": r[4], "source_name": r[5],
                    "goldstein_scale": r[6], "mentions": r[7], "language": r[8],
                    "timestamp": r[9].isoformat() if r[9] else None,
                },
            })
        # Social
        for r in conn.execute(
            f"SELECT event_id, channel, lat, lon, text, language, ts "
            f"FROM raw_social WHERE event_id IN ({ph})",
            source_ids,
        ).fetchall():
            sources_raw.append({
                "type":  "SocialSignal",
                "props": {
                    "id": r[0], "channel": r[1], "lat": r[2], "lon": r[3],
                    "text": r[4], "language": r[5],
                    "timestamp": r[6].isoformat() if r[6] else None,
                },
            })
    return ce, sources_raw
