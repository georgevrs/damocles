"""External events overlay endpoints.

Lightweight read-through proxies for free, no-key public feeds we want to
render on the map *without* feeding them through fusion / HDBSCAN. They
contribute visual richness (earthquakes near a maritime AoI, wildfires
inside a fire-source cluster) but their integration into the agent pipeline
is deliberately deferred — that requires schema and prompt changes that
would invalidate the existing 71-AoI Greek standing scan.

Disk-cached for 10 minutes per source so panning the map doesn't hammer
upstream APIs. Cache files live in ``data/cache/external/``.

Endpoints
---------
GET /api/external/earthquakes — USGS FDSN, last 7 days, M ≥ 4.0, Greek bbox
GET /api/external/disasters   — GDACS RSS, all current alerts in Greek bbox
GET /api/external/eonet       — NASA EONET open events (fires, storms, etc.)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Query

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/external", tags=["external"])

# Greek mainland + EEZ + Aegean + neighbors (extended for cross-border context)
DEFAULT_BBOX = (17.0, 31.0, 37.0, 45.0)

CACHE_DIR = Path("data/cache/external")
CACHE_TTL_SECONDS = 600  # 10 minutes

UA = "Damocles/1.0 (sovereign-intel-platform)"


# ─────────────────────────── disk cache ───────────────────────────

def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{name}.json"


def _read_cache(name: str) -> dict[str, Any] | None:
    p = _cache_path(name)
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    if age > CACHE_TTL_SECONDS:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(name: str, payload: dict[str, Any]) -> None:
    try:
        _cache_path(name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.warning("cache write failed for %s: %s", name, exc)


def _empty_fc(reason: str | None = None) -> dict[str, Any]:
    return {
        "type":     "FeatureCollection",
        "features": [],
        "meta":     {"reason": reason} if reason else {},
    }


def _bbox_filter(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


# ─────────────────────────── USGS earthquakes ───────────────────────────

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


@router.get("/earthquakes")
async def earthquakes(
    days:    int   = Query(7,   ge=1, le=30),
    min_mag: float = Query(3.5, ge=0.0, le=9.5),
) -> dict[str, Any]:
    """USGS earthquakes within the Greek extended bbox over the last N days.

    Returns a GeoJSON FeatureCollection — feature.geometry is a Point, properties
    include `magnitude`, `depth_km`, `place`, `threat_grade`, `source_url`.
    """
    cache_key = f"earthquakes_d{days}_m{min_mag}"
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    time_to   = datetime.now(timezone.utc)
    time_from = time_to - timedelta(days=days)

    params = {
        "format":       "geojson",
        "starttime":    time_from.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime":      time_to.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": min_mag,
        "minlongitude": DEFAULT_BBOX[0],
        "minlatitude":  DEFAULT_BBOX[1],
        "maxlongitude": DEFAULT_BBOX[2],
        "maxlatitude":  DEFAULT_BBOX[3],
        "orderby":      "time",
    }

    try:
        async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=15) as client:
            r = await client.get(USGS_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("USGS earthquakes fetch failed: %s", exc)
        return _empty_fc(reason=f"upstream_error: {type(exc).__name__}")

    features: list[dict[str, Any]] = []
    for feat in data.get("features", []):
        try:
            p = feat["properties"]
            c = feat["geometry"]["coordinates"]
            mag = float(p.get("mag") or 0)
            grade = "RED" if mag >= 6.0 else ("AMBER" if mag >= 5.0 else "GREEN")
            ts = p.get("time")
            features.append({
                "type": "Feature",
                "id":   feat.get("id"),
                "geometry": {"type": "Point", "coordinates": [c[0], c[1]]},
                "properties": {
                    "kind":         "earthquake",
                    "magnitude":    mag,
                    "depth_km":     c[2] if len(c) > 2 else None,
                    "place":        p.get("place"),
                    "threat_grade": grade,
                    "source_url":   p.get("url"),
                    "ts":           datetime.utcfromtimestamp(ts / 1000).isoformat() + "Z" if ts else None,
                    "felt":         p.get("felt"),
                    "tsunami":      bool(p.get("tsunami")),
                    "label":        f"M{mag:.1f} — {p.get('place','')}",
                },
            })
        except (KeyError, TypeError, ValueError):
            continue

    payload = {
        "type":     "FeatureCollection",
        "features": features,
        "meta":     {"source": "USGS", "days": days, "min_mag": min_mag, "count": len(features)},
    }
    _write_cache(cache_key, payload)
    return payload


# ─────────────────────────── GDACS disasters ───────────────────────────

GDACS_RSS = "https://www.gdacs.org/xml/rss.xml"


@router.get("/disasters")
async def disasters() -> dict[str, Any]:
    """GDACS active disaster alerts (RSS) clipped to the Greek extended bbox.

    Each feature carries `alert_level` (GREEN/ORANGE/RED), `event_type` (EQ, FL, TC, …),
    `ts`, and a clickable `source_url`.
    """
    cache_key = "disasters"
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=15) as client:
            r = await client.get(GDACS_RSS)
            r.raise_for_status()
            xml_bytes = r.content
    except httpx.HTTPError as exc:
        log.warning("GDACS RSS fetch failed: %s", exc)
        return _empty_fc(reason=f"upstream_error: {type(exc).__name__}")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        log.warning("GDACS XML parse failed: %s", exc)
        return _empty_fc(reason="parse_error")

    ns = {
        "gdacs": "http://www.gdacs.org",
        "geo":   "http://www.w3.org/2003/01/geo/wgs84_pos#",
    }

    grade_map = {"GREEN": "GREEN", "ORANGE": "AMBER", "RED": "RED"}

    features: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        try:
            lat_el = item.find("geo:lat", ns)
            lon_el = item.find("geo:long", ns)
            if lat_el is None or lon_el is None or not lat_el.text or not lon_el.text:
                continue
            lat = float(lat_el.text)
            lon = float(lon_el.text)
            if not _bbox_filter(lon, lat, DEFAULT_BBOX):
                continue

            alert_el = item.find("gdacs:alertlevel", ns)
            alert = (alert_el.text if alert_el is not None and alert_el.text else "GREEN").upper()
            grade = grade_map.get(alert, "GREEN")

            event_type_el = item.find("gdacs:eventtype", ns)
            event_type = event_type_el.text if event_type_el is not None and event_type_el.text else None

            pub_str = item.findtext("pubDate", "")
            try:
                ts = parsedate_to_datetime(pub_str).astimezone(timezone.utc).isoformat() if pub_str else None
            except (TypeError, ValueError):
                ts = None

            title = (item.findtext("title", "") or "").strip()
            features.append({
                "type": "Feature",
                "id":   f"gdacs-{lat:.3f}-{lon:.3f}-{pub_str[:16]}",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "kind":         "disaster",
                    "alert_level":  alert,
                    "event_type":   event_type,
                    "threat_grade": grade,
                    "source_url":   item.findtext("link", ""),
                    "ts":           ts,
                    "label":        f"GDACS {alert}: {title[:80]}",
                    "title":        title,
                },
            })
        except (ValueError, AttributeError):
            continue

    payload = {
        "type":     "FeatureCollection",
        "features": features,
        "meta":     {"source": "GDACS", "count": len(features)},
    }
    _write_cache(cache_key, payload)
    return payload


# ─────────────────────────── NASA EONET ───────────────────────────

EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"


@router.get("/eonet")
async def eonet(
    days: int = Query(14, ge=1, le=60),
    status: str = Query("open", pattern="^(open|closed|all)$"),
) -> dict[str, Any]:
    """NASA EONET open natural events clipped to the Greek extended bbox.

    Categories include wildfires, severe storms, volcanoes, earthquakes,
    sea/lake ice — the API returns a normalised feed across them.
    """
    cache_key = f"eonet_d{days}_s{status}"
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    params = {"days": days, "status": status, "bbox": ",".join(str(x) for x in DEFAULT_BBOX)}

    try:
        async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=20) as client:
            r = await client.get(EONET_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("EONET fetch failed: %s", exc)
        return _empty_fc(reason=f"upstream_error: {type(exc).__name__}")

    features: list[dict[str, Any]] = []
    for evt in data.get("events", []):
        try:
            cats = evt.get("categories") or []
            cat = (cats[0] or {}).get("title") if cats else None
            geometries = evt.get("geometry") or []
            if not geometries:
                continue
            # Use the most recent geometry (last entry by date)
            g = geometries[-1]
            coords = g.get("coordinates")
            if not coords or g.get("type") != "Point":
                # EONET also has Polygon (e.g. fire perimeter); take centroid
                if g.get("type") == "Polygon" and isinstance(coords, list) and coords:
                    ring = coords[0]
                    if not ring:
                        continue
                    lons = [pt[0] for pt in ring if isinstance(pt, list)]
                    lats = [pt[1] for pt in ring if isinstance(pt, list)]
                    if not lons:
                        continue
                    lon = sum(lons) / len(lons)
                    lat = sum(lats) / len(lats)
                else:
                    continue
            else:
                lon, lat = float(coords[0]), float(coords[1])

            if not _bbox_filter(lon, lat, DEFAULT_BBOX):
                continue

            # EONET has no formal severity. Use category to seed a grade so
            # the layer renders meaningful colours.
            grade = "AMBER" if cat in {"Wildfires", "Severe Storms", "Volcanoes"} else "GREEN"

            features.append({
                "type": "Feature",
                "id":   evt.get("id"),
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "kind":         "eonet",
                    "category":     cat,
                    "title":        evt.get("title"),
                    "threat_grade": grade,
                    "source_url":   evt.get("link"),
                    "ts":           g.get("date"),
                    "label":        f"{cat or 'Event'}: {evt.get('title','')[:60]}",
                    "magnitude":    g.get("magnitudeValue"),
                    "magnitude_unit": g.get("magnitudeUnit"),
                },
            })
        except (KeyError, TypeError, ValueError):
            continue

    payload = {
        "type":     "FeatureCollection",
        "features": features,
        "meta":     {"source": "NASA EONET", "days": days, "status": status, "count": len(features)},
    }
    _write_cache(cache_key, payload)
    return payload


# ─────────────────────────── combined ───────────────────────────

@router.get("/all")
async def external_all(days: int = Query(7, ge=1, le=30)) -> dict[str, Any]:
    """Concurrent fetch of all three external sources."""
    eq_task = asyncio.create_task(earthquakes(days=days, min_mag=3.5))
    ds_task = asyncio.create_task(disasters())
    en_task = asyncio.create_task(eonet(days=days, status="open"))
    eq, ds, en = await asyncio.gather(eq_task, ds_task, en_task, return_exceptions=True)

    def _ok(x: Any) -> dict[str, Any]:
        return x if isinstance(x, dict) else _empty_fc(reason=f"task_error: {type(x).__name__}")

    return {
        "earthquakes": _ok(eq),
        "disasters":   _ok(ds),
        "eonet":       _ok(en),
    }
