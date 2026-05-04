"""Day 11 end-to-end smoke: full agent pipeline + brief assembly + ingestion.

For one CompositeEvent:
  1. Run GeospatialAgent + OSINTAgent (the factual primaries)
  2. Run DevilsAdvocateAgent on the primaries' outputs
  3. Run SupervisorAgent on all of them, assemble a canonical Brief
  4. Ingest the Brief into Neo4j
  5. Run the **gold-medal citation chain query** in Cypher and print results

Step 5 is what fires when a judge clicks a sentence in the demo.

Prereq: ``scripts/seed_neo4j.py`` has been run.
"""
from __future__ import annotations

import asyncio
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backend.agents.devils_advocate import DevilsAdvocateAgent
from backend.agents.geospatial_agent import GeospatialAgent
from backend.agents.osint_agent import OSINTAgent
from backend.agents.supervisor_agent import SupervisorAgent, run_supervisor_and_assemble
from backend.graph.client import graph_client
from backend.graph.ingestion import ingest_brief
from backend.llm.factory import get_devil_provider, get_provider

console = Console()


async def _pick_composite() -> dict | None:
    rows = await graph_client.run("""
        MATCH (ce:CompositeEvent {threat_grade: 'AMBER'})-[:COMPOSED_OF]->(s)
        RETURN ce ORDER BY ce.confidence DESC LIMIT 1
    """)
    if rows:
        return rows[0]["ce"]
    rows = await graph_client.run(
        "MATCH (ce:CompositeEvent) RETURN ce ORDER BY ce.confidence DESC LIMIT 1"
    )
    return rows[0]["ce"] if rows else None


async def _pick_watch_id() -> str | None:
    rows = await graph_client.run(
        "MATCH (w:Watch) RETURN w.id AS id ORDER BY w.created_at DESC LIMIT 1"
    )
    return rows[0]["id"] if rows else None


async def _source_count(ce_id: str) -> int:
    rows = await graph_client.run(
        "MATCH (:CompositeEvent {id: $id})-[:COMPOSED_OF]->(s) RETURN count(s) AS n",
        id=ce_id,
    )
    return rows[0]["n"] if rows else 0


async def main() -> int:
    await graph_client.connect()
    try:
        ce = await _pick_composite()
        if ce is None:
            console.print("[red]No composites in the graph. Run seed_neo4j.py first.[/]")
            return 2

        watch_id = await _pick_watch_id()
        if watch_id is None:
            console.print("[red]No Watch in the graph.[/]")
            return 2

        provider = get_provider()
        if not await provider.health_check():
            console.print("[red]LLM provider not reachable.[/]")
            return 3

        console.print(Panel.fit(
            f"composite      : {ce['id']}\n"
            f"watch          : {watch_id}\n"
            f"threat_grade   : {ce['threat_grade']}\n"
            f"summary        : {ce['summary']}\n"
            f"primary LLM    : {provider.get_model_name()}",
            title="Run", border_style="cyan",
        ))
        console.print()

        # ─── Run primaries ────────────────────────────────────────────────────
        t_start = time.time()
        prior_outputs = []

        try:
            geo_out = await GeospatialAgent(llm=provider, graph=graph_client).run(
                composite_event_id=ce["id"]
            )
            prior_outputs.append(("geospatial_agent", geo_out))
            console.print(f"[green]GEO[/]    {len(geo_out.key_findings)} findings, conf={geo_out.confidence}")
        except Exception as exc:
            console.print(f"[red]GeospatialAgent failed: {exc}[/]")

        try:
            osint_out = await OSINTAgent(llm=provider, graph=graph_client).run(
                composite_event_id=ce["id"]
            )
            prior_outputs.append(("osint_agent", osint_out))
            console.print(f"[blue]OSINT[/]  {len(osint_out.key_findings)} findings, conf={osint_out.confidence}")
        except Exception as exc:
            console.print(f"[red]OSINTAgent failed: {exc}[/]")

        # ─── Devil's advocate against the primaries ──────────────────────────
        devil_provider = get_devil_provider()
        try:
            devil_out = await DevilsAdvocateAgent(llm=devil_provider, graph=graph_client).run(
                composite_event_id=ce["id"], prior_outputs=prior_outputs
            )
            prior_outputs.append(("devils_advocate", devil_out))
            console.print(
                f"[red]DEVIL[/]  {len(devil_out.key_findings)} challenges, "
                f"conf={devil_out.confidence}, devil_confidence={devil_out.devil_confidence}"
            )
        except Exception as exc:
            console.print(f"[red]DevilsAdvocate failed: {exc}[/]")

        if not prior_outputs:
            console.print("[red]No prior outputs to supervise.[/]")
            return 4
        console.print()

        # ─── Supervisor + assembly ───────────────────────────────────────────
        supervisor = SupervisorAgent(llm=provider, graph=graph_client)
        sources_count = await _source_count(ce["id"])
        brief = await run_supervisor_and_assemble(
            agent=supervisor,
            composite_event_id=ce["id"],
            watch_id=watch_id,
            prior_outputs=prior_outputs,
            sources_count=sources_count,
        )
        elapsed = round(time.time() - t_start, 2)
        console.print(f"[bold green]Brief assembled[/] in {elapsed}s "
                      f"({len(brief.all_sections())} sections)")
        console.print()

        # ─── Render the brief ────────────────────────────────────────────────
        console.print(Panel(
            f"[bold]{brief.bluf.text}[/]\n\n"
            f"confidence: {brief.bluf.confidence}",
            title="BLUF (Bottom Line Up Front)", border_style="cyan",
        ))

        kj_table = Table(title=f"Key Judgments ({len(brief.key_judgments)})")
        kj_table.add_column("#", justify="right")
        kj_table.add_column("conf", justify="right")
        kj_table.add_column("source")
        kj_table.add_column("text")
        for i, kj in enumerate(brief.key_judgments, 1):
            kj_table.add_row(str(i), f"{kj.confidence:.2f}", kj.agent_source, kj.text)
        console.print(kj_table)

        if brief.supporting_evidence:
            se_table = Table(title=f"Supporting Evidence ({len(brief.supporting_evidence)})")
            se_table.add_column("#", justify="right")
            se_table.add_column("source")
            se_table.add_column("text")
            for i, se in enumerate(brief.supporting_evidence, 1):
                se_table.add_row(str(i), se.agent_source, se.text)
            console.print(se_table)

        if brief.devils_advocate is not None:
            d = brief.devils_advocate
            console.print(Panel(
                f"{d.text}\n\ndevil_confidence: {d.extra.get('devil_confidence', '-')}",
                title="Devil's Advocate (counter-signal)", border_style="red",
            ))

        if brief.recommendation is not None:
            r = brief.recommendation
            urgency = r.extra.get("urgency", "ROUTINE")
            color = {"IMMEDIATE": "red", "PRIORITY": "yellow", "ROUTINE": "green"}.get(urgency, "white")
            console.print(Panel(
                f"[{color}]{urgency}[/] - {r.text}",
                title="Recommended Action", border_style=color,
            ))

        # ─── Ingest the Brief into Neo4j ─────────────────────────────────────
        await ingest_brief(graph_client, brief)
        console.print()
        console.print(f"[green]Ingested[/] Brief {brief.id[:8]} -> Neo4j "
                      f"with {len(brief.all_sections())} BriefSection nodes")
        console.print()

        # ─── The gold-medal citation chain query ─────────────────────────────
        # Pick the BLUF section and walk its CITES edges to source nodes.
        chain = await graph_client.run(
            """
            MATCH (b:Brief {id: $brief_id})-[:CONTAINS]->(bs:BriefSection {section_type: 'BLUF'})
            OPTIONAL MATCH (bs)-[r:CITES]->(source)
            RETURN bs, collect({type: r.node_type, props: source}) AS sources
            """,
            brief_id=brief.id,
        )
        if not chain:
            console.print("[red]Citation chain query returned no rows![/]")
            return 5

        bs = chain[0]["bs"]
        sources = [s for s in chain[0]["sources"] if s and s.get("type")]
        ct = Table(title=f"Citation chain for BLUF section {bs['id'][:8]}")
        ct.add_column("source type")
        ct.add_column("source id (truncated)")
        ct.add_column("identity / location")
        for s in sources:
            t_, p = s["type"], dict(s["props"])
            sid = (p.get("id") or "")[:20] + "..."
            if t_ == "Vessel":
                ident = f"{p.get('lat',0):.3f},{p.get('lon',0):.3f} ais={p.get('ais_status')}"
            elif t_ == "NewsEvent":
                ident = f"{p.get('source_name','?')}: {(p.get('headline') or '')[:50]}"
            elif t_ == "SocialSignal":
                ident = f"{p.get('channel','?')}"
            elif t_ == "CompositeEvent":
                ident = f"grade={p.get('threat_grade')} conf={p.get('confidence')}"
            else:
                ident = "-"
            ct.add_row(t_, sid, ident)
        console.print(ct)
        console.print()
        console.print(f"[bold green]Day 11 OK[/] - "
                      f"end-to-end pipeline -> Brief -> Neo4j -> citation chain query "
                      f"all wired in {elapsed}s.")
        return 0
    finally:
        await graph_client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
