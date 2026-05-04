"""SupervisorAgent — assembles the final intelligence brief.

Differs from the other agents in two ways:

1. **Its output schema is `SupervisorOutput`**, not `AgentOutput`. The brief
   has nested text-bearing blocks (BLUF, key_judgments, supporting_evidence,
   devils_advocate, recommended_action) — each with its own citations and
   confidence. AgentOutput's flat `key_findings + citation_node_ids` shape
   doesn't fit.

2. **It validates citations across all sections**, not just one flat list.
   Every text-bearing block must reference at least one node ID present in
   the context. ``BaseAgent.validate_agent_output`` doesn't fit either, so
   we override ``run()`` to apply nested validation.

After a successful run, ``assemble_brief()`` converts the parsed
`SupervisorOutput` into a canonical `Brief` Pydantic with watch_id,
brief_id, BriefSection IDs, and ``agents_consulted`` metadata.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Iterable

from backend.agents.base import (
    AgentOutput,
    AgentValidationError,
    BaseAgent,
    DevilsAdvocateOutput,
)
from backend.graph.client import Neo4jClient
from backend.llm.base import LLMProvider
from backend.models.brief import (
    Brief,
    BriefSection,
    SectionType,
    SupervisorBriefSection,
    SupervisorDevilsAdvocate,
    SupervisorOutput,
    SupervisorRecommendation,
    Urgency,
)

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "supervisor.txt"


class SupervisorAgent(BaseAgent):
    name = "supervisor_agent"
    # 0.0 — pure synthesis, no creativity needed (per the plan).
    temperature = 0.0
    max_tokens = 4096
    output_model = SupervisorOutput   # type: ignore[assignment]

    def __init__(self, llm: LLMProvider, graph: Neo4jClient):
        super().__init__(llm=llm, graph=graph)

    def system_prompt(self) -> str:
        return _PROMPT_PATH.read_text(encoding="utf-8")

    # ─── Context assembly ────────────────────────────────────────────────────
    async def fetch_context(
        self,
        composite_event_id: str,
        prior_outputs: list[tuple[str, AgentOutput]] | None = None,
        aoi_id: str | None = None,
        **_kwargs,
    ) -> tuple[str, list[str]]:
        """Pull the composite + sources, fold prior agents' outputs into prompt.

        When ``aoi_id`` is provided, the AoI is loaded from the DuckDB store and
        added to the valid citation IDs. The supervisor prompt then mandates
        the AoI as the first BLUF citation so the frontend can link the BLUF
        directly to the polygon on the map (see prompts/supervisor.txt).
        """
        rows = await self.graph.run(
            """
            MATCH (ce:CompositeEvent {id: $id})
            OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(source)
            RETURN ce, collect({type: labels(source)[0], props: source}) AS sources
            """,
            id=composite_event_id,
        )
        if not rows or not rows[0].get("ce"):
            raise ValueError(f"CompositeEvent {composite_event_id!r} not found")

        ce = rows[0]["ce"]
        sources_raw = [s for s in (rows[0]["sources"] or []) if s and s.get("type")]

        valid_ids: list[str] = [ce["id"]]
        sources_compact: list[dict] = []
        for s in sources_raw:
            t = s["type"]
            p = dict(s["props"])
            sid = p.get("id")
            if sid:
                valid_ids.append(sid)
            sources_compact.append({"type": t, **self._compact(t, p)})

        ce_compact = {
            "id":           ce["id"],
            "threat_grade": ce.get("threat_grade"),
            "summary":      ce.get("summary"),
            "confidence":   ce.get("confidence"),
            "centroid":     [ce.get("centroid_lat"), ce.get("centroid_lon")],
        }

        # Optional AoI scope: when present, add to valid IDs and prompt context
        aoi_block = ""
        if aoi_id:
            try:
                from backend.store import get_store
                aoi = get_store().get_aoi(aoi_id)
            except Exception as exc:
                log.warning("supervisor: AoI lookup failed for %s: %s", aoi_id, exc)
                aoi = None
            if aoi is not None:
                valid_ids.insert(0, aoi.id)
                aoi_compact = {
                    "aoi_id":         aoi.id,
                    "name_el":        aoi.name_el,
                    "name_en":        aoi.name_en,
                    "threat_grade":   aoi.threat_grade,
                    "threat_summary": aoi.threat_summary,
                    "centroid":       [aoi.centroid_lat, aoi.centroid_lon],
                    "event_count":    len(aoi.citation_event_ids or []),
                }
                aoi_block = (
                    f"Area of Interest under analysis (this brief is scoped to it):\n"
                    f"  {json.dumps(aoi_compact, default=str, ensure_ascii=False)}\n\n"
                )

        prior_section = "Prior agent outputs:\n"
        if not prior_outputs:
            prior_section += "  (no prior outputs supplied)\n"
        else:
            for agent_name, out in prior_outputs:
                prior_section += f"- agent: {agent_name}\n"
                prior_section += f"  confidence: {out.confidence}\n"
                if isinstance(out, DevilsAdvocateOutput):
                    prior_section += f"  devil_confidence: {out.devil_confidence}\n"
                prior_section += f"  analysis: {out.analysis}\n"
                prior_section += "  findings:\n"
                for i, f in enumerate(out.key_findings, 1):
                    prior_section += f"    {i}. {f}\n"
                prior_section += f"  uncertainties: {out.uncertainty_flags}\n"

        ctx = (
            f"Valid citation_node_ids you may reference (and only these):\n"
            f"  {valid_ids}\n\n"
            f"{aoi_block}"
            f"CompositeEvent under analysis:\n"
            f"  {json.dumps(ce_compact, default=str)}\n\n"
            f"Source nodes ({len(sources_compact)}):\n"
            f"  {json.dumps(sources_compact, default=str, ensure_ascii=False)}\n\n"
            f"{prior_section}\n"
            f"Produce your structured SupervisorOutput now."
        )
        return ctx, valid_ids

    @staticmethod
    def _compact(node_type: str, p: dict) -> dict:
        if node_type == "Vessel":
            return {
                "id": p.get("id"),
                "lat": p.get("lat"), "lon": p.get("lon"),
                "ais_status": p.get("ais_status"),
                "mmsi": p.get("mmsi"),
                "length_m": p.get("length_m"),
                "dark_score": p.get("dark_vessel_score"),
            }
        if node_type == "NewsEvent":
            return {
                "id": p.get("id"),
                "headline": (p.get("headline") or "")[:120],
                "source": p.get("source_name"),
                "goldstein": p.get("goldstein_scale"),
                "mentions": p.get("mentions"),
            }
        if node_type == "SocialSignal":
            return {
                "id": p.get("id"),
                "channel": p.get("channel"),
                "text": (p.get("text") or "")[:200],
                "language": p.get("language"),
            }
        return {"id": p.get("id")}

    # ─── Run loop with nested-citation validation ────────────────────────────
    async def run(self, **kwargs) -> SupervisorOutput:   # type: ignore[override]
        context_text, valid_ids = await self.fetch_context(**kwargs)
        aoi_id = kwargs.get("aoi_id")

        first = await self._call_llm(context_text)
        first_error: str | None = None
        try:
            self._validate_supervisor_output(first, valid_ids, aoi_id=aoi_id)   # type: ignore[arg-type]
            return first   # type: ignore[return-value]
        except AgentValidationError as exc:
            first_error = str(exc)
            log.warning("%s: invalid output, retrying once: %s", self.name, first_error)

        retried = await self._call_llm_with_correction(context_text, first, first_error)
        try:
            self._validate_supervisor_output(retried, valid_ids, aoi_id=aoi_id)   # type: ignore[arg-type]
        except AgentValidationError as exc:
            # Soft-recover: if the only failure is the aoi_id-first rule, prepend it
            # to the BLUF citations server-side rather than failing the whole brief.
            if aoi_id and "aoi_id" in str(exc).lower():
                bluf_cites = list(retried.bluf.citation_node_ids)
                if aoi_id in bluf_cites:
                    bluf_cites.remove(aoi_id)
                retried.bluf.citation_node_ids = [aoi_id, *bluf_cites]
                self._validate_supervisor_output(retried, valid_ids, aoi_id=aoi_id)
            else:
                raise
        return retried   # type: ignore[return-value]

    @staticmethod
    def _validate_supervisor_output(
        out: SupervisorOutput,
        valid_node_ids: Iterable[str],
        *,
        aoi_id: str | None = None,
    ) -> None:
        """Every text-bearing block must cite at least one valid node ID.

        When ``aoi_id`` is provided, additionally enforces the rule documented
        in prompts/supervisor.txt §"AOI-SCOPED BRIEFS": the first BLUF
        citation MUST be the AoI id so the frontend can link the BLUF to
        the polygon on the map.
        """
        valid = set(valid_node_ids)

        if aoi_id is not None:
            if not out.bluf.citation_node_ids or out.bluf.citation_node_ids[0] != aoi_id:
                raise AgentValidationError(
                    f"BLUF first citation must be aoi_id {aoi_id!r} when brief is "
                    f"AoI-scoped. Got: {list(out.bluf.citation_node_ids)[:3]}."
                )

        all_blocks: list[tuple[str, list[str]]] = [
            ("bluf", out.bluf.citation_node_ids),
        ]
        for i, kj in enumerate(out.key_judgments):
            all_blocks.append((f"key_judgments[{i}]", kj.citation_node_ids))
        for i, se in enumerate(out.supporting_evidence):
            all_blocks.append((f"supporting_evidence[{i}]", se.citation_node_ids))
        if out.devils_advocate is not None:
            all_blocks.append(("devils_advocate", out.devils_advocate.citation_node_ids))
        if out.recommended_action is not None:
            all_blocks.append(("recommended_action", out.recommended_action.citation_node_ids))

        for path, citations in all_blocks:
            if not citations:
                raise AgentValidationError(
                    f"section {path!r} has no citation_node_ids. Every text-bearing "
                    f"block must cite at least one node ID."
                )
            unknown = [nid for nid in citations if nid not in valid]
            if unknown:
                raise AgentValidationError(
                    f"section {path!r} cites unknown node IDs: {unknown[:3]}"
                    f"{'…' if len(unknown) > 3 else ''}. "
                    f"Valid IDs: {list(valid)[:5]}{'…' if len(valid) > 5 else ''}"
                )

        if not out.key_judgments:
            raise AgentValidationError("key_judgments is empty.")

    # ─── Brief assembly ──────────────────────────────────────────────────────
    @staticmethod
    def assemble_brief(
        sup: SupervisorOutput,
        *,
        watch_id: str,
        agents_consulted: list[str],
        processing_duration_seconds: float,
        sources_count: int,
    ) -> Brief:
        """Convert the LLM-shaped SupervisorOutput into a canonical Brief."""
        bluf = _to_section(sup.bluf, SectionType.BLUF, default_agent="fused")

        key_judgments = [
            _to_section(s, SectionType.KEY_JUDGMENT, default_agent="fused")
            for s in sup.key_judgments
        ]
        supporting = [
            _to_section(s, SectionType.SUPPORTING, default_agent="fused")
            for s in sup.supporting_evidence
        ]

        devil_section: BriefSection | None = None
        if sup.devils_advocate is not None:
            devil_section = BriefSection(
                section_type=SectionType.DEVILS_ADVOCATE,
                text=sup.devils_advocate.text,
                citation_node_ids=list(sup.devils_advocate.citation_node_ids),
                confidence=sup.devils_advocate.devil_confidence,
                agent_source="devils_advocate",
                extra={"devil_confidence": sup.devils_advocate.devil_confidence},
            )

        recommendation_section: BriefSection | None = None
        if sup.recommended_action is not None:
            recommendation_section = BriefSection(
                section_type=SectionType.RECOMMENDATION,
                text=sup.recommended_action.text,
                citation_node_ids=list(sup.recommended_action.citation_node_ids),
                confidence=1.0,
                agent_source="supervisor",
                extra={"urgency": sup.recommended_action.urgency.value
                       if isinstance(sup.recommended_action.urgency, Urgency)
                       else str(sup.recommended_action.urgency)},
            )

        return Brief(
            watch_id=watch_id,
            bluf=bluf,
            key_judgments=key_judgments,
            supporting_evidence=supporting,
            devils_advocate=devil_section,
            recommendation=recommendation_section,
            metadata={
                "agents_consulted":            list(agents_consulted),
                "processing_duration_seconds": processing_duration_seconds,
                "sources_count":               sources_count,
                "supervisor_metadata":         dict(sup.metadata or {}),
            },
        )


def _to_section(
    s: SupervisorBriefSection,
    section_type: SectionType,
    *,
    default_agent: str,
) -> BriefSection:
    return BriefSection(
        section_type=section_type,
        text=s.text,
        citation_node_ids=list(s.citation_node_ids),
        confidence=s.confidence,
        agent_source=s.agent_source or default_agent,
    )


# Convenience wrapper that runs the agent and returns a fully assembled Brief.
async def run_supervisor_and_assemble(
    *,
    agent: SupervisorAgent,
    composite_event_id: str,
    watch_id: str,
    prior_outputs: list[tuple[str, AgentOutput]],
    sources_count: int = 0,
    aoi_id: str | None = None,
) -> Brief:
    t0 = time.time()
    sup_out = await agent.run(
        composite_event_id=composite_event_id,
        prior_outputs=prior_outputs,
        aoi_id=aoi_id,
    )
    return agent.assemble_brief(
        sup_out,
        watch_id=watch_id,
        agents_consulted=[name for name, _ in prior_outputs] + ["supervisor"],
        processing_duration_seconds=round(time.time() - t0, 3),
        sources_count=sources_count,
    )
