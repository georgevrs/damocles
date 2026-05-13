"""Pre-cache canonical briefs for all RED AoIs in the demo snapshot.

Why: the 4-agent live pipeline takes 12-15s cold. On stage that's a
lifetime. This script generates each brief once, persists it via the
``aoi_canonical_brief`` table, and the next ``POST /api/aoi/{id}/brief``
serves it back in <50ms.

Run:
    # Backend must be running (it owns the DuckDB lock).
    NEO4J_PASSWORD=damocles2026 uv run python scripts/pre_cache_briefs.py

Idempotent. Each AoI's brief is regenerated and overwritten — change
``--include-amber`` to also cache AMBER, ``--only`` to limit to specific IDs.

Outputs a verification dump at ``docs/_canonical_briefs.json`` so we can
review the BLUF wording before pitch day (and prompt-tweak if needed).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BACKEND = os.environ.get("DAMOCLES_BACKEND", "http://127.0.0.1:8001")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
log = logging.getLogger("pre_cache")


def fetch_json(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        f"{BACKEND}{path}", method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        data=data,
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-amber", action="store_true",
                    help="Cache AMBER AoIs too (default: RED only)")
    ap.add_argument("--only", help="Comma-separated list of aoi_ids to limit to")
    ap.add_argument("--clear", action="store_true",
                    help="Clear all existing canonical briefs first")
    args = ap.parse_args()

    log.info("backend: %s", BACKEND)

    if args.clear:
        existing = fetch_json("GET", "/api/aoi/canonical/_list").get("items", [])
        for it in existing:
            try:
                urllib.request.urlopen(urllib.request.Request(
                    f"{BACKEND}/api/aoi/{it['aoi_id']}/brief/canonical", method="DELETE"
                )).read()
            except urllib.error.HTTPError as e:
                if e.code != 204:
                    log.warning("clear failed for %s: %s", it["aoi_id"], e)
        log.info("cleared %d existing canonical briefs", len(existing))

    fc = fetch_json("GET", "/api/aoi?source=ai")
    features = fc.get("features", [])
    log.info("total AI AoIs: %d", len(features))

    wanted_grades = {"RED"} | ({"AMBER"} if args.include_amber else set())
    targets = [
        f for f in features
        if (f["properties"].get("threat_grade") in wanted_grades)
    ]
    if args.only:
        keep = {x.strip() for x in args.only.split(",")}
        targets = [t for t in targets if t["id"] in keep]
    log.info("targets: %d (grades %s)", len(targets), wanted_grades)

    dump: list[dict] = []
    for i, f in enumerate(targets, 1):
        aoi_id = f["id"]
        p = f["properties"]
        log.info("[%d/%d] %s — %s  grade=%s",
                 i, len(targets), aoi_id, p.get("name_en"), p.get("threat_grade"))
        t0 = time.time()
        try:
            result = fetch_json("POST", f"/api/aoi/{aoi_id}/brief/canonical",
                                body={"notes": "auto-cached by pre_cache_briefs.py"})
            elapsed = time.time() - t0
            log.info("    OK in %.1fs (%d sections)", elapsed, result.get("sections", 0))
            # Re-fetch the brief to capture for the dump
            brief = fetch_json("POST", f"/api/aoi/{aoi_id}/brief")  # cache hit
            bluf_text = ""
            for s in brief.get("sections", []):
                if s.get("section_type") == "BLUF":
                    bluf_text = s.get("text", "")
                    break
            dump.append({
                "aoi_id":   aoi_id,
                "name_el":  p.get("name_el"),
                "name_en":  p.get("name_en"),
                "grade":    p.get("threat_grade"),
                "bluf":     bluf_text,
                "sections": len(brief.get("sections", [])),
                "generation_seconds": round(elapsed, 1),
            })
        except urllib.error.HTTPError as e:
            log.error("    FAIL HTTP %d: %s", e.code, e.read()[:200])
            dump.append({"aoi_id": aoi_id, "error": f"HTTP {e.code}"})
        except Exception as e:
            log.error("    FAIL %s: %s", type(e).__name__, e)
            dump.append({"aoi_id": aoi_id, "error": f"{type(e).__name__}: {e}"})

    out_path = ROOT / "docs" / "_canonical_briefs.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("wrote %s (%d briefs)", out_path.relative_to(ROOT), len(dump))

    # Final inventory
    inv = fetch_json("GET", "/api/aoi/canonical/_list")
    log.info("canonical cache now has %d briefs", len(inv.get("items", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
