"""End-to-end API smoke (no full pipeline).

Exercises the read-only endpoints against whatever Brief was last ingested
by ``scripts/test_brief_assembly.py``:

  GET  /health
  GET  /api/watches
  GET  /api/watches/{watch_id}
  GET  /api/briefs?watch_id=...
  GET  /api/briefs/{brief_id}                       full brief
  GET  /api/briefs/{brief_id}/citation/{bluf_id}    gold-medal citation chain
  GET  /api/graph/{watch_id}                        Cytoscape payload
  GET  /api/audit

Skips POST /api/watches because spinning up the full pipeline through
the API takes ~20s and we already proved it works in test_brief_assembly.

Usage: start the backend separately
    uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

then in another shell
    uv run python scripts/test_api.py
"""
from __future__ import annotations

import asyncio
import sys

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
BASE = "http://127.0.0.1:8000"


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=10.0) as c:
        # ─── /health
        r = await c.get("/health")
        h = r.json()
        console.print(Panel.fit(
            f"status     : {h['status']}\n"
            f"neo4j      : {h['neo4j']['ok']}\n"
            f"llm        : {h['llm']['ok']} (model={h['llm']['model']})",
            title="GET /health", border_style="green",
        ))

        # ─── /api/watches list
        r = await c.get("/api/watches?limit=5")
        watches = r.json()
        if not watches:
            console.print("[red]No watches in graph. Run scripts/test_brief_assembly.py first.[/]")
            return 2
        latest = watches[0]
        wid = latest["id"]
        console.print(f"[bold]Latest watch:[/] {wid[:8]} ({latest.get('raw_query', '?')})")

        # ─── /api/watches/{id}
        r = await c.get(f"/api/watches/{wid}")
        meta = r.json()
        console.print(f"  is_done      : {meta['is_done']}")
        console.print(f"  event_count  : {meta['event_count']}")
        console.print(f"  last_event   : {(meta.get('last_event') or {}).get('stage', '-')}")
        console.print()

        # ─── /api/briefs?watch_id=...
        r = await c.get("/api/briefs", params={"watch_id": wid})
        briefs = r.json()
        if not briefs:
            console.print("[yellow]No briefs for this watch. Run test_brief_assembly.py first.[/]")
            return 3
        bid = briefs[0]["id"]
        console.print(f"[bold]Latest brief:[/] {bid[:8]} for watch {wid[:8]}")

        # ─── /api/briefs/{bid}
        r = await c.get(f"/api/briefs/{bid}")
        full = r.json()
        sections = full["sections"]
        bluf = next((s for s in sections if s["section_type"] == "BLUF"), None)
        if bluf is None:
            console.print("[red]Brief has no BLUF section![/]")
            return 4

        kj_count = sum(1 for s in sections if s["section_type"] == "KEY_JUDGMENT")
        sup_count = sum(1 for s in sections if s["section_type"] == "SUPPORTING")
        has_devil = any(s["section_type"] == "DEVILS_ADVOCATE" for s in sections)
        has_rec   = any(s["section_type"] == "RECOMMENDATION" for s in sections)

        console.print(f"  sections     : {len(sections)}")
        console.print(f"  key_judgments: {kj_count}")
        console.print(f"  supporting   : {sup_count}")
        console.print(f"  devil        : {has_devil}")
        console.print(f"  recommend.   : {has_rec}")
        console.print()
        console.print(Panel(bluf["text"], title=f"BLUF (conf={bluf['confidence']:.2f})", border_style="cyan"))

        # ─── /api/briefs/{bid}/citation/{bluf_id} — THE GOLD-MEDAL ENDPOINT
        r = await c.get(f"/api/briefs/{bid}/citation/{bluf['id']}")
        chain = r.json()
        console.print()

        ct = Table(title=f"GET /api/briefs/{{bid}}/citation/{{bluf_id}} - {len(chain['source_nodes'])} sources")
        ct.add_column("type")
        ct.add_column("identity")
        ct.add_column("map_highlight")
        ct.add_column("evidence_type")
        for sn in chain["source_nodes"]:
            p = sn["properties"]
            if sn["node_type"] == "Vessel":
                ident = f"{p.get('lat', 0):.3f},{p.get('lon', 0):.3f} ais={p.get('ais_status')}"
            elif sn["node_type"] == "NewsEvent":
                ident = f"{p.get('source_name', '?')}: {(p.get('headline') or '')[:40]}"
            elif sn["node_type"] == "SocialSignal":
                ident = f"{p.get('channel', '?')}"
            elif sn["node_type"] == "CompositeEvent":
                ident = f"grade={p.get('threat_grade')} conf={p.get('confidence')}"
            else:
                ident = "-"
            mh = sn.get("map_highlight")
            mh_text = f"({mh['lat']:.2f}, {mh['lon']:.2f}) r={mh['radius_km']}km" if mh else "-"
            ct.add_row(sn["node_type"], ident, mh_text, sn["raw_evidence"].get("type", "-"))
        console.print(ct)
        cb = chain["confidence_breakdown"]
        console.print(f"  confidence_breakdown: section={cb['section_confidence']}, "
                      f"sources={cb['source_count']}, corroboration={cb['corroboration_count']}")
        console.print()

        # ─── /api/graph/{wid}
        r = await c.get(f"/api/graph/{wid}", params={"limit": 100})
        g = r.json()
        type_counts: dict[str, int] = {}
        for n in g["nodes"]:
            type_counts[n["type"]] = type_counts.get(n["type"], 0) + 1
        edge_counts: dict[str, int] = {}
        for e in g["edges"]:
            edge_counts[e["type"]] = edge_counts.get(e["type"], 0) + 1
        console.print(Panel.fit(
            f"nodes: {len(g['nodes']):>4}   by type: {type_counts}\n"
            f"edges: {len(g['edges']):>4}   by type: {edge_counts}",
            title=f"GET /api/graph/{{wid}}", border_style="magenta",
        ))

        # ─── /api/audit
        r = await c.get("/api/audit?hours_back=24")
        a = r.json()
        console.print(Panel.fit(
            f"entries: {a['count']}\n"
            f"verified: {a['verified']}\n"
            f"note: {a.get('note') or '(populated)'}",
            title="GET /api/audit", border_style="yellow",
        ))

    console.print()
    console.print("[bold green]Day 12 OK[/] - all REST endpoints serving correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
