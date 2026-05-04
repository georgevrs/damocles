"""Spatiotemporal fusion engine.

Takes typed sensor events (Vessel, NewsEvent, SocialSignal, AirspaceEvent),
correlates them across sensors using a spatiotemporal "bubble" per event,
and emits ``CompositeEvent``s. CompositeEvents are what the agent layer
reasons over and what the brief cites — so the fusion algorithm is the
central pillar of the citation chain.

Algorithm
---------
1. Each sensor event has a tolerance bubble: ``(spatial_radius_km, temporal_window_h)``
   keyed by sensor name. Defaults from the plan:
       geospatial : 5 km   ±2 h
       gdelt      : 50 km  ±12 h
       telegram   : 100 km ±24 h
       airspace   : 10 km  ±1 h

2. For each pair of events from **different** sensors, compute a correlation:
       d_km   = haversine(a.lat, a.lon, b.lat, b.lon)
       dt_h   = |a.t - b.t| / hours
       max_r  = max(radius[sensor_a], radius[sensor_b])
       max_w  = max(window[sensor_a], window[sensor_b])
       spatial_score  = max(0, 1 - d_km / max_r)
       temporal_score = max(0, 1 - dt_h / max_w)
       corr_score     = 0.6 * spatial_score + 0.4 * temporal_score

3. Pairs with ``corr_score > min_corr_score`` (default 0.5) form a graph
   of "compatible" events; we run connected components to cluster them.
   Each component (≥1 event) becomes a CompositeEvent.

4. Threat grade is assigned per the plan's matrix:
       GREEN : single source OR low conflict signal
       AMBER : 2+ sources OR high conflict signal
       RED   : 3+ sources AND a dark vessel AND high conflict signal
   Where "high conflict signal" = any GDELT goldstein <= -5 OR any Vessel
   tagged as DARK with dark_vessel_score >= 0.85.

5. Each CompositeEvent gets:
       - source_node_ids:  IDs of every constituent sensor event
       - corroboration_count:  number of *distinct sensors* contributing
       - confidence:  weighted blend of constituent confidences
       - centroid (lat, lon):  average of constituent positions
       - time_window: min/max timestamps across constituents

Telegram messages without lat/lon (the Day 9 NER-derived geo isn't running
yet) are still useful: they correlate by time alone. We give them the
default centroid of the watch bbox as a placeholder spatial coordinate
(passed in via ``default_lat/lon`` by the caller). When NER lands, the
Linguist agent will rewrite those coordinates.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Iterable, Sequence

from backend.models.event import (
    AirspaceEvent,
    AISStatus,
    CompositeEvent,
    NewsEvent,
    SocialSignal,
    ThreatGrade,
    Vessel,
)

from ._geom import haversine_km

log = logging.getLogger(__name__)

# Plan-defined tolerances. Keyed by sensor name.
DEFAULT_SPATIAL_RADIUS_KM: dict[str, float] = {
    "geospatial": 5.0,
    "gdelt":      50.0,
    "telegram":   100.0,
    "airspace":   10.0,
}
DEFAULT_TEMPORAL_WINDOW_H: dict[str, float] = {
    "geospatial": 2.0,
    "gdelt":      12.0,
    "telegram":   24.0,
    "airspace":   1.0,
}


@dataclass
class _Node:
    """Internal helper: a uniform handle on any sensor event for fusion."""
    id: str
    sensor: str
    lat: float | None
    lon: float | None
    timestamp: datetime
    confidence: float
    is_dark_vessel: bool = False
    goldstein: float | None = None


def _to_node(event, sensor: str, default_lat: float, default_lon: float) -> _Node:
    """Lift a typed Pydantic event into a sensor-agnostic _Node."""
    if isinstance(event, Vessel):
        return _Node(
            id=event.id,
            sensor=sensor,
            lat=event.lat,
            lon=event.lon,
            timestamp=_aware(event.timestamp),
            confidence=event.confidence,
            is_dark_vessel=(
                event.ais_status == AISStatus.DARK
                and (event.dark_vessel_score or 0.0) >= 0.85
            ),
        )
    if isinstance(event, NewsEvent):
        return _Node(
            id=event.id, sensor=sensor,
            lat=event.lat, lon=event.lon,
            timestamp=_aware(event.timestamp),
            confidence=min(1.0, 0.5 + (event.mentions / 50.0)),  # mentions is a soft proxy
            goldstein=event.goldstein_scale,
        )
    if isinstance(event, SocialSignal):
        return _Node(
            id=event.id, sensor=sensor,
            lat=(event.lat if event.lat is not None else default_lat),
            lon=(event.lon if event.lon is not None else default_lon),
            timestamp=_aware(event.timestamp),
            # Telegram messages have no inherent confidence — use views as soft signal.
            confidence=min(1.0, 0.4 + (event.views or 0) / 5000.0),
        )
    if isinstance(event, AirspaceEvent):
        return _Node(
            id=event.id, sensor=sensor,
            lat=event.lat, lon=event.lon,
            timestamp=_aware(event.timestamp),
            confidence=0.6,
        )
    raise TypeError(f"Unknown event type for fusion: {type(event).__name__}")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class FusionConfig:
    spatial_radius_km: dict[str, float] = None  # type: ignore[assignment]
    temporal_window_h: dict[str, float] = None  # type: ignore[assignment]
    min_corr_score: float = 0.5
    spatial_weight: float = 0.6
    temporal_weight: float = 0.4
    high_conflict_goldstein: float = -5.0   # any GDELT event at or below this is "hot"

    def __post_init__(self) -> None:
        if self.spatial_radius_km is None:
            self.spatial_radius_km = dict(DEFAULT_SPATIAL_RADIUS_KM)
        if self.temporal_window_h is None:
            self.temporal_window_h = dict(DEFAULT_TEMPORAL_WINDOW_H)


def _correlation(a: _Node, b: _Node, cfg: FusionConfig) -> float:
    """Pair correlation in [0, 1]. Returns 0 when same-sensor or out-of-tolerance."""
    if a.sensor == b.sensor:
        return 0.0
    if a.lat is None or b.lat is None or a.lon is None or b.lon is None:
        return 0.0

    max_r = max(cfg.spatial_radius_km.get(a.sensor, 50.0),
                cfg.spatial_radius_km.get(b.sensor, 50.0))
    max_w = max(cfg.temporal_window_h.get(a.sensor, 24.0),
                cfg.temporal_window_h.get(b.sensor, 24.0))

    d_km = haversine_km(a.lat, a.lon, b.lat, b.lon)
    dt_h = abs((a.timestamp - b.timestamp).total_seconds()) / 3600.0

    if d_km > max_r or dt_h > max_w:
        return 0.0

    spatial = 1.0 - d_km / max_r
    temporal = 1.0 - dt_h / max_w
    return cfg.spatial_weight * spatial + cfg.temporal_weight * temporal


# Union-find — tiny because we only handle hundreds of nodes per fusion call.
class _DSU:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _grade(nodes: list[_Node], distinct_sensors: int, cfg: FusionConfig) -> ThreatGrade:
    has_dark = any(n.is_dark_vessel for n in nodes)
    high_signal = (
        any((n.goldstein or 0.0) <= cfg.high_conflict_goldstein for n in nodes)
        or has_dark
    )

    if distinct_sensors >= 3 and has_dark and high_signal:
        return ThreatGrade.RED
    if distinct_sensors >= 2 or high_signal:
        return ThreatGrade.AMBER
    return ThreatGrade.GREEN


@dataclass
class FusionResult:
    composites: list[CompositeEvent]
    pairwise_edges: list[tuple[str, str, float]]   # (id_a, id_b, corr_score)
    stats: dict


class FusionEngine:
    """Stateless — instantiate per call or reuse, doesn't matter."""

    def __init__(self, config: FusionConfig | None = None):
        self.cfg = config or FusionConfig()

    def fuse(
        self,
        *,
        vessels: Sequence[Vessel] = (),
        news: Sequence[NewsEvent] = (),
        social: Sequence[SocialSignal] = (),
        airspace: Sequence[AirspaceEvent] = (),
        default_lat: float = 0.0,
        default_lon: float = 0.0,
    ) -> FusionResult:
        """Cluster correlated events into CompositeEvents.

        ``default_lat/lon`` are used for SocialSignals that lack geo (until
        the Linguist agent populates lat/lon via NER).
        """
        nodes: list[_Node] = []
        for v in vessels:
            nodes.append(_to_node(v, "geospatial", default_lat, default_lon))
        for n in news:
            nodes.append(_to_node(n, "gdelt", default_lat, default_lon))
        for s in social:
            nodes.append(_to_node(s, "telegram", default_lat, default_lon))
        for a in airspace:
            nodes.append(_to_node(a, "airspace", default_lat, default_lon))

        edges: list[tuple[int, int, float]] = []
        for i, a in enumerate(nodes):
            for j in range(i + 1, len(nodes)):
                b = nodes[j]
                score = _correlation(a, b, self.cfg)
                if score > self.cfg.min_corr_score:
                    edges.append((i, j, score))

        dsu = _DSU(len(nodes))
        for i, j, _s in edges:
            dsu.union(i, j)

        clusters: dict[int, list[int]] = defaultdict(list)
        for k in range(len(nodes)):
            clusters[dsu.find(k)].append(k)

        composites: list[CompositeEvent] = []
        for member_idxs in clusters.values():
            members = [nodes[i] for i in member_idxs]
            sensors_in_cluster = {n.sensor for n in members}
            if len(members) == 1 and len(sensors_in_cluster) == 1:
                # Solo event — still emit a CompositeEvent so every sensor event
                # is reachable from a composite, but mark it GREEN.
                pass
            composites.append(self._make_composite(members, sensors_in_cluster))

        edges_out = [(nodes[i].id, nodes[j].id, round(s, 3)) for i, j, s in edges]
        log.info(
            "Fusion: %d nodes, %d edges, %d composites (RED=%d AMBER=%d GREEN=%d)",
            len(nodes), len(edges), len(composites),
            sum(1 for c in composites if c.threat_grade == ThreatGrade.RED),
            sum(1 for c in composites if c.threat_grade == ThreatGrade.AMBER),
            sum(1 for c in composites if c.threat_grade == ThreatGrade.GREEN),
        )

        return FusionResult(
            composites=composites,
            pairwise_edges=edges_out,
            stats={
                "nodes":         len(nodes),
                "edges":         len(edges),
                "composites":    len(composites),
                "by_sensor":     {s: sum(1 for n in nodes if n.sensor == s)
                                  for s in {n.sensor for n in nodes}},
            },
        )

    # ─── internals ───────────────────────────────────────────────────────────
    def _make_composite(self, members: list[_Node], sensors: Iterable[str]) -> CompositeEvent:
        confidences = [m.confidence for m in members]
        # Weighted blend: more sources -> higher confidence, but capped.
        n = len(members)
        avg_conf = mean(confidences) if confidences else 0.0
        # Boost factor: each additional sensor adds 10% of (1 - avg_conf)
        boost = (len({m.sensor for m in members}) - 1) * 0.10 * (1.0 - avg_conf)
        confidence = min(1.0, avg_conf + boost)

        ts_min = min(m.timestamp for m in members)
        ts_max = max(m.timestamp for m in members)

        # Centroid (only nodes with geo)
        geo = [(m.lat, m.lon) for m in members if m.lat is not None and m.lon is not None]
        if geo:
            cen_lat = mean(lat for lat, _ in geo)
            cen_lon = mean(lon for _, lon in geo)
        else:
            cen_lat = cen_lon = None

        distinct_sensors = len(set(sensors))
        grade = _grade(members, distinct_sensors, self.cfg)

        summary = self._compose_summary(members, distinct_sensors, grade)

        return CompositeEvent(
            threat_grade=grade,
            confidence=round(confidence, 3),
            corroboration_count=distinct_sensors,
            summary=summary,
            source_node_ids=[m.id for m in members],
            centroid_lat=cen_lat,
            centroid_lon=cen_lon,
            time_window_start=ts_min,
            time_window_end=ts_max,
        )

    @staticmethod
    def _compose_summary(members: list[_Node], distinct_sensors: int, grade: ThreatGrade) -> str:
        by_sensor: dict[str, int] = defaultdict(int)
        for m in members:
            by_sensor[m.sensor] += 1
        parts = [f"{count} {sensor}" for sensor, count in sorted(by_sensor.items())]
        dark = sum(1 for m in members if m.is_dark_vessel)
        bits = [
            f"{grade.value} threat",
            f"{distinct_sensors} sensor{'' if distinct_sensors == 1 else 's'}",
            ", ".join(parts),
        ]
        if dark:
            bits.append(f"{dark} dark vessel{'' if dark == 1 else 's'}")
        return " | ".join(bits)
