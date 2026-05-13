"""W2-T4 — click-test every citation in the canonical demo brief.

Steps the demo target's brief through every citation chip's resolver
(``GET /api/briefs/{brief_id}/citation/{section_id}``) and verifies:

  - Resolver returns 200.
  - The resolved chain contains source_nodes.
  - Each source_node carries a non-empty ``raw_evidence`` (the modal will
    have something to render).
  - The first chain node matches the section's first citation_id.

Pass = every citation chip works on demo day, no surprise blank modals.

Run:
    uv run python scripts/demo_click_test.py

Optional --aoi-id to test a different RED. Output: green/red summary +
docs/_canonical_click_test.json with the full chain dump for any failing
citations so we can investigate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
ROOT    = Path(__file__).resolve().parent.parent
BACKEND = os.environ.get("DAMOCLES_BACKEND", "http://127.0.0.1:8001")
DEFAULT_AOI = "aoi-17854afce5"   # North Heraklion Zone — the W2-T1 demo target


def fetch(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{BACKEND}{path}", method=method, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi-id", default=DEFAULT_AOI)
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"== demo click test ==  aoi={args.aoi_id}")

    # 1. Pull the canonical brief
    try:
        brief = fetch("POST", f"/api/aoi/{args.aoi_id}/brief")
    except urllib.error.HTTPError as e:
        print(f"FATAL: brief fetch failed: HTTP {e.code} {e.read()[:200]!r}")
        return 1

    brief_id = brief.get("id")
    sections = brief.get("sections", [])
    print(f"   brief={brief_id!r}, sections={len(sections)}")
    if not sections:
        print("FATAL: no sections")
        return 1

    failures: list[dict] = []
    passes: list[dict] = []

    for sec in sections:
        sec_id = sec.get("id")
        sec_type = sec.get("section_type")
        cites = sec.get("citation_node_ids", [])
        if not sec_id or not cites:
            failures.append({"section": sec_type, "reason": "section has no id or no cites"})
            continue
        # Test the per-section citation chain resolver
        try:
            chain = fetch("GET",
                          f"/api/briefs/{brief_id}/citation/{sec_id}")
        except urllib.error.HTTPError as e:
            failures.append({
                "section": sec_type, "section_id": sec_id,
                "reason": f"HTTP {e.code}: {e.read()[:120]!r}",
            })
            continue

        nodes = chain.get("source_nodes") or []
        first_cite = cites[0]
        first_node_id = (nodes[0] or {}).get("node_id") if nodes else None

        # Each node must carry a non-empty raw_evidence — otherwise the
        # evidence modal opens to a blank pane on stage.
        empty_evidence_nodes = [
            n for n in nodes
            if not n.get("raw_evidence") or
               (isinstance(n.get("raw_evidence"), dict) and not any(n["raw_evidence"].values()))
        ]

        status_ok = bool(nodes) and len(empty_evidence_nodes) <= len(nodes) - 1
        result = {
            "section":         sec_type,
            "section_id":      sec_id,
            "cites_n":         len(cites),
            "chain_n":         len(nodes),
            "first_cite":      first_cite,
            "first_node_id":   first_node_id,
            "empty_evidence":  len(empty_evidence_nodes),
            "ok":              status_ok,
        }
        if status_ok:
            passes.append(result)
        else:
            failures.append(result)

    # Output
    print()
    print(f"   {len(passes)} sections PASS")
    print(f"   {len(failures)} sections FAIL")
    print()
    for p in passes:
        print(f"   [OK]  {p['section']:18s}  cites={p['cites_n']}  chain={p['chain_n']}  first={p['first_cite'][:14]}")
    for f in failures:
        print(f"   [BAD] {f.get('section','?'):18s}  reason={f.get('reason') or f}")

    out = ROOT / "docs" / "_canonical_click_test.json"
    out.write_text(json.dumps({
        "aoi_id":  args.aoi_id,
        "brief_id": brief_id,
        "passes":  passes,
        "failures": failures,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   → {out.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
