"""Live OSINTAgent smoke test.

Picks a CompositeEvent that has at least one NewsEvent or SocialSignal source
(prefers AMBER) and runs ``OSINTAgent`` against it. Prints the structured
output and verifies citations resolve.

Prereq: ``uv run python scripts/seed_neo4j.py`` has been run.
"""
from __future__ import annotations

import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backend.agents.osint_agent import OSINTAgent
from backend.graph.client import graph_client
from backend.llm.factory import get_provider

console = Console()


async def _pick_composite() -> dict | None:
    """Prefer AMBER + NewsEvent. Fall back to any composite with OSINT source."""
    rows = await graph_client.run("""
        MATCH (ce:CompositeEvent {threat_grade: 'AMBER'})-[:COMPOSED_OF]->(:NewsEvent)
        RETURN ce ORDER BY ce.confidence DESC LIMIT 1
    """)
    if rows:
        return rows[0]["ce"]
    rows = await graph_client.run("""
        MATCH (ce:CompositeEvent)-[:COMPOSED_OF]->(s)
        WHERE s:NewsEvent OR s:SocialSignal
        RETURN ce ORDER BY ce.confidence DESC LIMIT 1
    """)
    return rows[0]["ce"] if rows else None


async def main() -> int:
    await graph_client.connect()
    try:
        ce = await _pick_composite()
        if ce is None:
            console.print("[red]No OSINT-source composites in the graph. Run seed_neo4j.py first.[/]")
            return 2

        console.print(Panel.fit(
            f"id           : {ce['id']}\n"
            f"threat_grade : {ce['threat_grade']}\n"
            f"confidence   : {ce['confidence']}\n"
            f"summary      : {ce['summary']}",
            title="CompositeEvent under analysis", border_style="cyan",
        ))

        provider = get_provider()
        if not await provider.health_check():
            console.print("[red]LLM provider not reachable.[/]")
            return 3
        console.print(f"[dim]LLM: {provider.get_model_name()}[/]")
        console.print()

        agent = OSINTAgent(llm=provider, graph=graph_client)
        out = await agent.run(composite_event_id=ce["id"])

        console.print(Panel(out.analysis, title="analysis", border_style="green"))

        t = Table(title=f"key_findings (confidence={out.confidence})")
        t.add_column("#", justify="right")
        t.add_column("finding")
        for i, f in enumerate(out.key_findings, 1):
            t.add_row(str(i), f)
        console.print(t)

        console.print(Panel(
            "\n".join(f"- {u}" for u in out.uncertainty_flags),
            title="uncertainty_flags", border_style="yellow",
        ))

        # Verify citations resolve in Neo4j
        ct = Table(title="citation_node_ids resolution")
        ct.add_column("node id (truncated)")
        ct.add_column("type")
        ct.add_column("identity")
        for nid in out.citation_node_ids:
            r = await graph_client.run(
                "MATCH (n {id: $id}) RETURN labels(n)[0] AS t, n", id=nid
            )
            if not r:
                ct.add_row(nid[:20] + "...", "[red]NOT FOUND[/]", "")
                continue
            t_, n_ = r[0]["t"], r[0]["n"]
            if t_ == "NewsEvent":
                ident = f"{n_.get('source_name', '?')}: {(n_.get('headline') or '')[:50]}"
            elif t_ == "SocialSignal":
                ident = f"{n_.get('channel', '?')}: {(n_.get('text') or '')[:50]}"
            elif t_ == "CompositeEvent":
                ident = f"grade={n_.get('threat_grade')} conf={n_.get('confidence')}"
            else:
                ident = "-"
            ct.add_row(nid[:20] + "...", t_, ident)
        console.print(ct)

        console.print()
        console.print("[bold green]Day 9 OSINTAgent OK[/]")
        return 0
    finally:
        await graph_client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
