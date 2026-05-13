"""Build a real water-surface polygon for Greece + neighbour waters.

The sea geojsons shipped at `data/geojson/{aegean,ionian,eastern_med,greek_eez}.geojson`
are bbox rectangles, not actual sea surfaces — they classify Phthiotis
mountains as "water." This script generates a precise water polygon by
**subtracting the Greek land polygon** (from `frontend/src/lib/geoGreece.ts`,
a Douglas-Peucker-simplified public-domain coastline) from a broader sea
bbox covering the Eastern Mediterranean.

Writes the result to `data/geojson/_water_surface.geojson` for the runtime
water-mask to load. Idempotent — safe to re-run.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO_TS = ROOT / "frontend" / "src" / "lib" / "geoGreece.ts"
OUT = ROOT / "data" / "geojson" / "_water_surface.geojson"

# Eastern Mediterranean working bbox — generous enough for the Greek EEZ
# plus Turkish coast, Ionian, North Aegean. Subtracting Greek land from
# this gives us "water surfaces near Greece" — which is what the AoI
# pipeline cares about.
SEA_BBOX = (19.0, 30.0, 30.0, 42.0)   # min_lon, min_lat, max_lon, max_lat

# The GREECE_GEOJSON polygon covers only Greek sovereign territory, so without
# explicit neighbour-land subtraction the water mask would classify inland
# Turkey, Bulgaria, Albania, and North Macedonia as "sea" (since they're
# within the working bbox but not subtracted). These approximate bounding
# rectangles are intentionally conservative — they extend into the sea
# slightly so coastal water within ~3-5 km of the foreign coast is excluded
# too (cleaner than computing real coastlines for every neighbour).
# Each tuple: (min_lon, min_lat, max_lon, max_lat).
NEIGHBOUR_LAND_BBOXES = (
    # Turkey — split into two rectangles so the Marmara Sea (lat 40.4-41.0,
    # lon 27.5-29.5) and the Aegean corridor east of Lesvos/Chios/Samos
    # remain water:
    #   Thrace (north of Marmara): wide rectangle above lat 41.0
    (26.6, 41.0, 30.0, 42.0),
    #   Anatolia (east of Aegean): starts at lon 27.5 so Greek islands +
    #   the eastern Aegean stay water. Top capped at lat 40.4 to preserve
    #   the Marmara Sea (which sits at lat 40.4-41.0).
    (27.5, 36.4, 30.0, 40.4),
    # Bulgaria — south of Danube, east of FYROM.
    (22.4, 41.7, 28.5, 42.0),
    # Albania — west coast pulled in so we don't eat the Adriatic.
    (19.3, 39.6, 20.7, 42.0),
    # North Macedonia.
    (20.5, 40.85, 23.0, 42.0),
    # North African coast (Libya / Egypt) at the bottom of the bbox.
    (19.0, 30.0, 30.0, 33.0),
    # Cyprus — separate landmass.
    (32.2, 34.5, 34.6, 35.7),
)


def extract_greece_geojson() -> dict:
    """Pull the embedded JSON out of the TS file."""
    text = GEO_TS.read_text(encoding="utf-8")
    m = re.search(r"GREECE_GEOJSON\s*=\s*\(({.*?})\)\s*as", text, re.S)
    if not m:
        sys.exit(f"could not find GREECE_GEOJSON literal in {GEO_TS}")
    return json.loads(m.group(1))


def main() -> int:
    from shapely.geometry import box, mapping, shape
    from shapely.ops import unary_union

    print(f"loading land polygon from {GEO_TS.relative_to(ROOT)}")
    land_geojson = extract_greece_geojson()
    land = shape(land_geojson)
    if not land.is_valid:
        land = land.buffer(0)
    print(f"  land: {land.geom_type}, {sum(1 for _ in land.geoms) if hasattr(land, 'geoms') else 1} parts, bounds={land.bounds}")

    sea_bbox = box(*SEA_BBOX)
    print(f"sea bbox: {SEA_BBOX}")

    # Subtract land from sea. Allow a 0.005° (~500m) tolerance so coastal
    # noise (GPS jitter on real AIS broadcasts) still counts as water.
    LAND_DILATE_DEG = -0.005   # negative buffer = shrink land = expand water
    land_for_subtract = land.buffer(LAND_DILATE_DEG)
    if not land_for_subtract.is_valid:
        land_for_subtract = land_for_subtract.buffer(0)
    print(f"  land (eroded {LAND_DILATE_DEG}° for coastal tolerance): bounds={land_for_subtract.bounds}")

    # Subtract neighbour-land rectangles too, otherwise Turkish/Bulgarian/etc.
    # inland would be classified as water (Greek polygon doesn't cover them).
    neighbour_geoms = [box(*r) for r in NEIGHBOUR_LAND_BBOXES]
    all_land = unary_union([land_for_subtract] + neighbour_geoms)
    if not all_land.is_valid:
        all_land = all_land.buffer(0)
    print(f"  + {len(neighbour_geoms)} neighbour-land rectangles "
          f"(Turkey, Bulgaria, Albania, FYROM, N. Africa, Cyprus)")

    water = sea_bbox.difference(all_land)
    if not water.is_valid:
        water = water.buffer(0)
    print(f"  water: {water.geom_type}, area={water.area:.2f} deg², bounds={water.bounds}")

    # Sanity check known points
    from shapely.geometry import Point
    checks = [
        ("Central Aegean (water)",     25.5, 37.5, True),
        ("Phthiotis mountains (land)", 22.7, 38.6, False),
        ("Athens metro (land)",        23.7, 38.0, False),
        ("Marmara Sea (water)",        28.0, 40.7, True),
        ("Crete inland (land)",        25.0, 35.2, False),
        ("Crete south sea (water)",    24.5, 34.5, True),
        # New checks for the neighbour-land fix
        ("Kirklareli, Turkey (land)",  27.2, 41.6, False),
        ("Inland Bulgaria (land)",     26.0, 42.0, False),
        ("Northern Evros river (land 41.7N)", 26.2, 41.7, False),
        ("Aegean E of Lesvos (water)", 26.6, 39.0, True),
        ("Limnos waters (water)",      25.2, 39.8, True),
    ]
    print("sanity checks:")
    for label, lon, lat, expected in checks:
        actual = water.contains(Point(lon, lat))
        ok = "OK " if actual == expected else "FAIL"
        print(f"  [{ok}] {label}: expected={expected} actual={actual}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    feature = {
        "type":     "Feature",
        "properties": {
            "name":         "Damocles water surface",
            "description":  "Sea bbox minus Greek land. Used for SAR false-positive filtering.",
            "generated_by": "scripts/build_water_mask.py",
        },
        "geometry": mapping(water),
    }
    fc = {"type": "FeatureCollection", "features": [feature]}
    OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size//1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
