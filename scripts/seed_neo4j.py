"""End-of-Week-1 integration test: full pipeline -> Neo4j -> citation query.

Runs ``WatchExecutor`` against a real time window for a given query, writes
every sensor event + composite event to Neo4j, then runs the gold-medal
citation chain query in Cypher to prove the wiring is end-to-end.

Defaults are tuned for an end-of-week-1 smoke test:
- query   : "Aegean - last 7 days"
- AIS     : skipped by default (no historical replay; Day 7 isn't where we
            invest in the seed-and-replay infra). Pass --enable-ais to capture
            ~30 s of live AIS and fold it into the cross-reference.
- Telegram: skipped automatically if no Telethon session exists.

This is the moment where Neo4j Browser at http://localhost:7474 should show
a populated graph with vessels, news, social signals, and composite events.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

from backend.graph.client import graph_client
from backend.llm.factory import get_provider
from backend.watch_engine.executor import WatchExecutor

console = Console()


async def main(query: str, enable_ais: bool, ais_seconds: float) -> int:
    console.print()
    console.print(f"[bold]Damocles seed run[/]")
    console.print(f"  query       : {query!r}")
    console.print(f"  AIS capture : {'on' if enable_ais else 'off'}")
    if enable_ais:
        console.print(f"  AIS seconds : {ais_seconds:.0f}")
    console.print()

    # Connect graph + apply schema (idempotent)
    await graph_client.connect()
    await graph_client.apply_schema()

    provider = get_provider()
    if not await provider.health_check():
        console.print("[red]LLM provider not reachable. Check .env / GEMINI_MODEL.[/]")
        return 2

    exec_ = WatchExecutor(
        graph=graph_client,
        llm=provider,
        enable_ais=enable_ais,
        ais_capture_seconds=ais_seconds,
        enable_telegram=True,   # auto-skip if no session
    )

    # 1. Parse the query into a Watch
    watch = await exec_.parse_query(query)
    console.print(f"[bold]Parsed Watch[/]")
    console.print(f"  id       : {watch.id}")
    console.print(f"  region   : {watch.spec.region.value}")
    console.print(f"  domain   : {watch.spec.domain.value}")
    console.print(f"  window   : {watch.spec.time_window_days} day(s)")
    console.print(f"  bbox     : {watch.spec.get_bbox()}")
    console.print()

    # 2. Stream pipeline progress
    console.print("[bold]Pipeline progress[/]")
    async for event in exec_.execute(watch):
        status_color = {"complete": "green", "started": "cyan", "failed": "red"}.get(
            event["status"], "yellow"
        )
        console.print(
            f"  [{status_color}]{event['progress_pct']:>3}%[/] "
            f"{event['stage']:<20} {event['status']:<8} {event['detail']}"
        )
    console.print()

    # 3. Verify the graph
    await _print_graph_summary(watch.id)

    # 4. Verify the citation chain (the gold-medal query)
    await _print_citation_chain_proof(watch.id)

    await graph_client.close()
    return 0


async def _print_graph_summary(watch_id: str) -> None:
    console.print("[bold]Graph summary[/]")
    rows = await graph_client.run("""
        MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n
        ORDER BY n DESC
    """)
    table = Table(show_header=True)
    table.add_column("node label")
    table.add_column("count", justify="right")
    for r in rows:
        table.add_row(r["label"] or "(none)", str(r["n"]))
    console.print(table)

    rows = await graph_client.run("""
        MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n
        ORDER BY n DESC
    """)
    table = Table(show_header=True)
    table.add_column("edge type")
    table.add_column("count", justify="right")
    for r in rows:
        table.add_row(r["type"], str(r["n"]))
    console.print(table)

    # Watch-rooted summary
    rows = await graph_client.run(
        """
        MATCH (w:Watch {id: $id})-[:TRIGGERED]->(ce:CompositeEvent)
        RETURN ce.threat_grade AS grade, count(ce) AS n
        ORDER BY grade
        """,
        id=watch_id,
    )
    table = Table(title=f"CompositeEvents for watch {watch_id[:8]}", show_header=True)
    table.add_column("threat grade")
    table.add_column("count", justify="right")
    if not rows:
        table.add_row("(none)", "0")
    for r in rows:
        table.add_row(r["grade"], str(r["n"]))
    console.print(table)
    console.print()


async def _print_citation_chain_proof(watch_id: str) -> None:
    """Pick the highest-confidence CompositeEvent and walk one source link.

    This is the gold-medal demo path executed in raw Cypher: a graph row
    plus the resolved source-node properties. When the BriefSection layer
    lands in Week 2, this same path is what the analyst's click traverses.
    """
    rows = await graph_client.run(
        """
        MATCH (w:Watch {id: $id})-[:TRIGGERED]->(ce:CompositeEvent)
        RETURN ce ORDER BY ce.confidence DESC LIMIT 1
        """,
        id=watch_id,
    )
    if not rows:
        console.print("[yellow]No composite events on this watch — nothing to chain.[/]")
        return

    ce = rows[0]["ce"]
    console.print("[bold]Citation chain proof[/]")
    console.print(f"  top composite event id   : {ce['id']}")
    console.print(f"  threat_grade             : {ce['threat_grade']}")
    console.print(f"  confidence               : {ce['confidence']}")
    console.print(f"  corroboration_count      : {ce['corroboration_count']}")
    console.print(f"  summary                  : {ce['summary']}")
    console.print()

    # Walk the COMPOSED_OF edges to the underlying sensor evidence
    rows = await graph_client.run(
        """
        MATCH (ce:CompositeEvent {id: $id})-[:COMPOSED_OF]->(source)
        RETURN labels(source)[0] AS type, source LIMIT 5
        """,
        id=ce["id"],
    )
    table = Table(title="Source nodes (the evidence the brief will cite)")
    table.add_column("node type")
    table.add_column("id (truncated)")
    table.add_column("identity / location")
    for r in rows:
        s: dict[str, Any] = r["source"]
        ident = _identify(r["type"], s)
        table.add_row(r["type"], (s.get("id") or "")[:20] + "...", ident)
    console.print(table)
    console.print()
    console.print("[bold green]Day 7 OK[/] — Watch -> sensors -> fusion -> Neo4j -> citation chain all wired")


def _identify(node_type: str, s: dict[str, Any]) -> str:
    if node_type == "Vessel":
        bits = [f"{s.get('lat', '?'):.3f}", f"{s.get('lon', '?'):.3f}"]
        if s.get("mmsi"):
            bits.append(f"mmsi={s['mmsi']}")
        if s.get("ais_status"):
            bits.append(f"ais={s['ais_status']}")
        return " ".join(bits)
    if node_type == "NewsEvent":
        return f"{s.get('source_name', '?')}: {(s.get('headline') or '')[:50]}"
    if node_type == "SocialSignal":
        return f"{s.get('channel', '?')}: {(s.get('text') or '')[:50]}"
    return str(s.get("id", "?"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--query", default="Aegean - last 7 days",
                   help="Free-text query to seed (parsed by the LLM Watch parser).")
    p.add_argument("--enable-ais", action="store_true",
                   help="Capture ~30 s of live AIS and fold into the SAR cross-reference. Off by default for Day 7 because SAR/AIS timestamps don't align without seed-and-replay infra.")
    p.add_argument("--ais-seconds", type=float, default=30.0,
                   help="If --enable-ais, how long to capture (default 30 s).")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args.query, args.enable_ais, args.ais_seconds)))
