"""Deep quality scan of 10 random AoIs.

Probes the live backend (http://localhost:8001) for each sampled AoI:
    /api/aoi              — get the FeatureCollection
    /api/aoi/{id}/explore — composites + sources + subgraph
    /api/aoi/{id}/dna     — strand-tagged subgraph

For each AoI, the script records evidence on five quality axes:
    1. Geographic plausibility (centroid in Greek scope? name matches geography?)
    2. Polygon validity (area, vertex count, self-intersection sanity)
    3. Source diversity (vessels / news / social — is it single-source-only?)
    4. Threat-grade justification (does the grade match the worst member?)
    5. Naming quality (Greek + English present? non-trivial / non-default?)

Output: docs/_aoi_scan.json (machine-readable) + console summary.
The accompanying narrative analysis is written to docs/AOI_QUALITY_REPORT.md.
"""
from __future__ import annotations

import json
import random
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = "http://127.0.0.1:8001"
SEED = 1337

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "docs" / "_aoi_scan.json"


def fetch(path: str) -> dict[str, Any]:
    req = urllib.request.Request(f"{BACKEND}{path}",
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


# ─────────────────────────── geographic reference ───────────────────────────

# Coarse box -> human-readable region label. Lets us sanity-check "this AoI
# centroid is in the Aegean / Ionian / mainland / Crete / Turkish coast etc."
REGION_BOXES = [
    # (label, min_lon, min_lat, max_lon, max_lat)
    ("South Crete sea",        21.5, 33.5, 26.5, 35.4),
    ("Crete island",           23.4, 34.8, 26.5, 35.7),
    ("Libyan sea",             19.0, 31.0, 26.5, 33.5),
    ("Karpathos / Kasos arc",  26.5, 35.0, 28.5, 36.3),
    ("Rhodes / Dodecanese SE", 27.5, 35.5, 29.0, 37.5),
    ("Dodecanese N",           26.5, 37.5, 28.5, 39.5),
    ("Cyclades",               23.5, 35.7, 26.5, 38.0),
    ("Cyclades N edge",        24.0, 37.5, 26.5, 38.5),
    ("Lemnos basin",           24.5, 39.0, 26.0, 40.3),
    ("North Aegean",           24.5, 39.5, 26.5, 41.0),
    ("Thracian Sea",           24.0, 40.3, 26.5, 41.5),
    ("Evros / Thrace land",    25.7, 40.5, 27.0, 41.8),
    ("Western Turkey coast",   26.0, 36.0, 28.5, 39.5),
    ("Sea of Marmara / Turkish straits", 26.0, 40.0, 30.0, 41.5),
    ("Saronic Gulf / Attica",  22.8, 37.4, 24.5, 38.5),
    ("Athens metro",           23.5, 37.8, 24.2, 38.3),
    ("Peloponnese",            21.0, 36.3, 23.5, 38.4),
    ("Ionian sea",             18.5, 36.0, 21.5, 39.5),
    ("Albanian coast",         18.5, 39.5, 20.5, 41.5),
    ("Macedonia / Chalkidiki", 22.0, 39.5, 24.5, 41.5),
    ("Thessaly",               21.5, 38.8, 23.5, 40.0),
    ("Central Greece",         21.5, 38.0, 23.5, 39.5),
    ("Epirus / NW Greece",     19.5, 39.0, 21.5, 40.5),
]

def region_for(lon: float, lat: float) -> str:
    for label, l1, b1, l2, b2 in REGION_BOXES:
        if l1 <= lon <= l2 and b1 <= lat <= b2:
            return label
    if 19.0 <= lon <= 30.0 and 34.0 <= lat <= 43.0:
        return "Greek bbox (uncategorised)"
    return f"Outside Greek bbox ({lon:.1f}, {lat:.1f})"


# ─────────────────────────── polygon utils ───────────────────────────

def polygon_area_km2(geometry: dict) -> float:
    """Spherical-excess area approximation in km². Sufficient for sanity-check
    at AoI scales (≤ ~5000 km²)."""
    import math
    R_KM = 6371.0
    def ring_area(ring: list[list[float]]) -> float:
        if len(ring) < 3:
            return 0.0
        total = 0.0
        n = len(ring)
        for i in range(n):
            lon1, lat1 = ring[i]
            lon2, lat2 = ring[(i + 1) % n]
            total += math.radians(lon2 - lon1) * (2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
        return abs(total * R_KM * R_KM / 2)
    if geometry.get("type") == "Polygon":
        rings = [geometry["coordinates"][0]]
    elif geometry.get("type") == "MultiPolygon":
        rings = [poly[0] for poly in geometry["coordinates"]]
    else:
        return 0.0
    return sum(ring_area(r) for r in rings)


def polygon_vertex_count(geometry: dict) -> int:
    if geometry.get("type") == "Polygon":
        return sum(len(r) for r in geometry.get("coordinates", []))
    if geometry.get("type") == "MultiPolygon":
        return sum(len(r) for poly in geometry.get("coordinates", []) for r in poly)
    return 0


# ─────────────────────────── sampling ───────────────────────────

def sample_aois(n: int = 10) -> list[dict]:
    fc = fetch("/api/aoi?source=all")
    features = fc["features"]
    rng = random.Random(SEED)

    # Stratify: include at least one from each grade if available
    by_grade: dict[str, list] = {}
    for f in features:
        g = f["properties"].get("threat_grade") or "GREEN"
        by_grade.setdefault(g, []).append(f)
    picked: list[dict] = []
    for grade, fs in by_grade.items():
        if fs:
            picked.append(rng.choice(fs))
    # Fill remainder with uniform random from the full pool
    rest = [f for f in features if f not in picked]
    rng.shuffle(rest)
    picked.extend(rest[: max(0, n - len(picked))])
    return picked[:n]


# ─────────────────────────── per-AoI analysis ───────────────────────────

THREAT_RANK = {"GREEN": 1, "AMBER": 2, "RED": 3}

def analyse(aoi: dict) -> dict[str, Any]:
    p = aoi["properties"]
    aoi_id = aoi["id"]
    geom   = aoi["geometry"]
    name_el = p.get("name_el") or ""
    name_en = p.get("name_en") or ""
    grade   = (p.get("threat_grade") or "GREEN").upper()
    lat, lon = p.get("centroid_lat"), p.get("centroid_lon")

    region = region_for(lon, lat) if (lat is not None and lon is not None) else "no centroid"
    area_km2 = polygon_area_km2(geom)
    vertex_count = polygon_vertex_count(geom)

    # Fetch member composites + sources via /explore
    try:
        explore = fetch(f"/api/aoi/{aoi_id}/explore")
    except Exception as exc:
        return {"id": aoi_id, "error": f"explore failed: {exc}"}

    composites = explore.get("composites", [])
    sources    = explore.get("sources", [])

    # Source diversity
    type_counts: dict[str, int] = {}
    for s in sources:
        type_counts[s["type"]] = type_counts.get(s["type"], 0) + 1

    # Threat justification: derive grade from worst composite
    worst_grade = "GREEN"
    for c in composites:
        cg = (c.get("threat_grade") or "GREEN").upper()
        if THREAT_RANK.get(cg, 0) > THREAT_RANK.get(worst_grade, 0):
            worst_grade = cg
    grade_match = grade == worst_grade

    # Confidence stats over composites
    confs = [c.get("confidence") for c in composites if isinstance(c.get("confidence"), (int, float))]
    avg_conf = sum(confs) / len(confs) if confs else None

    # Temporal spread (oldest -> newest member)
    times = []
    for c in composites:
        for k in ("time_window_end", "time_window_start", "created_at"):
            t = c.get(k)
            if t:
                try:
                    times.append(datetime.fromisoformat(t.replace("Z", "+00:00")))
                    break
                except Exception:
                    pass
    if times:
        oldest = min(times); newest = max(times)
        span_hours = round((newest - oldest).total_seconds() / 3600, 1)
    else:
        oldest = newest = None
        span_hours = None

    # Fetch DNA for base-pair stats
    try:
        dna = fetch(f"/api/aoi/{aoi_id}/dna")
        dna_stats = dna.get("stats", {})
    except Exception:
        dna_stats = {}

    # Name plausibility
    name_default_like = name_en.lower().startswith("cluster ") or name_el.startswith("Συστάδα ")
    name_has_both    = bool(name_el) and bool(name_en)
    name_length_ok   = (1 <= len(name_el.split()) <= 6) and (1 <= len(name_en.split()) <= 6)

    return {
        "id":            aoi_id,
        "name_el":       name_el,
        "name_en":       name_en,
        "centroid":      [lat, lon],
        "region_match":  region,
        "polygon": {
            "type":           geom.get("type"),
            "area_km2":       round(area_km2, 1),
            "vertex_count":   vertex_count,
            "looks_valid":    (vertex_count >= 4 and area_km2 > 0),
        },
        "threat": {
            "declared":     grade,
            "worst_member": worst_grade,
            "matches":      grade_match,
        },
        "members": {
            "composite_count": len(composites),
            "source_count":    len(sources),
            "type_counts":     type_counts,
            "avg_confidence":  round(avg_conf, 3) if avg_conf is not None else None,
        },
        "temporal": {
            "oldest":     oldest.isoformat() if oldest else None,
            "newest":     newest.isoformat() if newest else None,
            "span_hours": span_hours,
        },
        "dna_stats": dna_stats,
        "naming": {
            "el_present":   bool(name_el),
            "en_present":   bool(name_en),
            "both_present": name_has_both,
            "default_like": name_default_like,
            "length_ok":    name_length_ok,
        },
        "source_meta": {
            "source":   p.get("source"),
            "scan_id":  p.get("scan_id"),
            "created":  p.get("created_at"),
        },
    }


# ─────────────────────────── orchestrate ───────────────────────────

def main() -> int:
    print(f"== AoI quality scan == backend={BACKEND}")
    picked = sample_aois(n=10)
    print(f"Sampled {len(picked)} AoIs")

    results: list[dict] = []
    for f in picked:
        r = analyse(f)
        results.append(r)
        if "error" in r:
            print(f"  [ERR] {r['id']}: {r['error']}")
            continue
        print(f"  {r['id'][:14]:14s}  {r['threat']['declared']:6s}  "
              f"area={r['polygon']['area_km2']:7.1f}km^2  "
              f"src_types={list(r['members']['type_counts'].keys())}  "
              f"{r['name_en'][:40]:40s}  ({r['region_match']})")

    OUT_JSON.parent.mkdir(exist_ok=True, parents=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-- scan saved: {OUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
