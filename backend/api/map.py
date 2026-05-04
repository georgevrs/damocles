"""Map data endpoints — Phase 2 layered visualization.

These read from DuckDB only (the standing scan and per-watch caches
already populate it). No upstream API calls happen here — these endpoints
are cheap and meant to be called per pan/zoom.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from backend.store import get_store

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/map", tags=["map"])

# Default to Greece-wide if the client doesn't pass a bbox.
GREECE_BBOX = (19.0, 34.5, 29.7, 41.8)


def _parse_bbox(bbox_str: str | None) -> tuple[float, float, float, float]:
    if not bbox_str:
        return GREECE_BBOX
    parts = bbox_str.split(",")
    if len(parts) != 4:
        return GREECE_BBOX
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return GREECE_BBOX


@router.get("/trajectories")
async def trajectories(
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    hours: int = Query(24, ge=1, le=24 * 14),
    min_points: int = Query(3, ge=2, le=50),
    max_vessels: int = Query(250, ge=1, le=2000),
) -> dict[str, Any]:
    """GeoJSON FeatureCollection of LineString-per-vessel."""
    box = _parse_bbox(bbox)
    t_to = datetime.now(timezone.utc)
    t_from = t_to - timedelta(hours=hours)
    rows = get_store().vessel_trajectories(
        bbox=box, time_from=t_from, time_to=t_to,
        min_points=min_points, max_vessels=max_vessels,
    )
    features = []
    for row in rows:
        coords = [(p["lon"], p["lat"]) for p in row["points"]]
        timestamps = [p["ts"].isoformat() if hasattr(p["ts"], "isoformat") else str(p["ts"]) for p in row["points"]]
        features.append({
            "type": "Feature",
            "id": f"traj-{row['mmsi']}",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "mmsi": row["mmsi"],
                "n_points": row["count"],
                "first_ts": timestamps[0] if timestamps else None,
                "last_ts": timestamps[-1] if timestamps else None,
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/vessels")
async def vessels(
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    hours: int = Query(24 * 7, ge=1, le=24 * 30),
    limit: int = Query(2000, ge=1, le=10000),
) -> dict[str, Any]:
    """All vessel detections in the bbox/window. Reads raw_ais (which
    contains both AISStream broadcasts AND SAR-detected vessels — the
    SAR ones lack MMSI). Independent of any active watch."""
    box = _parse_bbox(bbox)
    t_to = datetime.now(timezone.utc)
    t_from = t_to - timedelta(hours=hours)
    conn = get_store().connect()
    rows = conn.execute(
        """
        SELECT event_id, mmsi, ts, lat, lon, vessel_name,
               flag, length_m, ais_status
          FROM raw_ais
         WHERE ts BETWEEN ? AND ?
           AND lon BETWEEN ? AND ?
           AND lat BETWEEN ? AND ?
         ORDER BY ts DESC
         LIMIT ?
        """,
        [t_from, t_to, box[0], box[2], box[1], box[3], limit],
    ).fetchall()

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "id":   r[0],
            "geometry": {"type": "Point", "coordinates": [r[4], r[3]]},
            "properties": {
                "node_id":     r[0],
                "node_type":   "Vessel",
                "label":       r[5] or r[1] or r[0][:8],
                "mmsi":        r[1],
                "ts":          r[2].isoformat() if r[2] else None,
                "vessel_name": r[5],
                "flag":        r[6],
                "length_m":    r[7],
                "ais_status":  r[8],
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/vessel/{event_id}/trajectory")
async def vessel_trajectory(
    event_id: str,
    hours: int = Query(24 * 14, ge=1, le=24 * 30),
) -> dict[str, Any]:
    """Per-vessel trajectory polyline. Looks up the vessel's MMSI from the
    event_id, then returns every raw_ais row for that MMSI within `hours`.
    Falls back to a single-point feature when the vessel has no MMSI
    (typical for SAR-only detections)."""
    conn = get_store().connect()

    # Resolve event_id → mmsi (might be NULL for SAR-only)
    row = conn.execute(
        "SELECT mmsi, lat, lon, ts FROM raw_ais WHERE event_id = ?",
        [event_id],
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="vessel not found")

    mmsi, lat0, lon0, ts0 = row
    if not mmsi:
        # Single-point fallback
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "id":   f"traj-{event_id}",
                "geometry": {"type": "Point", "coordinates": [lon0, lat0]},
                "properties": {"event_id": event_id, "mmsi": None, "n_points": 1, "ts": ts0.isoformat() if ts0 else None},
            }],
        }

    t_to = datetime.now(timezone.utc)
    t_from = t_to - timedelta(hours=hours)
    rows = conn.execute(
        """
        SELECT lon, lat, ts, ais_status FROM raw_ais
         WHERE mmsi = ? AND ts BETWEEN ? AND ?
         ORDER BY ts ASC
        """,
        [mmsi, t_from, t_to],
    ).fetchall()
    coords = [[r[0], r[1]] for r in rows]
    timestamps = [r[2].isoformat() if r[2] else None for r in rows]
    if len(coords) < 2:
        # one or zero points — render as a single point
        if not coords:
            coords = [[lon0, lat0]]
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "id":   f"traj-{mmsi}",
                "geometry": {"type": "Point", "coordinates": coords[0]},
                "properties": {"mmsi": mmsi, "n_points": len(coords)},
            }],
        }
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id":   f"traj-{mmsi}",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "mmsi":     mmsi,
                "n_points": len(coords),
                "first_ts": timestamps[0],
                "last_ts":  timestamps[-1],
            },
        }],
    }


@router.get("/flights")
async def flights(
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
) -> dict[str, Any]:
    """Live OpenSky aircraft positions inside the bbox. Free public endpoint
    https://opensky-network.org/api/states/all (no key required for
    anonymous requests, ~10 req/min cap).

    We treat this as a live read — there is no DuckDB cache because the
    point of flights is "what's in the air now". For historical replay
    (Day 27+) we'd persist these, but for the operational map this is fine.
    """
    box = _parse_bbox(bbox)
    url = (
        f"https://opensky-network.org/api/states/all"
        f"?lamin={box[1]}&lomin={box[0]}&lamax={box[3]}&lomax={box[2]}"
    )
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.get(url)
            if r.status_code != 200:
                log.warning("OpenSky returned %d", r.status_code)
                return {"type": "FeatureCollection", "features": []}
            payload = r.json()
    except Exception as exc:
        log.warning("OpenSky fetch failed: %s", exc)
        return {"type": "FeatureCollection", "features": []}

    features = []
    for s in payload.get("states", []) or []:
        # OpenSky state vector tuple, by index:
        # 0 icao24, 1 callsign, 2 origin_country, 3 time_position, 4 last_contact,
        # 5 longitude, 6 latitude, 7 baro_altitude, 8 on_ground, 9 velocity,
        # 10 true_track, 11 vertical_rate, 12 sensors, 13 geo_altitude, 14 squawk
        if not s or s[5] is None or s[6] is None:
            continue
        features.append({
            "type": "Feature",
            "id":   s[0],
            "geometry": {"type": "Point", "coordinates": [s[5], s[6]]},
            "properties": {
                "icao24":         s[0],
                "callsign":       (s[1] or "").strip() or None,
                "origin_country": s[2],
                "altitude_m":     s[7],
                "on_ground":      bool(s[8]),
                "velocity_ms":    s[9],
                "heading":        s[10],
                "vertical_rate":  s[11],
                "ts":             s[3],
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/news_heatmap")
async def news_heatmap(
    bbox: str | None = Query(None),
    hours: int = Query(24 * 7, ge=1),
    h3_resolution: int = Query(5, ge=3, le=8),
) -> dict[str, Any]:
    """H3 hex aggregation of GDELT events for a heatmap-style fill layer."""
    try:
        import h3
    except ImportError:
        return {"type": "FeatureCollection", "features": []}

    box = _parse_bbox(bbox)
    t_to = datetime.now(timezone.utc)
    t_from = t_to - timedelta(hours=hours)
    conn = get_store().connect()
    rows = conn.execute(
        """
        SELECT lat, lon, mentions, goldstein_scale
          FROM raw_news
         WHERE ts BETWEEN ? AND ?
           AND lon BETWEEN ? AND ?
           AND lat BETWEEN ? AND ?
        """,
        [t_from, t_to, box[0], box[2], box[1], box[3]],
    ).fetchall()

    bins: dict[str, dict[str, float | int]] = {}
    for lat, lon, mentions, goldstein in rows:
        cell = h3.latlng_to_cell(lat, lon, h3_resolution)
        b = bins.setdefault(cell, {"n": 0, "mentions": 0, "tone_sum": 0.0})
        b["n"] += 1
        b["mentions"] += int(mentions or 0)
        b["tone_sum"] += float(goldstein or 0.0)

    features = []
    for cell, b in bins.items():
        boundary = h3.cell_to_boundary(cell)
        coords = [[(lon, lat) for (lat, lon) in boundary] + [(boundary[0][1], boundary[0][0])]]
        n = int(b["n"])
        features.append({
            "type": "Feature",
            "id": cell,
            "geometry": {"type": "Polygon", "coordinates": coords},
            "properties": {
                "h3": cell,
                "n_events": n,
                "mentions": int(b["mentions"]),
                "avg_tone": (b["tone_sum"] / n) if n else 0.0,
            },
        })
    return {"type": "FeatureCollection", "features": features}
