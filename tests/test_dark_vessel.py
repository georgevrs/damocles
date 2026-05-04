"""Dark-vessel cross-reference unit tests.

Synthetic fixtures only — no network, no live AIS. Validates:
  - exact match within tolerances → BROADCASTING + MMSI attached
  - no match (out of time / out of space / no AIS at all) → DARK
  - dark-score risk-factor logic (size, contested zone, nighttime)
  - closest-AIS tiebreaker
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models.event import AISStatus, Vessel
from backend.sensors.dark_vessel import (
    AISRecord,
    ContestedZone,
    DarkVesselConfig,
    cross_reference,
    summarize,
)

UTC_NOW = datetime(2024, 3, 17, 14, 30, tzinfo=timezone.utc)


def _vessel(lat: float, lon: float, **kw) -> Vessel:
    return Vessel(
        lat=lat, lon=lon,
        timestamp=kw.pop("timestamp", UTC_NOW),
        detection_source="SAR",
        confidence=kw.pop("confidence", 0.8),
        length_m=kw.pop("length_m", 50.0),
        **kw,
    )


def _ais(mmsi: str, lat: float, lon: float, **kw) -> AISRecord:
    return AISRecord(
        mmsi=mmsi, lat=lat, lon=lon,
        timestamp=kw.pop("timestamp", UTC_NOW),
        **kw,
    )


# ───────────────────────────────────────────────────────────────────────────────
# Matching
# ───────────────────────────────────────────────────────────────────────────────
def test_exact_match_marks_broadcasting():
    sar = [_vessel(37.5, 25.5)]
    ais = [_ais("240123456", 37.5005, 25.5005, name="GREEK STAR")]   # ~70 m away

    out = cross_reference(sar, ais)

    assert len(out) == 1
    v = out[0]
    assert v.ais_status == AISStatus.BROADCASTING
    assert v.mmsi == "240123456"
    assert v.vessel_name == "GREEK STAR"
    assert v.dark_vessel_score is None
    assert v.ais_match_distance_km is not None
    assert v.ais_match_distance_km < 0.1   # well under 100 m


def test_out_of_space_marks_dark():
    sar = [_vessel(37.5, 25.5)]
    ais = [_ais("240123456", 37.55, 25.55)]   # ~6 km away — outside 2 km tolerance

    out = cross_reference(sar, ais)

    assert out[0].ais_status == AISStatus.DARK
    assert out[0].dark_vessel_score is not None
    assert out[0].mmsi is None


def test_out_of_time_marks_dark():
    sar = [_vessel(37.5, 25.5)]
    ais = [_ais("240123456", 37.5, 25.5,
                timestamp=UTC_NOW + timedelta(hours=2))]   # ±30 min default

    out = cross_reference(sar, ais)
    assert out[0].ais_status == AISStatus.DARK


def test_empty_ais_marks_all_dark():
    sar = [_vessel(37.5, 25.5), _vessel(38.0, 26.0)]
    out = cross_reference(sar, [])
    assert all(v.ais_status == AISStatus.DARK for v in out)


def test_picks_closest_when_multiple_candidates():
    sar = [_vessel(37.5, 25.5)]
    ais = [
        _ais("AAA", 37.510, 25.510),    # ~1.4 km
        _ais("BBB", 37.5005, 25.5005),  # ~70 m   ← closest
        _ais("CCC", 37.515, 25.515),    # ~2.0 km, on edge
    ]

    out = cross_reference(sar, ais)
    assert out[0].mmsi == "BBB"


# ───────────────────────────────────────────────────────────────────────────────
# Dark-score risk factors
# ───────────────────────────────────────────────────────────────────────────────
def test_dark_score_baseline():
    """Small vessel, daylight, outside contested zone — should be the base 0.7."""
    sar = [_vessel(37.0, 24.0,    # west of contested zone
                   timestamp=datetime(2024, 3, 17, 14, 0, tzinfo=timezone.utc),
                   length_m=30.0)]
    out = cross_reference(sar, [])
    assert out[0].dark_vessel_score == 0.7


def test_dark_score_large_vessel_boost():
    sar = [_vessel(37.0, 24.0,
                   timestamp=datetime(2024, 3, 17, 14, 0, tzinfo=timezone.utc),
                   length_m=150.0)]
    out = cross_reference(sar, [])
    assert out[0].dark_vessel_score == 0.8


def test_dark_score_contested_zone_boost():
    sar = [_vessel(37.5, 27.0,    # east of 26°E → in default contested zone
                   timestamp=datetime(2024, 3, 17, 14, 0, tzinfo=timezone.utc),
                   length_m=30.0)]
    out = cross_reference(sar, [])
    assert out[0].dark_vessel_score == 0.8


def test_dark_score_nighttime_boost():
    sar = [_vessel(37.0, 24.0,
                   timestamp=datetime(2024, 3, 17, 3, 30, tzinfo=timezone.utc),
                   length_m=30.0)]
    out = cross_reference(sar, [])
    assert out[0].dark_vessel_score == 0.8


def test_dark_score_all_factors_max_at_one():
    # 200 m vessel + east of 26°E + 03:00 UTC = 0.7 + 3 × 0.1 = 1.0
    sar = [_vessel(37.5, 27.0,
                   timestamp=datetime(2024, 3, 17, 3, 30, tzinfo=timezone.utc),
                   length_m=200.0)]
    out = cross_reference(sar, [])
    assert out[0].dark_vessel_score == 1.0


def test_custom_contested_zones_override():
    cfg = DarkVesselConfig(contested_zones=[
        ContestedZone(name="custom", bbox=(20.0, 30.0, 22.0, 35.0)),
    ])
    sar = [_vessel(37.5, 27.0,
                   timestamp=datetime(2024, 3, 17, 14, 0, tzinfo=timezone.utc),
                   length_m=30.0)]
    out = cross_reference(sar, [], config=cfg)
    # Vessel sits outside the custom zone → no contested-zone boost
    assert out[0].dark_vessel_score == 0.7


# ───────────────────────────────────────────────────────────────────────────────
# Aggregate helper
# ───────────────────────────────────────────────────────────────────────────────
def test_summarize_counts():
    vessels = [
        _vessel(37.0, 24.0),
        _vessel(37.0, 24.0),
        _vessel(37.5, 27.0,
                timestamp=datetime(2024, 3, 17, 3, 30, tzinfo=timezone.utc),
                length_m=200.0),
    ]
    ais = [_ais("X", 37.0, 24.0)]
    out = cross_reference(vessels, ais)
    s = summarize(out)
    assert s["total"] == 3
    assert s["broadcasting"] >= 1
    assert s["dark"] == s["total"] - s["broadcasting"]
    # The 3rd vessel maxes out the dark score (1.0) → counts as high_risk_dark
    assert s["high_risk_dark"] >= 1


def test_does_not_mutate_inputs():
    sar = [_vessel(37.5, 25.5)]
    original_status = sar[0].ais_status
    ais = [_ais("AAA", 37.5, 25.5)]
    _ = cross_reference(sar, ais)
    assert sar[0].ais_status == original_status   # original Vessel untouched
