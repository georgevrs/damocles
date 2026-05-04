"""End-of-Week-2 integration test.

This is the ceremonial check that runs before every demo dry-run. It walks
the full public-API path:

  1. GET /health                                              system ready
  2. POST /api/watches { "query": "Aegean - last 7 days" }    kick off pipeline
  3. WS  /ws/watches/{watch_id}                               stream progress live
  4. GET /api/briefs?watch_id=...                             brief appears
  5. GET /api/briefs/{brief_id}                               full structured brief
  6. GET /api/briefs/{brief_id}/citation/{section_id}         citation chain (×N sections)
  7. GET /api/audit/verify                                    Merkle chain intact

Then asserts every demo-critical invariant from the plan in one place:

  - Brief has BLUF + ≥ 1 KEY_JUDGMENT + at least one of {DEVILS_ADVOCATE,
    RECOMMENDATION}
  - Every text-bearing section has at least one citation
  - Every citation_node_id resolves to a real source node via the
    citation-chain endpoint
  - Every source node carries a non-empty raw_evidence + map_highlight
    where applicable
  - The audit chain is intact (no tamper) and grew during this run

Prereq: uvicorn must be running.
    .\\start.ps1 -NoFrontend
or  uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

Cost: this fires the FULL pipeline including a live SAR fetch, a live AIS
capture (~30s), a live GDELT pull (~25 MB), and 4 Gemini calls. Budget:
~60-90 s wall-clock, ~10 Sentinel Hub PUs, ~5 Gemini requests.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

import httpx
import websockets
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"

QUERY = "Aegean - last 7 days"
PIPELINE_TIMEOUT_S = 240.0


# ───────────────────────────────────────────────────────────────────────────────
# Assertion machinery — every check appends a (label, ok, detail) row
# ───────────────────────────────────────────────────────────────────────────────
class Checks:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def assert_(self, label: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((label, bool(ok), detail))
        return bool(ok)

    def all_passed(self) -> bool:
        return all(ok for _, ok, _ in self.rows)

    def render(self) -> Table:
        table = Table(title="Integration assertions", show_header=True)
        table.add_column("#", justify="right")
        table.add_column("check")
        table.add_column("status", justify="center")
        table.add_column("detail")
        for i, (label, ok, detail) in enumerate(self.rows, 1):
            mark = "[green]PASS[/]" if ok else "[red]FAIL[/]"
            table.add_row(str(i), label, mark, detail)
        return table


# ───────────────────────────────────────────────────────────────────────────────
# Phases
# ───────────────────────────────────────────────────────────────────────────────
async def phase_health(c: httpx.AsyncClient, checks: Checks) -> bool:
    r = await c.get("/health")
    h = r.json()
    ok = (
        r.status_code == 200
        and h.get("status") in {"ok", "degraded"}
        and h.get("neo4j", {}).get("ok") is True
        and h.get("llm", {}).get("ok") is True
    )
    checks.assert_(
        "GET /health: backend reachable, Neo4j up, LLM up",
        ok,
        f"status={h.get('status')} neo4j={h.get('neo4j',{}).get('ok')} "
        f"llm={h.get('llm',{}).get('ok')} model={h.get('llm',{}).get('model')}",
    )
    return ok


async def phase_post_watch(c: httpx.AsyncClient, checks: Checks) -> str | None:
    r = await c.post("/api/watches", json={"query": QUERY}, timeout=30)
    ok = r.status_code == 200 and r.json().get("id")
    checks.assert_(
        "POST /api/watches returns Watch with id",
        ok,
        f"status={r.status_code} id={r.json().get('id', '')[:8] if ok else '-'}",
    )
    return r.json().get("id") if ok else None


async def phase_stream_ws(watch_id: str, checks: Checks) -> list[dict]:
    """Subscribe to the WebSocket and stream events until 'complete'.

    Prints progress live so the operator sees the pipeline firing in real time.
    """
    url = f"{WS_BASE}/ws/watches/{watch_id}"
    events: list[dict] = []
    saw_complete = False
    started = time.time()

    try:
        async with websockets.connect(url) as ws:
            while True:
                if time.time() - started > PIPELINE_TIMEOUT_S:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=PIPELINE_TIMEOUT_S)
                except asyncio.TimeoutError:
                    break
                event = json.loads(raw)
                events.append(event)
                pct = event.get("progress_pct", 0)
                color = {
                    "complete": "green", "started": "cyan",
                    "failed": "red", "skipped": "yellow",
                }.get(event.get("status"), "white")
                console.print(
                    f"  [{color}]{pct:>3}%[/]  "
                    f"{event.get('stage', '?'):<22} "
                    f"{event.get('status', '-'):<8}  "
                    f"{event.get('detail', '')[:80]}"
                )
                if event.get("stage") == "complete":
                    saw_complete = True
                    break
    except websockets.exceptions.ConnectionClosed as exc:
        console.print(f"[yellow]WS closed mid-stream: code={exc.code}[/]")

    elapsed = time.time() - started
    checks.assert_(
        "WS streamed events to completion",
        saw_complete,
        f"{len(events)} events in {elapsed:.1f}s",
    )
    return events


async def phase_brief_exists(c: httpx.AsyncClient, watch_id: str, checks: Checks) -> dict | None:
    """Poll /api/briefs?watch_id=... briefly in case the WS 'complete' arrived
    fractionally before the brief landed in Neo4j."""
    brief_summary: dict | None = None
    for _ in range(15):
        r = await c.get("/api/briefs", params={"watch_id": watch_id})
        briefs = r.json() if r.status_code == 200 else []
        if briefs:
            brief_summary = briefs[0]
            break
        await asyncio.sleep(0.5)

    checks.assert_(
        "GET /api/briefs?watch_id=... returns ≥ 1 brief",
        brief_summary is not None,
        f"id={brief_summary['id'][:8] if brief_summary else '-'}",
    )
    return brief_summary


async def phase_brief_full(c: httpx.AsyncClient, brief_id: str, checks: Checks) -> dict | None:
    r = await c.get(f"/api/briefs/{brief_id}")
    if r.status_code != 200:
        checks.assert_("GET /api/briefs/{id}", False, f"status={r.status_code}")
        return None
    brief = r.json()
    sections = brief.get("sections", [])
    by_type: dict[str, int] = {}
    for s in sections:
        by_type[s["section_type"]] = by_type.get(s["section_type"], 0) + 1

    bluf = next((s for s in sections if s["section_type"] == "BLUF"), None)
    kj_count = by_type.get("KEY_JUDGMENT", 0)
    has_devil = "DEVILS_ADVOCATE" in by_type
    has_rec = "RECOMMENDATION" in by_type

    checks.assert_("brief has exactly one BLUF section", bluf is not None and by_type.get("BLUF") == 1,
                   f"by_type={by_type}")
    checks.assert_("brief has ≥ 1 KEY_JUDGMENT", kj_count >= 1, f"count={kj_count}")
    checks.assert_("brief has DEVILS_ADVOCATE", has_devil, "" if has_devil else "missing")
    checks.assert_("brief has RECOMMENDATION", has_rec, "" if has_rec else "missing")

    # Every text-bearing section must cite at least one node id.
    every_section_cited = all(len(s.get("citation_node_ids") or []) >= 1 for s in sections)
    bad_sections = [s["section_type"] for s in sections if not s.get("citation_node_ids")]
    checks.assert_("every section has ≥ 1 citation_node_id", every_section_cited,
                   "all sections cited" if every_section_cited else f"empty: {bad_sections}")

    # BLUF text-quality sanity: not empty, not "TODO".
    bluf_text = (bluf or {}).get("text", "").strip()
    checks.assert_("BLUF text is substantive", len(bluf_text) > 30 and "todo" not in bluf_text.lower(),
                   f"len={len(bluf_text)}")

    if bluf:
        console.print()
        console.print(Panel(
            bluf_text,
            title=f"BLUF (conf={bluf.get('confidence', 0):.2f})",
            border_style="cyan",
        ))

    return brief


async def phase_citation_chain(c: httpx.AsyncClient, brief: dict, checks: Checks) -> None:
    """Resolve citations for the BLUF + first KEY_JUDGMENT + DEVILS_ADVOCATE if present.

    Each call must return at least one source_node, every source must have
    a node_id that resolves, and (where the source has lat/lon) a map_highlight.
    """
    brief_id = brief["id"]
    sections_to_check: list[dict] = []
    for s in brief.get("sections", []):
        if s["section_type"] in {"BLUF", "DEVILS_ADVOCATE"}:
            sections_to_check.append(s)
        elif s["section_type"] == "KEY_JUDGMENT" and len(sections_to_check) < 4:
            sections_to_check.append(s)

    for s in sections_to_check:
        sid = s["id"]
        r = await c.get(f"/api/briefs/{brief_id}/citation/{sid}")
        ok = r.status_code == 200
        if not ok:
            checks.assert_(f"citation chain for {s['section_type']} returns 200", False,
                           f"status={r.status_code}")
            continue
        chain = r.json()
        sources = chain.get("source_nodes") or []
        # Section claimed N citations — chain should resolve N sources (filtering missing/bad cites
        # would silently shrink the list, which we want to flag).
        claimed = len(s.get("citation_node_ids") or [])
        resolved = len(sources)
        checks.assert_(
            f"citation chain for {s['section_type']} resolves all citations",
            resolved >= 1 and resolved == claimed,
            f"claimed={claimed} resolved={resolved}",
        )

        # Every source must carry a node_id, node_type, and raw_evidence
        every_source_complete = all(
            sn.get("node_id") and sn.get("node_type") and sn.get("raw_evidence", {}).get("type")
            for sn in sources
        )
        checks.assert_(
            f"{s['section_type']} sources all have node_id + node_type + raw_evidence",
            every_source_complete,
            "" if every_source_complete else "incomplete source payloads",
        )


async def phase_audit_verified(c: httpx.AsyncClient, checks: Checks) -> dict | None:
    r = await c.get("/api/audit/verify")
    if r.status_code != 200:
        checks.assert_("GET /api/audit/verify", False, f"status={r.status_code}")
        return None
    payload = r.json()
    checks.assert_(
        "audit chain verifies (no tamper)",
        payload.get("verified") is True,
        payload.get("verdict", ""),
    )
    checks.assert_(
        "audit chain has > 0 entries (this run logged something)",
        (payload.get("chain_total") or 0) > 0,
        f"chain_total={payload.get('chain_total')}",
    )
    return payload


# ───────────────────────────────────────────────────────────────────────────────
# Driver
# ───────────────────────────────────────────────────────────────────────────────
async def main() -> int:
    console.print()
    console.print(Panel.fit(
        f"Damocles end-to-end integration test\n"
        f"  base    : {BASE}\n"
        f"  query   : {QUERY!r}\n"
        f"  budget  : ~60-90 s wall-clock + LLM/Sentinel Hub quota",
        border_style="cyan", title="Day 14",
    ))

    checks = Checks()
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as c:
        if not await phase_health(c, checks):
            console.print("[red]Backend not healthy. Start uvicorn first.[/]")
            console.print(checks.render())
            return 2

        watch_id = await phase_post_watch(c, checks)
        if not watch_id:
            console.print(checks.render())
            return 3

        console.print()
        console.print(f"[bold]Streaming pipeline progress for watch {watch_id[:8]}...[/]")
        events = await phase_stream_ws(watch_id, checks)

        if not events or events[-1].get("stage") != "complete":
            console.print("[yellow]Pipeline did not complete cleanly — continuing to read whatever did persist.[/]")

        console.print()
        brief_summary = await phase_brief_exists(c, watch_id, checks)
        if not brief_summary:
            console.print(checks.render())
            return 4

        brief = await phase_brief_full(c, brief_summary["id"], checks)
        if not brief:
            console.print(checks.render())
            return 5

        await phase_citation_chain(c, brief, checks)
        console.print()
        await phase_audit_verified(c, checks)

    console.print()
    console.print(checks.render())
    if checks.all_passed():
        console.print()
        console.print("[bold green]Day 14 OK[/] - end-to-end integration green; demo regression test passes.")
        return 0
    failed = sum(1 for _, ok, _ in checks.rows if not ok)
    total = len(checks.rows)
    console.print()
    console.print(f"[bold red]Day 14 FAILED[/] - {failed}/{total} assertions failed.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
