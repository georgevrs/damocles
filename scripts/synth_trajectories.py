"""Synthesise multi-point AIS trajectories for the demo snapshot.

The W1 demo snapshot has 1238 raw_ais rows, but most are SAR-only (null
MMSI) and the broadcasting ones each appear at a single timestamp. The
trajectory endpoint groups by MMSI and requires ≥N points per vessel,
so it returns an empty FeatureCollection — and the map's trajectories
overlay shows nothing.

For the demo we synthesise plausible 6-8 point random-walk tracks for
the 12 most-visible broadcasting vessels nearest the demo RED AoIs.
Synthesised points are written into raw_ais with the same source label
``ais_synth_demo`` so they're easy to identify or roll back.

Run once; idempotent.

    uv run python scripts/synth_trajectories.py
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.store import get_store   # noqa: E402

SOURCE_TAG = "ais_synth_demo"
POINTS_PER_TRACK = 8
HOURS_BACK = 48
STEP_DEG = 0.035  # ~3-4 km between hops at Greek latitudes
TARGET_TRACKS = 14


def main() -> int:
    rng = random.Random(1337)
    conn = get_store().connect()

    # Remove any prior synth points so this is idempotent. We tag the
    # cache_key with a known prefix so we can identify these later.
    conn.execute("DELETE FROM raw_ais WHERE cache_key LIKE ?", [f"{SOURCE_TAG}%"])

    # Pick the 14 most-recent broadcasting vessels with a named MMSI as
    # the seed positions. If we have <14 we still get whatever's there.
    seeds: list[tuple] = conn.execute(
        """
        SELECT mmsi, vessel_name, flag, length_m, lat, lon, ts
          FROM raw_ais
         WHERE mmsi IS NOT NULL
           AND ais_status = 'broadcasting'
         ORDER BY ts DESC
         LIMIT ?
        """,
        [TARGET_TRACKS],
    ).fetchall()

    if not seeds:
        # Demo snapshot has zero broadcasting MMSIs (all rows are SAR-only
        # dark detections). Fall back: synthesise our own seeds by picking
        # 14 over-water SAR positions near AoI centroids and inventing
        # plausible MMSIs, vessel names, and flags for the demo.
        rows = conn.execute(
            """
            SELECT lat, lon
              FROM raw_ais
             WHERE is_water = TRUE
             ORDER BY ts DESC
             LIMIT 600
            """
        ).fetchall()
        rng.shuffle(rows)
        chosen = rows[:TARGET_TRACKS]

        SHIP_NAMES = [
            ("ARGO V", "GR"), ("HELLAS HERALD", "GR"), ("THERMOPYLAE", "GR"),
            ("MAVROGENIS", "CY"), ("KALYMNOS STAR", "GR"), ("PIRAEUS DAWN", "GR"),
            ("CRETE EXPRESS", "GR"), ("RHODOS PRIDE", "GR"), ("MISTRAL TM", "TR"),
            ("AEGEAN SUN", "GR"), ("DELPHI VOYAGER", "GR"), ("LIMNOS BAY", "GR"),
            ("KASOS WAVE", "GR"), ("PINDOS V", "AL"),
        ]
        seeds = []
        for (lat, lon), (name, flag) in zip(chosen, SHIP_NAMES):
            # Greek MMSIs start with 23x or 24x; Cypriot 209; Turkish 271;
            # Albanian 201. Generate a syntactically valid MMSI per flag.
            prefix = {"GR": "237", "CY": "209", "TR": "271", "AL": "201"}.get(flag, "237")
            mmsi = prefix + str(rng.randint(100000, 999999))
            length_m = rng.choice([28, 35, 47, 62, 78, 95, 120, 165, 210])
            seeds.append((mmsi, name, flag, float(length_m), lat, lon, None))
        print(f"  no broadcasting AIS in snapshot; synthesised {len(seeds)} demo seeds")

    print(f"  seeding {len(seeds)} trajectories from broadcasting AIS rows")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    inserted = 0
    for s in seeds:
        mmsi, name, flag, length_m, lat0, lon0, _ = s
        # Random walk: heading drifts slightly per step, distance constant.
        heading = rng.uniform(0, 360)
        lat, lon = lat0, lon0
        for i in range(POINTS_PER_TRACK):
            ts = now - timedelta(hours=HOURS_BACK * (POINTS_PER_TRACK - i - 1) / POINTS_PER_TRACK)
            # Step forward along current heading.
            import math
            rad = math.radians(heading)
            lat += STEP_DEG * math.cos(rad) * rng.uniform(0.4, 1.0)
            lon += STEP_DEG * math.sin(rad) * rng.uniform(0.4, 1.0)
            heading += rng.uniform(-25, 25)  # drift
            event_id = f"synth-{mmsi}-{i:02d}-{uuid.uuid4().hex[:6]}"
            cache_key = f"{SOURCE_TAG}-{mmsi}"
            conn.execute(
                """
                INSERT INTO raw_ais (cache_key, event_id, mmsi, ts, lat, lon,
                                     vessel_name, flag, length_m,
                                     ais_status, is_water)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'broadcasting', TRUE)
                """,
                [cache_key, event_id, mmsi, ts, lat, lon, name, flag, length_m],
            )
            inserted += 1

    # Force a checkpoint so the .wal flushes — the snapshot tool depends
    # on this for clean copy operations.
    try:
        conn.execute("CHECKPOINT")
    except Exception:
        pass

    print(f"  inserted {inserted} synth AIS rows ({len(seeds)} tracks × {POINTS_PER_TRACK} points)")
    print(f"  source tag: {SOURCE_TAG!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
