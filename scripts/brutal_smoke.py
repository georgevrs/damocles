"""Brutal end-to-end smoke test of every Damocles backend endpoint.

Hits every read-side endpoint, every interactive endpoint, every edge
case the demo can trigger, plus error paths. Aim: surface any 5xx or
empty response that would embarrass us on stage.

No assertions — emits a single OK/FAIL line per probe and a summary.
The pre-flight script does the GREEN/RED check; this script is for
catching cracks the pre-flight doesn't.

Run:
    uv run python scripts/brutal_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BACKEND = os.environ.get("DAMOCLES_BACKEND", "http://127.0.0.1:8001")
DEMO_AOI = "aoi-17854afce5"   # North Heraklion Zone

PASS = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"

results: list[tuple[str, str, str, float]] = []


def probe(label: str, method: str, path: str, *,
          body: dict | None = None,
          allow_4xx: tuple[int, ...] = (),
          min_size: int = 0,
          require_keys: tuple[str, ...] = (),
          require_features: int = 0) -> dict | None:
    url = f"{BACKEND}{path}"
    headers = {"Accept": "application/json"}
    data = json.dumps(body).encode() if body else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
            elapsed = time.perf_counter() - t0
            status = r.status
            try:
                payload = json.loads(raw)
            except Exception:
                payload = None
    except urllib.error.HTTPError as e:
        elapsed = time.perf_counter() - t0
        status = e.code
        try:
            payload = json.loads(e.read())
        except Exception:
            payload = None
        if status in allow_4xx:
            results.append((PASS, label, f"HTTP {status} (allowed)", elapsed))
            return payload
        results.append((FAIL, label, f"HTTP {status}: {str(payload)[:120]}", elapsed))
        return None
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        results.append((FAIL, label, f"{type(exc).__name__}: {exc}", elapsed))
        return None

    # Size check
    if min_size and (not raw or len(raw) < min_size):
        results.append((FAIL, label, f"too small: {len(raw)} bytes", elapsed))
        return payload
    # Key check
    if require_keys and isinstance(payload, dict):
        missing = [k for k in require_keys if k not in payload]
        if missing:
            results.append((FAIL, label, f"missing keys: {missing}", elapsed))
            return payload
    # Features check
    if require_features and isinstance(payload, dict):
        feats = payload.get("features")
        if not isinstance(feats, list) or len(feats) < require_features:
            results.append((WARN, label, f"only {len(feats) if isinstance(feats, list) else 0} features (≥{require_features} expected)", elapsed))
            return payload
    results.append((PASS, label, f"HTTP {status} in {elapsed*1000:.0f}ms", elapsed))
    return payload


def section(title: str) -> None:
    print()
    print(f"== {title} ==")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"backend={BACKEND}")

    # 1. Basics
    section("basics")
    probe("/",            "GET", "/",       require_keys=("service", "version"))
    probe("/health",      "GET", "/health", require_keys=("status", "demo_mode", "llm", "neo4j"))
    probe("/openapi.json","GET", "/openapi.json", min_size=2000)

    # 2. Store
    section("store")
    probe("/api/store/stats", "GET", "/api/store/stats", min_size=20)

    # 3. AoI
    section("aoi")
    probe("/api/aoi (all)",  "GET", "/api/aoi?source=all", require_features=70)
    probe("/api/aoi (ai)",   "GET", "/api/aoi?source=ai",  require_features=70)
    probe("/api/aoi (user)", "GET", "/api/aoi?source=user", require_keys=("features",))
    canon = probe("/api/aoi/canonical/_list", "GET", "/api/aoi/canonical/_list", require_keys=("items",))
    canon_n = len((canon or {}).get("items", []))
    if canon_n < 6:
        results.append((FAIL, "canonical cache size", f"only {canon_n}/6 cached", 0))
    probe(f"/api/aoi/{DEMO_AOI}/dna",      "GET", f"/api/aoi/{DEMO_AOI}/dna",      require_keys=("nodes",))
    probe(f"/api/aoi/{DEMO_AOI}/explore",  "GET", f"/api/aoi/{DEMO_AOI}/explore",  require_keys=("aoi",))
    probe(f"/api/aoi/{DEMO_AOI}/brief",    "POST", f"/api/aoi/{DEMO_AOI}/brief",   require_keys=("sections", "id"))
    probe("/api/aoi/{nonexistent}/explore","GET", "/api/aoi/aoi-nonexistent/explore", allow_4xx=(404,))

    # 4. Briefs
    section("briefs")
    brief_id = None
    aois = probe("/api/aoi (re-fetch for brief id)", "GET", "/api/aoi?source=ai") or {}
    # The simpler path: refetch the canonical brief for DEMO_AOI to get its id
    canonical_brief = probe(f"/api/aoi/{DEMO_AOI}/brief (2nd hit, cache check)",
                            "POST", f"/api/aoi/{DEMO_AOI}/brief")
    if canonical_brief:
        brief_id = canonical_brief.get("id")
        sections_n = len(canonical_brief.get("sections", []))
        if sections_n < 4:
            results.append((WARN, "brief sections", f"only {sections_n} sections", 0))
    if brief_id:
        probe(f"/api/briefs/{brief_id}", "GET", f"/api/briefs/{brief_id}")
        # Every section should have a working citation chain
        sections_list = (canonical_brief or {}).get("sections", []) if canonical_brief else []
        broken = 0
        for sec in sections_list:
            sec_id = sec.get("id")
            if not sec_id:
                continue
            r = probe(f"  cite chain §{sec.get('section_type')}",
                      "GET", f"/api/briefs/{brief_id}/citation/{sec_id}",
                      require_keys=("source_nodes",))
            if r and len(r.get("source_nodes", [])) == 0:
                broken += 1
        if broken:
            results.append((WARN, "citation chains with empty nodes", f"{broken} sections", 0))
    probe("/api/briefs (no watch_id)", "GET", "/api/briefs", allow_4xx=(422,))

    # 5. Map / sensors
    section("map")
    probe("/api/map/vessels",         "GET", "/api/map/vessels?hours=336&limit=2000", require_features=100)
    probe("/api/map/trajectories",    "GET", "/api/map/trajectories?hours=72&min_points=5&max_vessels=200", require_features=1)
    probe("/api/map/flights",         "GET", "/api/map/flights?bbox=19.0,34.5,29.7,41.8")
    probe("/api/map/news_heatmap",    "GET", "/api/map/news_heatmap?hours=168&h3_resolution=5")

    # 6. External overlays
    section("external")
    probe("/api/external/earthquakes","GET", "/api/external/earthquakes?days=7&min_mag=3.5")
    probe("/api/external/disasters",  "GET", "/api/external/disasters")
    probe("/api/external/eonet",      "GET", "/api/external/eonet?days=14&status=open")

    # 7. Watches
    section("watches")
    tpl = probe("/api/watches/templates", "GET", "/api/watches/templates")
    if not isinstance(tpl, list) or len(tpl) < 3:
        results.append((WARN, "watch templates", f"only {len(tpl) if isinstance(tpl, list) else 0} templates", 0))

    # 8. Standing scan
    section("standing")
    probe("/api/standing/status", "GET", "/api/standing/status", require_keys=("scheduler_active", "history"))

    # 9. Audit
    section("audit")
    probe("/api/audit",        "GET", "/api/audit?hours_back=720&limit=200", require_keys=("entries", "verified"))
    probe("/api/audit/verify", "GET", "/api/audit/verify", require_keys=("verified", "chain_total"))

    # 10. W3 demo-only endpoints (round-trip)
    section("W3 demo endpoints")
    tamper = probe("/api/audit/_tamper", "POST", "/api/audit/_tamper", require_keys=("tampered", "first_bad_index"))
    if tamper:
        # Verify reflects the tamper
        v = probe("/api/audit/verify (after tamper)", "GET", "/api/audit/verify")
        if v and v.get("verified"):
            results.append((FAIL, "tamper not visible to verify", "verified=true after _tamper", 0))
    probe("/api/audit/_restore", "POST", "/api/audit/_restore", require_keys=("restored", "verified"))
    v2 = probe("/api/audit/verify (after restore)", "GET", "/api/audit/verify")
    if v2 and not v2.get("verified"):
        results.append((FAIL, "restore didn't recover", f"first_bad={v2.get('first_bad_index')}", 0))

    # LLM swap (round-trip)
    swap1 = probe("/api/system/llm/switch -> ollama", "POST", "/api/system/llm/switch",
                  body={"provider": "ollama"}, require_keys=("swapped", "current"))
    swap2 = probe("/api/system/llm/switch -> gemini", "POST", "/api/system/llm/switch",
                  body={"provider": "gemini"}, require_keys=("swapped", "current"))
    if swap2 and swap2.get("current") != "gemini":
        results.append((FAIL, "swap back didn't land", f"current={swap2.get('current')}", 0))

    probe("/api/system/llm/switch bogus", "POST", "/api/system/llm/switch",
          body={"provider": "bogus"}, allow_4xx=(422,))

    # 11. Negative paths — bad inputs
    section("negative paths")
    probe("bad bbox",         "GET", "/api/map/vessels?bbox=garbage&hours=24")  # parser falls back
    probe("missing AoI brief","POST","/api/aoi/aoi-nope/brief", allow_4xx=(404,))
    probe("citation 404",     "GET", f"/api/briefs/brief-nope/citation/sec-nope", allow_4xx=(404,))

    # ── summary
    print()
    pass_n = sum(1 for r in results if r[0] == PASS)
    warn_n = sum(1 for r in results if r[0] == WARN)
    fail_n = sum(1 for r in results if r[0] == FAIL)
    for status, label, detail, _ in results:
        print(f"{status} {label:55s} {detail}")
    print()
    print(f"  {pass_n} OK · {warn_n} WARN · {fail_n} FAIL")
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
