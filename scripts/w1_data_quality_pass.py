"""Week-1 data quality pass — one-shot script.

Reproducible, idempotent. Run after `scripts/build_water_mask.py` has
written `data/geojson/_water_surface.geojson`.

Phases:

  1. Run the runtime ALTER TABLE migrations (no-op if already migrated).
  2. Backfill `is_water` on every row of raw_ais and raw_sar using the
     water mask.
  3. Resolve every composite_event to its set of source types (Vessel /
     NewsEvent / SocialSignal). Build the `composite_source_types` map.
  4. Resolve every composite to a "is_water" flag based on its sources —
     a composite whose ONLY sources are land-SAR is excluded from AoI
     re-inference.
  5. Delete existing AI AoIs (user-drawn polygons are preserved).
  6. Re-run AoIAgent.infer() over the water-filtered composites, with the
     multi-source escalation gate enabled.
  7. Persist the new AoIs.
  8. Print before/after stats.

Run:
    NEO4J_PASSWORD=damocles2026 uv run python scripts/w1_data_quality_pass.py

Exits non-zero on any phase failure so it can drop into CI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Quiet noisy uv VIRTUAL_ENV warnings
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Ensure repo root is on sys.path when run via uv (it usually is, but belt-and-braces)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("w1")

# Mute noisy DEBUGs inside the AoI agent / hdbscan
logging.getLogger("backend.agents.aoi_agent").setLevel(logging.INFO)


def main() -> int:
    from backend.sensors._water_mask import diagnostics, is_over_water
    from backend.store import get_store
    from backend.models.event import CompositeEvent, ThreatGrade

    diag = diagnostics()
    log.info("water mask: %s", diag)
    if diag.get("status") != "enabled":
        log.error("water mask disabled — refusing to run. Did you run scripts/build_water_mask.py?")
        return 1

    store = get_store()
    conn  = store.connect()

    # ────────── Phase 2: re-tag is_water on existing rows ──────────
    # We always recompute on every run (even if the column is populated) — the
    # water mask geometry can change between runs (e.g. when we tighten
    # neighbour-land rectangles) and stale tags would silently re-introduce
    # land false-positives.
    log.info("phase 2: re-tagging is_water on every row")
    for table, lat_col, lon_col in (("raw_ais", "lat", "lon"), ("raw_sar", "lat", "lon")):
        rows = conn.execute(
            f"SELECT cache_key, event_id, {lat_col}, {lon_col} FROM {table}"
        ).fetchall()
        log.info("  %s: %d rows to tag", table, len(rows))
        if not rows: continue
        updates = []
        for ck, eid, lat, lon in rows:
            buf = 0.005 if table == "raw_sar" else 0.01
            updates.append((bool(is_over_water(lat, lon, coastal_buffer_deg=buf)), ck, eid))
        # Batch updates
        BATCH = 500
        for i in range(0, len(updates), BATCH):
            chunk = updates[i:i+BATCH]
            conn.executemany(
                f"UPDATE {table} SET is_water = ? WHERE cache_key = ? AND event_id = ?",
                chunk,
            )
        # Quick report
        water = conn.execute(f"SELECT count(*) FROM {table} WHERE is_water").fetchone()[0]
        land  = conn.execute(f"SELECT count(*) FROM {table} WHERE is_water = false").fetchone()[0]
        total = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        log.info("  %s: water=%d land=%d total=%d (%.1f%% over water)",
                 table, water, land, total, 100 * water / max(1, total))

    # ────────── Phase 2.5: synthesise "dark" AIS status ──────────
    # The cross_reference dark-vessel step only fires when both SAR and live
    # AIS broadcasts are present. Our scan data has no AISStream input —
    # so every SAR detection in raw_ais has ais_status='unknown' even though
    # operationally an SAR-seen vessel with no MMSI IS the definition of dark.
    # Promote them now so the RED-promotion rule has signal to work with.
    log.info("phase 2.5: marking SAR-only AIS rows (no MMSI, over water) as 'dark'")
    conn.execute("""
        UPDATE raw_ais
           SET ais_status = 'dark'
         WHERE mmsi IS NULL
           AND is_water = true
           AND (ais_status IS NULL OR ais_status = 'unknown')
    """)
    promoted = conn.execute("SELECT count(*) FROM raw_ais WHERE ais_status='dark'").fetchone()[0]
    log.info("  raw_ais.ais_status='dark' total now: %d", promoted)

    # ────────── Phase 3+4: build composite → {source types, has_water_source} ──
    log.info("phase 3-4: resolving composite source types + water-membership")
    composites_raw = conn.execute("""
        SELECT id, scan_id, threat_grade, confidence, summary,
               centroid_lat, centroid_lon, time_window_start, time_window_end,
               source_node_ids_json, created_at
          FROM composite_events
    """).fetchall()
    log.info("  %d composite events in store", len(composites_raw))

    # One-shot lookup tables
    ais_types = {row[0]: True for row in conn.execute("SELECT event_id FROM raw_ais").fetchall()}
    news_types = {row[0]: True for row in conn.execute("SELECT event_id FROM raw_news").fetchall()}
    social_types = {row[0]: True for row in conn.execute("SELECT event_id FROM raw_social").fetchall()}
    ais_water = {row[0]: bool(row[1]) for row in conn.execute("SELECT event_id, is_water FROM raw_ais").fetchall()}
    # Per-source signal flags — needed for RED promotion in the AoI agent
    ais_dark = {row[0] for row in conn.execute("SELECT event_id FROM raw_ais WHERE ais_status='dark'").fetchall()}
    # "Hot" news = Goldstein scale ≤ -5 (matches fusion.py default threshold)
    hot_news = {row[0] for row in conn.execute(
        "SELECT event_id FROM raw_news WHERE goldstein_scale IS NOT NULL AND goldstein_scale <= -5.0"
    ).fetchall()}
    log.info("  signals: %d dark vessels, %d hot news events", len(ais_dark), len(hot_news))

    composite_source_types: dict[str, set[str]] = {}
    composite_signals:      dict[str, dict[str, bool]] = {}
    composite_has_water:    dict[str, bool]     = {}
    composite_has_landonly_vessel: dict[str, bool] = {}

    composites: list[CompositeEvent] = []
    for row in composites_raw:
        cid = row[0]
        try:
            src_ids = json.loads(row[9] or "[]")
        except (TypeError, json.JSONDecodeError):
            src_ids = []

        types: set[str] = set()
        has_water_source = False
        has_landonly = False
        has_dark = False
        has_hot_news = False
        for sid in src_ids:
            if sid in ais_types:
                types.add("Vessel")
                if ais_water.get(sid, True):
                    has_water_source = True
                else:
                    has_landonly = True
                if sid in ais_dark:
                    has_dark = True
            if sid in news_types:
                types.add("NewsEvent")
                has_water_source = True   # news is geographic context, not on/over water — count as valid
                if sid in hot_news:
                    has_hot_news = True
            if sid in social_types:
                types.add("SocialSignal")
                has_water_source = True

        composite_source_types[cid] = types
        composite_signals[cid] = {"has_dark": has_dark, "has_hot_news": has_hot_news}
        composite_has_water[cid] = has_water_source
        # Vessel-only + every vessel is land = composite is a SAR false positive
        if types == {"Vessel"} and not has_water_source and has_landonly:
            composite_has_landonly_vessel[cid] = True

        composites.append(CompositeEvent(
            id=cid,
            threat_grade=ThreatGrade(row[2]) if row[2] else ThreatGrade.GREEN,
            confidence=row[3] or 0.0,
            summary=row[4] or "",
            centroid_lat=row[5],
            centroid_lon=row[6],
            time_window_start=row[7],
            time_window_end=row[8],
            source_node_ids=src_ids,
            created_at=row[10],
        ))

    # Stats
    landonly = sum(1 for v in composite_has_landonly_vessel.values() if v)
    monoculture = sum(1 for t in composite_source_types.values() if len(t) <= 1)
    log.info("  source-types: vessel-only=%d, news-only=%d, social-only=%d, mixed=%d",
             sum(1 for t in composite_source_types.values() if t == {"Vessel"}),
             sum(1 for t in composite_source_types.values() if t == {"NewsEvent"}),
             sum(1 for t in composite_source_types.values() if t == {"SocialSignal"}),
             sum(1 for t in composite_source_types.values() if len(t) >= 2))
    log.info("  composites with land-only-vessel sources (will drop): %d / %d",
             landonly, len(composites))
    log.info("  monoculture composites (would be GREEN-capped by gate): %d / %d",
             monoculture, len(composites))

    # Filter composites — drop land-only-vessel ones; keep everything else
    filtered = [c for c in composites if not composite_has_landonly_vessel.get(c.id)]
    log.info("phase 5: dropped %d land-only composites; %d → %d for AoI inference",
             len(composites) - len(filtered), len(composites), len(filtered))

    # ────────── Phase 5: rebuild aoi table (drop AI rows, keep user-drawn) ──
    # We rebuild the table instead of DELETE because DuckDB's index can get
    # out of sync with the heap and DELETE on indexed rows fails with
    # "FATAL: Failed to delete all rows from index" — a known DuckDB issue.
    # CREATE-AS + DROP + RENAME has no such problem.
    pre_ai   = conn.execute("SELECT count(*) FROM aoi WHERE source='ai'").fetchone()[0]
    pre_user = conn.execute("SELECT count(*) FROM aoi WHERE source='user'").fetchone()[0]
    log.info("phase 5: pre-state: %d AI AoIs, %d user AoIs — rebuilding", pre_ai, pre_user)
    conn.execute("CREATE OR REPLACE TABLE _aoi_keep AS SELECT * FROM aoi WHERE source = 'user'")
    conn.execute("DROP TABLE aoi")
    conn.execute("ALTER TABLE _aoi_keep RENAME TO aoi")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aoi_source ON aoi (source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aoi_scan   ON aoi (scan_id)")
    conn.commit()
    log.info("  cleared %d AI AoIs (user-drawn preserved)", pre_ai)

    # ────────── Phase 6: re-run AoI agent with the multi-source gate ──────
    from backend.agents.aoi_agent import AoIAgent
    from backend.llm.factory import get_provider

    log.info("phase 6: re-running AoIAgent.infer() with multi-source gate")
    try:
        llm = get_provider()
    except Exception as exc:
        log.warning("LLM provider unavailable (%s) — proceeding with deterministic names", exc)
        llm = None

    agent = AoIAgent(llm=llm)
    scan_id = "scan-w1-quality-pass"

    # Tally pre-promotion signal coverage so we know what we're working with
    promote_eligible = sum(
        1 for c in filtered
        if composite_signals.get(c.id, {}).get("has_dark")
           and composite_signals.get(c.id, {}).get("has_hot_news")
           and len(composite_source_types.get(c.id, set())) >= 2
    )
    log.info("  composites eligible for direct RED (dark+hot+multi-source): %d", promote_eligible)

    async def run():
        return await agent.infer(filtered, scan_id=scan_id,
                                  composite_source_types=composite_source_types,
                                  composite_signals=composite_signals)
    aois = asyncio.run(run())

    if not aois:
        log.warning("no AoIs produced — check thresholds / data")
        return 1

    log.info("phase 6: %d new AoIs produced", len(aois))
    by_grade: dict[str, int] = {}
    for a in aois:
        g = a.threat_grade or "GREEN"
        by_grade[g] = by_grade.get(g, 0) + 1
    log.info("  grade distribution: %s", by_grade)

    # ────────── Phase 7: persist ──────────
    n = store.upsert_aoi(aois)
    log.info("phase 7: persisted %d AoI rows to store", n)

    # ────────── Phase 8: final stats ──────────
    post = conn.execute("SELECT count(*), source FROM aoi GROUP BY source").fetchall()
    log.info("phase 8: post-state: %s", dict((s, c) for c, s in post))
    print()
    print("════ before / after ════")
    print(f"  AI AoIs:           {pre_ai:4d} → {sum(c for c, s in post if s == 'ai'):4d}")
    print(f"  RED AoIs:          {by_grade.get('RED', 0):4d}")
    print(f"  AMBER AoIs:        {by_grade.get('AMBER', 0):4d}")
    print(f"  GREEN AoIs:        {by_grade.get('GREEN', 0):4d}")
    print(f"  land-only dropped: {len(composites) - len(filtered):4d} composites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
