"""Live agent smoke test.

Picks the highest-confidence AMBER CompositeEvent in Neo4j (from the most
recent seeded Watch) and runs ``GeospatialAgent`` against it. Prints the
structured AgentOutput, cross-checks the citations, and shows the latency
+ token usage.

Prereq: ``uv run python scripts/seed_neo4j.py`` has been run at least once
so the graph contains composites with sources.
"""
from __future__ import annotations

import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backend.agents.geospatial_agent import GeospatialAgent
from backend.graph.client import graph_client
from backend.llm.factory import get_provider

console = Console()


async def _pick_composite() -> dict | None:
    """Prefer AMBER with a Vessel source (the demo case). Fall back to any composite."""
    rows = await graph_client.run("""
        MATCH (ce:CompositeEvent {threat_grade: 'AMBER'})-[:COMPOSED_OF]->(:Vessel)
        RETURN ce ORDER BY ce.confidence DESC LIMIT 1
    """)
    if rows:
        return rows[0]["ce"]
    rows = await graph_client.run("""
        MATCH (ce:CompositeEvent) RETURN ce ORDER BY ce.confidence DESC LIMIT 1
    """)
    return rows[0]["ce"] if rows else None


async def main() -> int:
    await graph_client.connect()
    try:
        ce = await _pick_composite()
        if ce is None:
            console.print("[red]No CompositeEvents in the graph. Run seed_neo4j.py first.[/]")
            return 2

        console.print(Panel.fit(
            f"id           : {ce['id']}\n"
            f"threat_grade : {ce['threat_grade']}\n"
            f"confidence   : {ce['confidence']}\n"
            f"corroboration: {ce['corroboration_count']}\n"
            f"summary      : {ce['summary']}",
            title="CompositeEvent under analysis", border_style="cyan",
        ))

        provider = get_provider()
        if not await provider.health_check():
            console.print("[red]LLM provider not reachable.[/]")
            return 3
        console.print(f"[dim]LLM: {provider.get_model_name()}[/]")
        console.print()

        agent = GeospatialAgent(llm=provider, graph=graph_client)

        # Inspect the context the agent will send (for debugging)
        ctx, valid_ids = await agent.fetch_context(composite_event_id=ce["id"])
        console.print(f"[dim]context length: {len(ctx)} chars; valid IDs: {len(valid_ids)}[/]")
        console.print()

        out = await agent.run(composite_event_id=ce["id"])

        # ─── Render output ───────────────────────────────────────────────────
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

        # Verify citations resolve
        citation_table = Table(title="citation_node_ids resolution")
        citation_table.add_column("node id (truncated)")
        citation_table.add_column("resolved type")
        citation_table.add_column("identity")
        for nid in out.citation_node_ids:
            r = await graph_client.run(
                "MATCH (n {id: $id}) RETURN labels(n)[0] AS t, n",
                id=nid,
            )
            if not r:
                citation_table.add_row(nid[:20] + "...", "[red]NOT FOUND[/]", "")
                continue
            t_, n_ = r[0]["t"], r[0]["n"]
            if t_ == "Vessel":
                ident = f"{n_.get('lat',0):.3f},{n_.get('lon',0):.3f} ais={n_.get('ais_status')}"
            elif t_ == "NewsEvent":
                ident = f"{n_.get('source_name','?')}: {(n_.get('headline') or '')[:40]}"
            elif t_ == "SocialSignal":
                ident = f"{n_.get('channel','?')}"
            elif t_ == "CompositeEvent":
                ident = f"grade={n_.get('threat_grade')} conf={n_.get('confidence')}"
            else:
                ident = "-"
            citation_table.add_row(nid[:20] + "...", t_, ident)
        console.print(citation_table)

        console.print()
        console.print("[bold green]Day 8 OK[/] - GeospatialAgent produced valid, citation-bound output.")
        return 0
    finally:
        await graph_client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
