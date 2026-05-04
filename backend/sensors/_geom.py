"""Tiny geometry helpers — kept minimal so they can stay test-free dependencies."""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in kilometers.

    Plenty accurate for vessel-scale matching (<10 km). For aerospace or
    long-distance bearings use pyproj.Geod.
    """
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    """``bbox = (min_lon, min_lat, max_lon, max_lat)``."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return (min_lon <= lon <= max_lon) and (min_lat <= lat <= max_lat)
