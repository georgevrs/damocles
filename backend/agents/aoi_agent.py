"""Area-of-Interest inference.

Given a set of CompositeEvents, this agent:

  1. Clusters them spatially with HDBSCAN (density-based — no need to pick K).
  2. Wraps each cluster in an alpha-shape polygon (handles archipelago
     geometry better than a convex hull; falls back to a buffered convex
     hull when alpha-shape collapses for n<4 points).
  3. Asks the LLM to name each cluster in Greek + English given the
     centroid, member events, and dominant sources.
  4. Emits a list of ``AoI`` ready for persistence.

This is *not* a citation-discipline agent (no AgentOutput contract). The
naming step is small and bounded; we validate JSON shape but don't enforce
citation_node_ids — the citations are the cluster member IDs themselves.

Demo-readiness rules (post-AoI-quality-audit, May 2026):
  - **Multi-source escalation gate.** A cluster whose member composites all
    share a single source-type (e.g. only Vessel detections, no news,
    no social) is capped at GREEN. The two-strands fusion story of the
    platform is invalidated by AMBER/RED clusters with a single strand,
    and the audit found 9/10 such monocultures in the random sample.
  - **RED escalation rule.** ``fusion.py`` requires `distinct_sensors >= 3
    AND has_dark AND high_signal` for RED, which is unreachable with the
    current data (only Vessel + News sensors active, no Telegram/Flight).
    The AoI agent overrides this for AI AoIs: a cluster gets RED when it
    has multiple source-types AND a "dark + hot-news" pair anywhere in its
    membership. Caller passes per-composite signal flags via the
    ``composite_signals`` parameter.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import numpy as np

from backend.llm.base import LLMMessage, LLMProvider
from backend.models.aoi import AoI, AoISource
from backend.models.event import CompositeEvent, ThreatGrade

log = logging.getLogger(__name__)


# Coordinate-space tunables. Greek territory spans ~10° in lon, ~7° in lat —
# clusters of ~50km in geographic distance are ~0.5° in degrees, which is
# what HDBSCAN's `cluster_selection_epsilon` is sized for.
DEFAULT_MIN_CLUSTER_SIZE = 4
DEFAULT_MIN_SAMPLES = 2
DEFAULT_ALPHA = 0.5

# Minimum buffer (in degrees) used when fallback-hulling a degenerate cluster.
FALLBACK_BUFFER_DEG = 0.05


class AoIAgent:
    """Cluster composite events into named polygons. ``llm`` is optional —
    when None, AoIs are emitted with a deterministic auto-name."""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        *,
        min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        alpha: float = DEFAULT_ALPHA,
    ) -> None:
        self.llm = llm
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.alpha = alpha

    async def infer(
        self,
        composites: list[CompositeEvent],
        *,
        scan_id: str | None = None,
        composite_source_types: dict[str, set[str]] | None = None,
        composite_signals: dict[str, dict[str, bool]] | None = None,
    ) -> list[AoI]:
        """Cluster composites and emit named AoIs.

        ``composite_source_types`` (optional): map composite_id → set of
        source-type labels ({'Vessel', 'NewsEvent', 'SocialSignal'}). When
        provided, the multi-source escalation gate is applied — a cluster
        whose union of source types has fewer than 2 entries is capped at
        GREEN regardless of its worst constituent grade.

        ``composite_signals`` (optional): map composite_id → flags dict
        ({'has_dark', 'has_hot_news', ...}). When provided, a cluster gets
        promoted to RED if it has BOTH ≥2 distinct source-types AND at
        least one dark-vessel signal AND at least one hot-news signal
        across its membership. This works around the unreachable RED
        condition in fusion.py.

        Both optional — when None, the corresponding gate is skipped
        (legacy behaviour preserved).
        """
        if not composites:
            return []

        clusters = _cluster(
            composites,
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
        )
        if not clusters:
            log.info("AoI: no clusters from %d composites", len(composites))
            return []

        log.info("AoI: %d clusters from %d composites", len(clusters), len(composites))
        out: list[AoI] = []
        gated_to_green = 0
        promoted_to_red = 0
        for idx, members in clusters.items():
            polygon_wkt, centroid = _polygon_for(members, alpha=self.alpha)
            if polygon_wkt is None:
                continue
            threat = _dominant_threat(members)

            # Pre-compute cluster-level aggregates once
            cluster_types: set[str] = set()
            cluster_has_dark = False
            cluster_has_hot_news = False
            if composite_source_types is not None or composite_signals is not None:
                for m in members:
                    if composite_source_types is not None:
                        cluster_types |= composite_source_types.get(m.id, set())
                    if composite_signals is not None:
                        flags = composite_signals.get(m.id, {})
                        if flags.get("has_dark"):     cluster_has_dark = True
                        if flags.get("has_hot_news"): cluster_has_hot_news = True

            # RED promotion — applies BEFORE the GREEN demotion gate so a
            # genuinely RED-grade cluster isn't accidentally demoted.
            # Conditions: multi-source AND a dark-vessel AND a hot-news event
            # appear somewhere in the cluster's membership. This is the
            # "AIS-dark vessel confirmed by hostile-coded news" pattern the
            # demo script promises.
            if (composite_signals is not None
                    and len(cluster_types) >= 2
                    and cluster_has_dark
                    and cluster_has_hot_news):
                if threat != ThreatGrade.RED:
                    log.debug("AoI cluster %d promoted %s→RED "
                              "(multi-source dark+hot pattern)",
                              idx, threat.value if threat else "GREEN")
                threat = ThreatGrade.RED
                promoted_to_red += 1

            # Multi-source escalation gate — see module docstring §"Demo-readiness".
            # Without ≥2 distinct source types in the cluster, the "fusion of
            # two strands" claim is unfounded. Cap at GREEN.
            elif composite_source_types is not None and threat in (ThreatGrade.AMBER, ThreatGrade.RED):
                if len(cluster_types) < 2:
                    log.debug("AoI cluster %d demoted %s→GREEN (single-strand: %s)",
                              idx, threat.value, cluster_types or "{}")
                    threat = ThreatGrade.GREEN
                    gated_to_green += 1

            name_el, name_en, description = await self._name(idx, members, centroid, threat)
            out.append(
                AoI(
                    source=AoISource.AI,
                    name_el=name_el,
                    name_en=name_en,
                    description=description,
                    polygon_wkt=polygon_wkt,
                    centroid_lat=centroid[1],
                    centroid_lon=centroid[0],
                    threat_grade=threat.value if threat else None,
                    threat_summary=_summary(members, threat),
                    citation_event_ids=[m.id for m in members],
                    scan_id=scan_id,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
        if gated_to_green:
            log.info("AoI: multi-source gate demoted %d/%d clusters to GREEN",
                     gated_to_green, len(clusters))
        if promoted_to_red:
            log.info("AoI: multi-source+dark+hot rule promoted %d/%d clusters to RED",
                     promoted_to_red, len(clusters))
        return out

    # ──────────────────────────── naming ─────────────────────────────

    async def _name(
        self,
        cluster_idx: int,
        members: list[CompositeEvent],
        centroid: tuple[float, float],
        threat: ThreatGrade | None,
    ) -> tuple[str, str, str]:
        if self.llm is None:
            fallback_el = f"Συστάδα {cluster_idx + 1}"
            fallback_en = f"Cluster {cluster_idx + 1}"
            return fallback_el, fallback_en, _summary(members, threat)

        sample_summaries = [m.summary for m in members[:3] if m.summary]
        prompt = (
            "Δώσε σύντομο όνομα στα ελληνικά ΚΑΙ στα αγγλικά για μια περιοχή ενδιαφέροντος "
            "βάσει του centroid και των γεγονότων που τη συγκροτούν. Επέστρεψε ΜΟΝΟ JSON.\n\n"
            f"centroid_lon: {centroid[0]:.3f}\n"
            f"centroid_lat: {centroid[1]:.3f}\n"
            f"threat_grade: {threat.value if threat else 'GREEN'}\n"
            f"member_count: {len(members)}\n"
            f"sample_summaries: {sample_summaries}\n\n"
            'Σχήμα: {"name_el": "<2-4 λέξεις, π.χ. \'Λεκάνη Λήμνου\'>", '
            '"name_en": "<2-4 words>", '
            '"description": "<μία πρόταση στα αγγλικά>"}'
        )
        try:
            resp = await self.llm.complete(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=256,
                json_mode=True,
            )
            data = json.loads(resp.content)
            return (
                str(data.get("name_el") or f"Συστάδα {cluster_idx + 1}").strip(),
                str(data.get("name_en") or f"Cluster {cluster_idx + 1}").strip(),
                str(data.get("description") or _summary(members, threat)).strip(),
            )
        except Exception as exc:
            log.warning("AoI name LLM call failed: %s — using fallback", exc)
            return (f"Συστάδα {cluster_idx + 1}", f"Cluster {cluster_idx + 1}",
                    _summary(members, threat))


# ────────────────────────────── geometry ─────────────────────────────

def _cluster(
    composites: list[CompositeEvent],
    *,
    min_cluster_size: int,
    min_samples: int,
) -> dict[int, list[CompositeEvent]]:
    """Group composites by HDBSCAN label, drop noise (label=-1)."""
    pts: list[tuple[float, float]] = []
    keep: list[CompositeEvent] = []
    for c in composites:
        if c.centroid_lat is None or c.centroid_lon is None:
            continue
        pts.append((c.centroid_lon, c.centroid_lat))
        keep.append(c)
    if len(pts) < min_cluster_size:
        return {}

    try:
        import hdbscan
    except ImportError:
        log.warning("hdbscan not installed; AoI clustering disabled")
        return {}

    arr = np.array(pts, dtype=np.float64)
    labels = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_epsilon=0.0,
    ).fit_predict(arr)

    out: dict[int, list[CompositeEvent]] = {}
    for label, comp in zip(labels.tolist(), keep):
        if label == -1:
            continue
        out.setdefault(int(label), []).append(comp)
    # Renumber labels to 0..N-1 for stable display
    return {i: out[k] for i, k in enumerate(sorted(out.keys()))}


def _polygon_for(
    members: list[CompositeEvent],
    *,
    alpha: float,
) -> tuple[str | None, tuple[float, float]]:
    """Returns (polygon_wkt, centroid) for a cluster. Falls back to a
    buffered convex hull when alpha-shape can't form a valid polygon."""
    pts = [(m.centroid_lon, m.centroid_lat) for m in members
           if m.centroid_lon is not None and m.centroid_lat is not None]
    if len(pts) < 3:
        # Single point or two-point cluster: buffer with a small disk so the
        # frontend has a non-degenerate polygon to render.
        from shapely.geometry import Point, MultiPoint
        if len(pts) == 0:
            return None, (0.0, 0.0)
        geom = MultiPoint(pts).buffer(FALLBACK_BUFFER_DEG)
        c = geom.centroid
        return geom.wkt, (c.x, c.y)

    from shapely.geometry import MultiPoint, Polygon
    centroid_pt = MultiPoint(pts).centroid

    try:
        import alphashape
        shape = alphashape.alphashape(pts, alpha)
        if shape is None or shape.is_empty or shape.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"degenerate alpha-shape ({getattr(shape, 'geom_type', None)})")
        return shape.wkt, (centroid_pt.x, centroid_pt.y)
    except Exception as exc:
        log.debug("alpha-shape failed (%s); falling back to buffered convex hull", exc)
        hull = MultiPoint(pts).convex_hull.buffer(FALLBACK_BUFFER_DEG)
        if not isinstance(hull, Polygon) and hull.geom_type != "MultiPolygon":
            return None, (centroid_pt.x, centroid_pt.y)
        return hull.wkt, (centroid_pt.x, centroid_pt.y)


def _dominant_threat(members: list[CompositeEvent]) -> ThreatGrade | None:
    if not members:
        return None
    order = {ThreatGrade.RED: 3, ThreatGrade.AMBER: 2, ThreatGrade.GREEN: 1}
    return max(members, key=lambda m: order.get(m.threat_grade, 0)).threat_grade


def _summary(members: list[CompositeEvent], threat: ThreatGrade | None) -> str:
    grade = threat.value if threat else "GREEN"
    return f"{len(members)} composite events, peak threat {grade}"
