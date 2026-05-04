"""Fusion engine unit tests.

Synthetic events with known geospatial/temporal relationships verify:
  - co-located, contemporaneous events from different sensors fuse
  - distant or stale events do not
  - same-sensor events never pair (cross-sensor only)
  - threat grading rules (GREEN/AMBER/RED)
  - SocialSignals without geo correlate via the bbox-default fallback
  - CompositeEvent confidence and corroboration_count are computed correctly
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models.event import (
    AISStatus,
    NewsEvent,
    SocialSignal,
    ThreatGrade,
    Vessel,
)
from backend.sensors.fusion import FusionConfig, FusionEngine

UTC_NOON = datetime(2024, 3, 17, 12, 0, tzinfo=timezone.utc)
DEFAULT_LAT = 37.5
DEFAULT_LON = 25.5


def _vessel(lat: float, lon: float, *, dark: bool = False, **kw) -> Vessel:
    return Vessel(
        lat=lat, lon=lon,
        timestamp=kw.pop("timestamp", UTC_NOON),
        detection_source="SAR",
        confidence=kw.pop("confidence", 0.85),
        length_m=kw.pop("length_m", 50.0),
        ais_status=AISStatus.DARK if dark else AISStatus.BROADCASTING,
        dark_vessel_score=kw.pop("dark_vessel_score", 0.95) if dark else None,
        **kw,
    )


def _news(lat: float, lon: float, *, goldstein: float = -3.0, **kw) -> NewsEvent:
    return NewsEvent(
        source_url=kw.pop("source_url", "https://example.com/x"),
        source_name=kw.pop("source_name", "example.com"),
        headline=kw.pop("headline", "test"),
        timestamp=kw.pop("timestamp", UTC_NOON),
        lat=lat, lon=lon,
        goldstein_scale=goldstein,
        cameo_code=kw.pop("cameo_code", "1822"),
        mentions=kw.pop("mentions", 5),
        **kw,
    )


def _social(text: str = "test", *, ts: datetime | None = None, **kw) -> SocialSignal:
    return SocialSignal(
        channel=kw.pop("channel", "@aegeanwatch"),
        message_id=kw.pop("message_id", "m1"),
        text=text,
        timestamp=ts or UTC_NOON,
        language=kw.pop("language", "en"),
        views=kw.pop("views", 100),
        **kw,
    )


# ───────────────────────────────────────────────────────────────────────────────
# Correlation: cross-sensor only
# ───────────────────────────────────────────────────────────────────────────────
def test_two_co_located_contemporaneous_events_fuse():
    fe = FusionEngine()
    v = _vessel(37.5, 25.5)
    n = _news(37.5, 25.5)   # same place, same time, different sensor
    res = fe.fuse(vessels=[v], news=[n])
    # Exactly one cluster containing both events
    assert len(res.composites) == 1
    composite = res.composites[0]
    assert set(composite.source_node_ids) == {v.id, n.id}
    assert composite.corroboration_count == 2
    assert len(res.pairwise_edges) == 1


def test_distant_events_do_not_fuse():
    fe = FusionEngine()
    v = _vessel(37.5, 25.5)
    n = _news(50.0, 4.5)   # Brussels — way outside any tolerance
    res = fe.fuse(vessels=[v], news=[n])
    assert len(res.composites) == 2   # two solo composites
    assert len(res.pairwise_edges) == 0


def test_temporally_stale_events_do_not_fuse():
    fe = FusionEngine()
    v = _vessel(37.5, 25.5, timestamp=UTC_NOON)
    n = _news(37.5, 25.5, timestamp=UTC_NOON + timedelta(days=3))   # > 12 h GDELT window
    res = fe.fuse(vessels=[v], news=[n])
    assert len(res.composites) == 2
    assert len(res.pairwise_edges) == 0


def test_same_sensor_never_pairs():
    fe = FusionEngine()
    # Two vessels right next to each other — should not fuse (same sensor).
    v1 = _vessel(37.5, 25.5)
    v2 = _vessel(37.5005, 25.5005)
    res = fe.fuse(vessels=[v1, v2])
    assert len(res.pairwise_edges) == 0
    assert len(res.composites) == 2


# ───────────────────────────────────────────────────────────────────────────────
# Clustering: chains of correlations form a single composite
# ───────────────────────────────────────────────────────────────────────────────
def test_three_sensor_chain_clusters_into_one_composite():
    fe = FusionEngine()
    v = _vessel(37.5, 25.5)
    n = _news(37.6, 25.6)              # ~14 km from v — inside GDELT 50 km
    s = _social()                       # no geo, falls back to default centroid
    res = fe.fuse(vessels=[v], news=[n], social=[s],
                  default_lat=37.5, default_lon=25.5)
    assert len(res.composites) == 1
    c = res.composites[0]
    assert c.corroboration_count == 3
    assert {v.id, n.id, s.id} == set(c.source_node_ids)


# ───────────────────────────────────────────────────────────────────────────────
# Threat grading
# ───────────────────────────────────────────────────────────────────────────────
def test_solo_low_signal_event_is_green():
    fe = FusionEngine()
    res = fe.fuse(news=[_news(37.5, 25.5, goldstein=-1.0)])
    assert res.composites[0].threat_grade == ThreatGrade.GREEN


def test_two_sensor_or_high_goldstein_is_amber():
    fe = FusionEngine()
    # Two-sensor case
    v = _vessel(37.5, 25.5)
    n = _news(37.5, 25.5, goldstein=-1.0)
    res = fe.fuse(vessels=[v], news=[n])
    assert res.composites[0].threat_grade == ThreatGrade.AMBER

    # High-goldstein solo case
    res_solo = fe.fuse(news=[_news(37.5, 25.5, goldstein=-9.0)])
    assert res_solo.composites[0].threat_grade == ThreatGrade.AMBER


def test_red_requires_three_sensors_dark_vessel_high_signal():
    fe = FusionEngine()
    v = _vessel(37.5, 25.5, dark=True)
    n = _news(37.5, 25.5, goldstein=-8.0)
    s = _social()
    res = fe.fuse(vessels=[v], news=[n], social=[s],
                  default_lat=37.5, default_lon=25.5)
    assert len(res.composites) == 1
    assert res.composites[0].threat_grade == ThreatGrade.RED


def test_dark_vessel_alone_does_not_redline():
    """A dark vessel without corroboration is still AMBER, not RED."""
    fe = FusionEngine()
    v = _vessel(37.5, 25.5, dark=True)
    res = fe.fuse(vessels=[v])
    # Solo dark vessel has high_signal=True but distinct_sensors=1, so AMBER.
    assert res.composites[0].threat_grade == ThreatGrade.AMBER


# ───────────────────────────────────────────────────────────────────────────────
# Composite metadata
# ───────────────────────────────────────────────────────────────────────────────
def test_composite_centroid_is_average_of_constituents():
    fe = FusionEngine()
    v = _vessel(37.4, 25.4)
    n = _news(37.6, 25.6)
    res = fe.fuse(vessels=[v], news=[n])
    c = res.composites[0]
    assert c.centroid_lat is not None and c.centroid_lon is not None
    assert abs(c.centroid_lat - 37.5) < 1e-9
    assert abs(c.centroid_lon - 25.5) < 1e-9


def test_composite_confidence_is_boosted_by_multiple_sensors():
    fe = FusionEngine()
    solo  = fe.fuse(vessels=[_vessel(37.5, 25.5, confidence=0.6)])
    multi = fe.fuse(vessels=[_vessel(37.5, 25.5, confidence=0.6)],
                    news=[_news(37.5, 25.5)])
    assert multi.composites[0].confidence > solo.composites[0].confidence


def test_pairwise_edges_returned_for_visualization():
    fe = FusionEngine()
    v = _vessel(37.5, 25.5)
    n = _news(37.5, 25.5)
    res = fe.fuse(vessels=[v], news=[n])
    assert len(res.pairwise_edges) == 1
    a_id, b_id, score = res.pairwise_edges[0]
    assert {a_id, b_id} == {v.id, n.id}
    assert 0.5 < score <= 1.0


# ───────────────────────────────────────────────────────────────────────────────
# Edge cases
# ───────────────────────────────────────────────────────────────────────────────
def test_empty_input_returns_empty_result():
    fe = FusionEngine()
    res = fe.fuse()
    assert res.composites == []
    assert res.stats["nodes"] == 0


def test_custom_thresholds_override_defaults():
    """Stricter min_corr_score should split a previously-fused pair."""
    cfg = FusionConfig(min_corr_score=0.99)
    fe = FusionEngine(cfg)
    v = _vessel(37.5, 25.5)
    n = _news(37.5, 25.5, timestamp=UTC_NOON + timedelta(hours=10))   # corr ~0.93, won't fuse at 0.99
    res = fe.fuse(vessels=[v], news=[n])
    assert len(res.composites) == 2
