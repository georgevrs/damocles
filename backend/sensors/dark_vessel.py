"""Dark vessel detection — cross-reference SAR detections against AIS broadcasts.

For each SAR-detected vessel, search the AIS feed for a transmitter within
``time_tolerance`` and ``spatial_tolerance``. If found, mark the vessel as
BROADCASTING and copy MMSI/name. If none found, mark it DARK and compute a
suspiciousness score combining vessel size, location, and time-of-day.

The DARK confidence score (per plan §2c):

    base = 0.7
    + 0.1 if length_m > 100  (large vessels rarely lose AIS by accident)
    + 0.1 if in a contested zone (e.g. eastern Aegean median line)
    + 0.1 if 00:00-06:00 UTC (nighttime evasion pattern)

This score is independent of CFAR detection confidence (which captures "is this
even a vessel"). The two get blended in the threat-grade rules — a high
detection confidence × high dark score = RED.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from backend.models.event import AISStatus, Vessel

from ._geom import haversine_km

log = logging.getLogger(__name__)


@dataclass
class AISRecord:
    """Minimal AIS broadcast for cross-reference. Populated by AISStreamClient."""
    mmsi: str
    lat: float
    lon: float
    timestamp: datetime
    name: str | None = None
    sog_knots: float | None = None         # speed over ground
    cog_deg: float | None = None           # course over ground
    flag: str | None = None                # ISO country code if known


@dataclass
class ContestedZone:
    """A polygon (bbox-approximated) where AIS-dark vessels carry extra weight.

    For the demo we use a simple bbox along the eastern Aegean median line.
    Real contested-zone polygons would come from operational maritime boundary
    datasets — out of scope for the foundation.
    """
    name: str
    bbox: tuple[float, float, float, float]   # (min_lon, min_lat, max_lon, max_lat)


# Default zone for the Aegean demo — east of 26°E between Lesvos and the Dodecanese.
# This roughly traces the area where Greek and Turkish maritime claims overlap.
DEFAULT_CONTESTED_ZONES: list[ContestedZone] = [
    ContestedZone(name="eastern_aegean_median", bbox=(26.0, 35.5, 28.0, 40.5)),
]


@dataclass
class DarkVesselConfig:
    time_tolerance_min: int = 30
    spatial_tolerance_km: float = 2.0
    contested_zones: list[ContestedZone] = field(default_factory=lambda: list(DEFAULT_CONTESTED_ZONES))
    large_vessel_threshold_m: float = 100.0
    nighttime_hours_utc: tuple[int, int] = (0, 6)   # half-open: hour ∈ [start, end)
    base_dark_score: float = 0.7
    risk_increment: float = 0.1


def _is_in_any_zone(lat: float, lon: float, zones: Iterable[ContestedZone]) -> bool:
    return any(
        z.bbox[0] <= lon <= z.bbox[2] and z.bbox[1] <= lat <= z.bbox[3] for z in zones
    )


def _compute_dark_score(v: Vessel, cfg: DarkVesselConfig) -> float:
    score = cfg.base_dark_score
    if (v.length_m or 0) > cfg.large_vessel_threshold_m:
        score += cfg.risk_increment
    if _is_in_any_zone(v.lat, v.lon, cfg.contested_zones):
        score += cfg.risk_increment
    h = v.timestamp.hour
    night_start, night_end = cfg.nighttime_hours_utc
    if night_start <= h < night_end:
        score += cfg.risk_increment
    return min(1.0, round(score, 3))


def cross_reference(
    sar_vessels: list[Vessel],
    ais_records: list[AISRecord],
    config: DarkVesselConfig | None = None,
) -> list[Vessel]:
    """Tag each SAR vessel as BROADCASTING (with attached MMSI) or DARK.

    Pure function — does not mutate input lists. Returns new Vessel objects
    with updated ``ais_status``, ``mmsi``, ``vessel_name``, ``flag``,
    ``ais_match_distance_km``, and ``dark_vessel_score`` fields.
    """
    cfg = config or DarkVesselConfig()
    tolerance_seconds = cfg.time_tolerance_min * 60.0

    enriched: list[Vessel] = []
    matched_ais_ids: set[str] = set()

    for v in sar_vessels:
        # Candidate AIS broadcasts within time tolerance
        in_time_window = [
            a for a in ais_records
            if abs((a.timestamp - v.timestamp).total_seconds()) <= tolerance_seconds
        ]
        # ...further filtered by spatial tolerance
        candidates = [
            (a, haversine_km(v.lat, v.lon, a.lat, a.lon)) for a in in_time_window
        ]
        candidates = [(a, d) for (a, d) in candidates if d <= cfg.spatial_tolerance_km]

        copy = v.model_copy(deep=True)

        if candidates:
            best, dist = min(candidates, key=lambda pair: pair[1])
            matched_ais_ids.add(best.mmsi)
            copy.ais_status = AISStatus.BROADCASTING
            copy.mmsi = best.mmsi
            copy.vessel_name = best.name or copy.vessel_name
            copy.flag = best.flag or copy.flag
            copy.ais_match_distance_km = round(dist, 3)
            copy.dark_vessel_score = None
        else:
            copy.ais_status = AISStatus.DARK
            copy.dark_vessel_score = _compute_dark_score(copy, cfg)
            copy.ais_match_distance_km = None

        enriched.append(copy)

    log.info(
        "Dark-vessel cross-reference: %d SAR vessels, %d AIS records → "
        "%d broadcasting / %d dark",
        len(sar_vessels), len(ais_records),
        sum(1 for v in enriched if v.ais_status == AISStatus.BROADCASTING),
        sum(1 for v in enriched if v.ais_status == AISStatus.DARK),
    )
    return enriched


def summarize(vessels: list[Vessel]) -> dict:
    """Quick aggregates for logging / progress streaming."""
    broadcasting = [v for v in vessels if v.ais_status == AISStatus.BROADCASTING]
    dark = [v for v in vessels if v.ais_status == AISStatus.DARK]
    return {
        "total": len(vessels),
        "broadcasting": len(broadcasting),
        "dark": len(dark),
        "high_risk_dark": sum(1 for v in dark if (v.dark_vessel_score or 0) >= 0.9),
    }
