"""End-to-end audit smoke + tamper test.

Two passes:

  PASS A — Run the brief assembly pipeline against the latest seeded
  composite, then verify the resulting audit chain. Expectation: every
  pipeline stage produces an entry, the chain hashes correctly.

  PASS B — Deliberately corrupt one entry's payload_hash in the JSONL,
  re-run verify(), confirm it rejects with the right index. This is what
  the demo at [3:30] would show a parliamentary committee asking *"how do
  we know it's tamper-evident?"*.

Prereq: scripts/seed_neo4j.py has been run. The script reuses the latest
seeded watch's composites; it does NOT run the full sensor fan-out again.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backend.agents.devils_advocate import DevilsAdvocateAgent
from backend.agents.geospatial_agent import GeospatialAgent
from backend.agents.osint_agent import OSINTAgent
from backend.agents.supervisor_agent import SupervisorAgent, run_supervisor_and_assemble
from backend.audit.logger import MerkleAuditLogger, verify_chain
from backend.config import settings
from backend.graph.client import graph_client
from backend.graph.ingestion import ingest_brief
from backend.llm.factory import get_devil_provider, get_provider
from backend.models.audit import AuditEntry

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


async def _run_brief_with_audit(audit_logger: MerkleAuditLogger) -> bool:
    """Run primary agents + devil + supervisor on one composite. Log every step."""
    ce = await _pick_composite()
    watch_id = await _pick_watch_id()
    if ce is None or watch_id is None:
        console.print("[red]Need a seeded watch+composite. Run scripts/seed_neo4j.py first.[/]")
        return False

    provider = get_provider()
    if not await provider.health_check():
        console.print("[red]LLM provider not reachable.[/]")
        return False

    console.print(f"[dim]composite={ce['id'][:8]}, watch={watch_id[:8]}, "
                  f"primary LLM={provider.get_model_name()}[/]")
    console.print()

    await audit_logger.log("smoke.start", "smoke_runner", {"composite": ce["id"]})

    prior_outputs = []
    geo_out = await GeospatialAgent(llm=provider, graph=graph_client).run(
        composite_event_id=ce["id"]
    )
    prior_outputs.append(("geospatial_agent", geo_out))
    await audit_logger.log("agent.geospatial_agent.run", "geospatial_agent", {
        "composite": ce["id"], "confidence": geo_out.confidence,
        "finding_count": len(geo_out.key_findings),
    })

    osint_out = await OSINTAgent(llm=provider, graph=graph_client).run(
        composite_event_id=ce["id"]
    )
    prior_outputs.append(("osint_agent", osint_out))
    await audit_logger.log("agent.osint_agent.run", "osint_agent", {
        "composite": ce["id"], "confidence": osint_out.confidence,
        "finding_count": len(osint_out.key_findings),
    })

    devil_out = await DevilsAdvocateAgent(
        llm=get_devil_provider(), graph=graph_client
    ).run(composite_event_id=ce["id"], prior_outputs=prior_outputs)
    prior_outputs.append(("devils_advocate", devil_out))
    await audit_logger.log("agent.devils_advocate.run", "devils_advocate", {
        "composite": ce["id"],
        "devil_confidence": devil_out.devil_confidence,
        "finding_count": len(devil_out.key_findings),
    })

    brief = await run_supervisor_and_assemble(
        agent=SupervisorAgent(llm=provider, graph=graph_client),
        composite_event_id=ce["id"],
        watch_id=watch_id,
        prior_outputs=prior_outputs,
        sources_count=len(ce.get("source_node_ids") or []),
    )
    await ingest_brief(graph_client, brief)
    await audit_logger.log("brief.ingested", "supervisor_agent", {
        "watch_id": watch_id, "brief_id": brief.id,
        "section_count": len(brief.all_sections()),
    })

    # Simulate a couple of analyst clicks on citations.
    for sec in [brief.bluf, *brief.key_judgments[:2]]:
        await audit_logger.log("brief.citation_accessed", "analyst", {
            "brief_id":     brief.id,
            "section_id":   sec.id,
            "section_type": sec.section_type.value,
            "source_count": len(sec.citation_node_ids),
        })

    await audit_logger.log("smoke.end", "smoke_runner", {"brief": brief.id})
    return True


def _read_jsonl(path: Path) -> list[AuditEntry]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(AuditEntry(**json.loads(line)))
    return out


def _tamper_one_entry(path: Path, idx: int) -> str:
    """Rewrite the payload_hash of the idx'th entry to a fixed value.

    Returns the original payload_hash so the test can reverse the tamper.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[idx])
    original = entry["payload_hash"]
    entry["payload_hash"] = "0" * 64
    lines[idx] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return original


def _restore_entry(path: Path, idx: int, original_hash: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[idx])
    entry["payload_hash"] = original_hash
    lines[idx] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> int:
    audit_log_path: Path = settings.audit_log_path
    # Start fresh so the smoke is reproducible.
    if audit_log_path.exists():
        audit_log_path.unlink()
        console.print(f"[dim]Cleared previous audit log at {audit_log_path}[/]")
    console.print()

    await graph_client.connect()
    try:
        # Use a JSONL-only logger so the tamper test is fully reproducible
        # and doesn't muck with the shared Neo4j AuditEntry chain.
        audit_logger = MerkleAuditLogger(log_file_path=audit_log_path)

        # ─── PASS A — populate the chain ─────────────────────────────────────
        console.print(Panel.fit(
            "Run primary agents + devil + supervisor on the latest AMBER composite.\n"
            "Each pipeline stage logs an entry to the Merkle chain.",
            title="PASS A: populate audit chain", border_style="cyan",
        ))
        ok = await _run_brief_with_audit(audit_logger)
        if not ok:
            return 2

        entries = _read_jsonl(audit_log_path)
        console.print(f"\n[dim]Audit chain has {len(entries)} entries[/]")

        actions = Table(title="Audit chain (action_type x actor x payload_hash[:12])")
        actions.add_column("#", justify="right")
        actions.add_column("action_type")
        actions.add_column("actor")
        actions.add_column("payload_hash[:12]")
        actions.add_column("chain_hash[:12]")
        for i, e in enumerate(entries, 1):
            actions.add_row(
                str(i), e.action_type, e.actor,
                e.payload_hash[:12] + "...",
                e.chain_hash[:12]   + "...",
            )
        console.print(actions)

        ok, idx = verify_chain(entries)
        verdict_color = "green" if ok else "red"
        console.print(Panel(
            f"verify_chain on {len(entries)} entries -> ok={ok} first_bad_idx={idx}",
            title="PASS A verdict", border_style=verdict_color,
        ))
        if not ok:
            console.print("[red]Chain failed to verify even before tamper. Bug in logger.[/]")
            return 3
        console.print()

        # ─── PASS B — deliberate tamper ──────────────────────────────────────
        target_idx = len(entries) // 2   # middle-of-chain tamper
        console.print(Panel.fit(
            f"Deliberately rewriting payload_hash of entry #{target_idx + 1} "
            f"({entries[target_idx].action_type}) to all zeros.\n"
            f"Expectation: verify_chain rejects with first_bad_idx == {target_idx}.",
            title="PASS B: tamper test", border_style="yellow",
        ))
        original_hash = _tamper_one_entry(audit_log_path, target_idx)
        tampered_entries = _read_jsonl(audit_log_path)
        ok2, idx2 = verify_chain(tampered_entries)
        verdict2_color = "green" if (not ok2 and idx2 == target_idx) else "red"
        console.print(Panel(
            f"verify_chain after tamper -> ok={ok2} first_bad_idx={idx2}\n\n"
            f"{'TAMPER DETECTED at the right index' if (not ok2 and idx2 == target_idx) else 'UNEXPECTED — tamper detection failed'}",
            title="PASS B verdict", border_style=verdict2_color,
        ))

        # ─── Restore so the audit log isn't permanently broken ───────────────
        _restore_entry(audit_log_path, target_idx, original_hash)
        restored_entries = _read_jsonl(audit_log_path)
        ok3, _ = verify_chain(restored_entries)
        console.print(f"[dim]Restored entry; chain re-verifies: {ok3}[/]")
        console.print()

        if ok and not ok2 and idx2 == target_idx and ok3:
            console.print("[bold green]Day 13 OK[/] - audit chain is tamper-evident end-to-end.")
            return 0
        else:
            console.print("[red]Day 13 FAILED — see verdicts above.[/]")
            return 4
    finally:
        await graph_client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
