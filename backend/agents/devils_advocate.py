"""Devil's Advocate Agent — adversarial counter-assessment.

Receives the primary agents' outputs (Geospatial / OSINT / Linguist) plus
the underlying CompositeEvent and produces the strongest counter-case the
data supports. Higher temperature (0.3) than the factual agents (0.1) to
allow creative counter-arguments.

The output is ``DevilsAdvocateOutput`` which extends ``AgentOutput`` with a
``devil_confidence`` field — the probability the primary assessment is
wrong. The frontend renders this as a separate counter-signal so the
analyst can see when the agent layer is internally divided.

When ``LLM_PROVIDER=ollama`` the factory routes the devil through a
slightly more creative model (qwen2.5:7b) per the plan. On Gemini the same
chain is used.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.graph.client import Neo4jClient
from backend.llm.base import LLMProvider

from .base import AgentOutput, BaseAgent, DevilsAdvocateOutput

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "devils_advocate.txt"


class DevilsAdvocateAgent(BaseAgent):
    name = "devils_advocate"
    # Higher temperature than factual agents so the model explores creative
    # counter-arguments rather than echoing the primary's framing.
    temperature = 0.3
    max_tokens = 2048
    output_model = DevilsAdvocateOutput

    def __init__(self, llm: LLMProvider, graph: Neo4jClient):
        super().__init__(llm=llm, graph=graph)

    def system_prompt(self) -> str:
        return _PROMPT_PATH.read_text(encoding="utf-8")

    async def fetch_context(
        self,
        composite_event_id: str,
        prior_outputs: list[tuple[str, AgentOutput]] | None = None,
        **_kwargs: Any,
    ) -> tuple[str, list[str]]:
        """Pull the composite + sources, format prior agent outputs into the prompt.

        ``prior_outputs`` is a list of ``(agent_name, AgentOutput)`` pairs.
        The devil cites IDs from the composite + sources; the prior outputs
        are evidence in the prompt, not citation targets themselves.
        """
        # Neo4j first → DuckDB fallback (shared helper) so the demo doesn't
        # require docker.
        from ._context import fetch_ce_with_sources
        ce, sources_raw = await fetch_ce_with_sources(self.graph, composite_event_id)

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

        prior_section = "Primary agent outputs to challenge:\n"
        if not prior_outputs:
            prior_section += "  (no prior outputs supplied — produce a counter-case from the source nodes alone)\n"
        else:
            for agent_name, out in prior_outputs:
                prior_section += (
                    f"- agent: {agent_name}\n"
                    f"  confidence: {out.confidence}\n"
                    f"  analysis: {out.analysis}\n"
                    f"  findings:\n"
                )
                for i, f in enumerate(out.key_findings, 1):
                    prior_section += f"    {i}. {f}\n"
                prior_section += f"  uncertainties: {out.uncertainty_flags}\n"

        ctx = (
            f"Valid citation_node_ids you may reference (and only these):\n"
            f"  {valid_ids}\n\n"
            f"CompositeEvent under analysis:\n"
            f"  {json.dumps(ce_compact, default=str)}\n\n"
            f"Source nodes ({len(sources_compact)}):\n"
            f"  {json.dumps(sources_compact, default=str, ensure_ascii=False)}\n\n"
            f"{prior_section}\n"
            f"Produce your structured DevilsAdvocateOutput now."
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
                "confidence": p.get("confidence"),
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
                "views": p.get("views"),
            }
        return {"id": p.get("id")}
