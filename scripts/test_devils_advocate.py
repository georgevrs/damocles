"""Live Devil's Advocate smoke test.

Picks a CompositeEvent with both Vessel and OSINT sources (or AMBER + any),
runs Geospatial + OSINT agents to produce primary outputs, then feeds them
to the Devil's Advocate. Prints all three side-by-side so you can see
whether the devil produced substantive challenges or just noise.

Prereq: ``uv run python scripts/seed_neo4j.py`` has been run.
"""
from __future__ import annotations

import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backend.agents.devils_advocate import DevilsAdvocateAgent
from backend.agents.geospatial_agent import GeospatialAgent
from backend.agents.osint_agent import OSINTAgent
from backend.graph.client import graph_client
from backend.llm.factory import get_devil_provider, get_provider

console = Console()


async def _pick_composite() -> dict | None:
    rows = await graph_client.run("""
        MATCH (ce:CompositeEvent {threat_grade: 'AMBER'})-[:COMPOSED_OF]->(s)
        WHERE s:NewsEvent OR s:Vessel
        RETURN ce ORDER BY ce.confidence DESC LIMIT 1
    """)
    if rows:
        return rows[0]["ce"]
    rows = await graph_client.run(
        "MATCH (ce:CompositeEvent) RETURN ce ORDER BY ce.confidence DESC LIMIT 1"
    )
    return rows[0]["ce"] if rows else None


def _show_agent(name: str, out, color: str) -> None:
    console.print(Panel(out.analysis, title=f"{name} :: analysis", border_style=color))
    table = Table(title=f"{name} :: key_findings (confidence={out.confidence})")
    table.add_column("#", justify="right")
    table.add_column("finding")
    for i, f in enumerate(out.key_findings, 1):
        table.add_row(str(i), f)
    console.print(table)
    console.print(Panel(
        "\n".join(f"- {u}" for u in out.uncertainty_flags),
        title=f"{name} :: uncertainty_flags", border_style="yellow",
    ))


async def main() -> int:
    await graph_client.connect()
    try:
        ce = await _pick_composite()
        if ce is None:
            console.print("[red]No composites in the graph. Run seed_neo4j.py first.[/]")
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
        console.print(f"[dim]Primary LLM: {provider.get_model_name()}[/]")

        # 1. Run primary agents
        prior_outputs = []

        try:
            geo_out = await GeospatialAgent(llm=provider, graph=graph_client).run(
                composite_event_id=ce["id"]
            )
            prior_outputs.append(("geospatial_agent", geo_out))
            _show_agent("GEOSPATIAL", geo_out, "green")
        except Exception as exc:
            console.print(f"[red]GeospatialAgent failed: {exc}[/]")

        try:
            osint_out = await OSINTAgent(llm=provider, graph=graph_client).run(
                composite_event_id=ce["id"]
            )
            prior_outputs.append(("osint_agent", osint_out))
            _show_agent("OSINT", osint_out, "blue")
        except Exception as exc:
            console.print(f"[red]OSINTAgent failed: {exc}[/]")

        if not prior_outputs:
            console.print("[red]No primary outputs to challenge.[/]")
            return 4

        # 2. Run Devil's Advocate against the prior outputs
        devil_provider = get_devil_provider()
        console.print(f"\n[dim]Devil LLM:   {devil_provider.get_model_name()}[/]\n")
        devil = DevilsAdvocateAgent(llm=devil_provider, graph=graph_client)
        devil_out = await devil.run(
            composite_event_id=ce["id"],
            prior_outputs=prior_outputs,
        )

        _show_agent("DEVIL'S ADVOCATE", devil_out, "red")

        signal_color = "red" if devil_out.devil_confidence >= 0.6 else (
            "yellow" if devil_out.devil_confidence >= 0.35 else "green"
        )
        console.print(Panel(
            f"devil_confidence = [{signal_color}]{devil_out.devil_confidence:.2f}[/]\n\n"
            f"Reading: {'primary likely WRONG' if devil_out.devil_confidence >= 0.6 else 'evidence ambiguous' if devil_out.devil_confidence >= 0.35 else 'primary likely RIGHT, only minor caveats'}",
            title="Counter-signal", border_style=signal_color,
        ))

        # Verify devil's citations resolve
        ct = Table(title="devil's citation_node_ids resolution")
        ct.add_column("node id (truncated)")
        ct.add_column("type")
        for nid in devil_out.citation_node_ids:
            r = await graph_client.run(
                "MATCH (n {id: $id}) RETURN labels(n)[0] AS t", id=nid
            )
            ct.add_row(nid[:20] + "...", r[0]["t"] if r else "[red]NOT FOUND[/]")
        console.print(ct)

        console.print()
        console.print("[bold green]Day 10 Devil's Advocate OK[/] - "
                      f"{len(prior_outputs)} primary agent(s) challenged, "
                      f"devil_confidence={devil_out.devil_confidence:.2f}")
        return 0
    finally:
        await graph_client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
