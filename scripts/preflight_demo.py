"""W4-T4 — demo machine pre-flight check.

Run within 60 seconds of stepping on stage. Verifies the demo box is
in the exact state ``docs/demo-script.md §"State the demo machine must
be in"`` requires.

  - Backend reachable on :8001 and reports DEMO_MODE=true.
  - DuckDB pointed at ``damocles.duckdb`` (the demo file must already
    have been copied over from ``.demo`` snapshot per DEMO_RESTORE.md).
  - ≥6 RED AoIs visible.
  - ≥6 canonical briefs cached.
  - Frontend served on :5173.
  - Audit chain verifies green.
  - The W2-T1 demo target (``aoi-17854afce5``) exists and has a brief.

Exit code 0 = ready for pitch.
Exit code 1 = STOP. Investigate before running setup the audience can see.

Run:
    uv run python scripts/preflight_demo.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND  = os.environ.get("DAMOCLES_BACKEND", "http://127.0.0.1:8001")
FRONTEND = os.environ.get("DAMOCLES_FRONTEND", "http://127.0.0.1:5173")
DEMO_AOI = "aoi-17854afce5"


def _fetch(method: str, path: str, base: str = BACKEND,
           accept_json: bool = True) -> tuple[int, dict | None]:
    try:
        headers = {"Accept": "application/json"} if accept_json else {}
        req = urllib.request.Request(f"{base}{path}", method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            if not accept_json:
                return r.status, None
            return r.status, json.loads(body)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read()) if accept_json else None
        except Exception:
            body = None
        return e.code, body
    except Exception:
        return 0, None


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = " OK" if ok else "FAIL"
    print(f"  [{mark}] {label:38s} {detail}")
    return ok


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"== demo pre-flight ==  backend={BACKEND}  frontend={FRONTEND}")
    print(f"   time={time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    failures = 0

    # 1. Backend up
    t0 = time.perf_counter()
    code, health = _fetch("GET", "/health")
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    backend_up = code == 200 and isinstance(health, dict)
    if not _check("backend reachable on :8001", backend_up, f"{code} in {elapsed_ms}ms"):
        failures += 1
        # Without backend nothing else works — bail early.
        return 1

    # 2. DEMO_MODE is on (so /_tamper, /_restore, /llm/switch are reachable)
    demo_on = bool((health or {}).get("demo_mode"))
    failures += 0 if _check("DEMO_MODE is on", demo_on, f"demo_mode={demo_on}") else 1

    # 3. Frontend reachable — Vite refuses Accept: application/json on the
    # HTML index (it 404s), so request without that header.
    code_fe, _ = _fetch("GET", "/", base=FRONTEND, accept_json=False)
    failures += 0 if _check("frontend reachable on :5173", code_fe == 200, f"HTTP {code_fe}") else 1

    # 4. Canonical brief cache primed (≥6 entries — one per RED)
    code, canon = _fetch("GET", "/api/aoi/canonical/_list")
    canon_items = (canon or {}).get("items", []) if isinstance(canon, dict) else (canon or [])
    canon_n = len(canon_items)
    failures += 0 if _check("canonical briefs cached", canon_n >= 6, f"{canon_n} entries") else 1

    # 5. Demo target AoI exists + has a canonical brief
    target_has_brief = any(
        (c.get("aoi_id") == DEMO_AOI) for c in canon_items
    )
    failures += 0 if _check(f"demo target {DEMO_AOI} cached", target_has_brief,
                            "North Heraklion Zone") else 1

    # 6. At least 6 RED AoIs visible
    code, aois = _fetch("GET", "/api/aoi?source=ai")
    red_n = 0
    aoi_n = 0
    if isinstance(aois, dict) and "features" in aois:
        aoi_n = len(aois["features"])
        red_n = sum(
            1 for f in aois["features"]
            if (f.get("properties") or {}).get("threat_grade") == "RED"
        )
    failures += 0 if _check("≥6 RED AoIs visible", red_n >= 6,
                            f"{red_n} RED of {aoi_n} AoIs") else 1

    # 7. Audit chain verifies green
    code, verdict = _fetch("GET", "/api/audit/verify")
    audit_ok = bool((verdict or {}).get("verified"))
    chain_n = (verdict or {}).get("chain_total", 0)
    failures += 0 if _check("audit chain verifies green", audit_ok,
                            f"verified, {chain_n} entries") else 1

    # 8. Scan-cinema WS endpoint responds (HEAD-check by trying upgrade fails
    #    cleanly, so we check the AoI count instead — same data source).
    failures += 0 if _check("scan-cinema source has ≥80 AoIs", aoi_n >= 80,
                            f"{aoi_n} AoIs streamable") else 1

    # 9. DuckDB file isn't a leftover backup
    duckdb_path = Path("data/damocles.duckdb")
    duckdb_ok = duckdb_path.exists() and duckdb_path.stat().st_size > 0
    size_mb = duckdb_path.stat().st_size / (1024 * 1024) if duckdb_ok else 0
    failures += 0 if _check("data/damocles.duckdb present", duckdb_ok,
                            f"{size_mb:.1f} MB") else 1

    print()
    if failures == 0:
        print(f"  ALL GREEN — demo machine is ready for stage")
        print(f"  next step: open {FRONTEND} on the projection screen")
        return 0
    print(f"  {failures} CHECK(S) FAILED — DO NOT proceed to demo without fixing")
    print(f"  most common fixes:")
    print(f"    - restore snapshot: see docs/DEMO_RESTORE.md")
    print(f"    - pre-cache briefs: uv run python scripts/pre_cache_briefs.py")
    print(f"    - boot frontend:    cd frontend && npm run dev -- --host 127.0.0.1")
    return 1


if __name__ == "__main__":
    sys.exit(main())
