"""SupervisorAgent unit tests with a mocked LLM.

Verifies:
  - SupervisorOutput parses end-to-end
  - Nested-citation validation rejects empty / orphan citations PER SECTION
  - Retry path produces a valid SupervisorOutput
  - assemble_brief() produces a canonical Brief with the right section types
  - run_supervisor_and_assemble() bundles run + assembly correctly
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from backend.agents.base import AgentOutput, AgentValidationError
from backend.agents.supervisor_agent import (
    SupervisorAgent,
    run_supervisor_and_assemble,
)
from backend.models.brief import (
    Brief,
    SectionType,
    SupervisorBriefSection,
    SupervisorDevilsAdvocate,
    SupervisorOutput,
    SupervisorRecommendation,
    Urgency,
)
from tests.test_agent_base import MockLLM


# ───────────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────────
def _good_supervisor_output(citations: list[str] | None = None) -> str:
    cits = citations or ["ev1"]
    return json.dumps({
        "bluf": {
            "text": "AMBER alert: rare May Day arrests at Bosporus.",
            "citation_node_ids": cits,
            "confidence": 0.7,
            "agent_source": "fused",
        },
        "key_judgments": [
            {
                "text": "Reports indicate at least 370 arrests during May 1 demonstrations.",
                "citation_node_ids": cits,
                "confidence": 0.7,
                "agent_source": "osint",
            }
        ],
        "supporting_evidence": [
            {
                "text": "Goldstein -6.5 from a single Lebanese-press source.",
                "citation_node_ids": cits,
                "confidence": 0.6,
                "agent_source": "osint",
            }
        ],
        "devils_advocate": {
            "text": "Civil unrest is not a maritime threat indicator absent vessel telemetry.",
            "devil_confidence": 0.7,
            "citation_node_ids": cits,
        },
        "recommended_action": {
            "text": "File in routine intel digest pending corroborating naval signals.",
            "urgency": "ROUTINE",
            "citation_node_ids": cits,
        },
        "metadata": {"agents_consulted": ["geospatial", "osint", "devils_advocate"]},
    })


class _StubSupervisor(SupervisorAgent):
    """Bypass Neo4j fetch_context — use fixed valid IDs."""

    def __init__(self, llm, valid_ids: list[str]):
        from backend.agents.base import BaseAgent
        BaseAgent.__init__(self, llm=llm, graph=None)   # type: ignore[arg-type]
        self._valid_ids = list(valid_ids)

    async def fetch_context(self, **_kwargs: Any):
        return "fixed supervisor context", list(self._valid_ids)


# ───────────────────────────────────────────────────────────────────────────────
# Schema
# ───────────────────────────────────────────────────────────────────────────────
def test_supervisor_output_parses():
    out = SupervisorOutput(**json.loads(_good_supervisor_output()))
    assert out.bluf.text.startswith("AMBER")
    assert len(out.key_judgments) == 1
    assert out.devils_advocate is not None
    assert out.recommended_action is not None
    assert out.recommended_action.urgency == Urgency.ROUTINE


def test_all_text_bearing_sections_collects_every_block():
    out = SupervisorOutput(**json.loads(_good_supervisor_output()))
    blocks = out.all_text_bearing_sections()
    # bluf + 1 judgment + 1 supporting + devil + recommendation = 5
    assert len(blocks) == 5


def test_supervisor_output_optional_blocks():
    raw = json.loads(_good_supervisor_output())
    raw["devils_advocate"] = None
    raw["recommended_action"] = None
    out = SupervisorOutput(**raw)
    assert out.devils_advocate is None
    assert out.recommended_action is None
    assert len(out.all_text_bearing_sections()) == 3


# ───────────────────────────────────────────────────────────────────────────────
# Nested citation validation (the headline supervisor-specific rule)
# ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_run_happy_path():
    llm = MockLLM([_good_supervisor_output(citations=["ev1"])])
    agent = _StubSupervisor(llm, valid_ids=["ev1", "ce1"])
    out = await agent.run()
    assert isinstance(out, SupervisorOutput)
    assert out.bluf.confidence == 0.7
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_run_rejects_empty_bluf_citations():
    raw = json.loads(_good_supervisor_output())
    raw["bluf"]["citation_node_ids"] = []
    llm = MockLLM([json.dumps(raw), _good_supervisor_output(citations=["ev1"])])
    agent = _StubSupervisor(llm, valid_ids=["ev1"])
    out = await agent.run()
    # First call rejected, retry succeeded
    assert isinstance(out, SupervisorOutput)
    assert len(llm.calls) == 2
    assert "bluf" in llm.calls[1][-1].content


@pytest.mark.asyncio
async def test_run_rejects_orphan_judgment_citation():
    raw = json.loads(_good_supervisor_output())
    raw["key_judgments"][0]["citation_node_ids"] = ["GHOST_ID"]
    llm = MockLLM([json.dumps(raw), json.dumps(raw)])
    agent = _StubSupervisor(llm, valid_ids=["ev1"])
    with pytest.raises(AgentValidationError, match="key_judgments"):
        await agent.run()


@pytest.mark.asyncio
async def test_run_rejects_orphan_devil_citation():
    raw = json.loads(_good_supervisor_output())
    raw["devils_advocate"]["citation_node_ids"] = ["GHOST_ID"]
    llm = MockLLM([json.dumps(raw), json.dumps(raw)])
    agent = _StubSupervisor(llm, valid_ids=["ev1"])
    with pytest.raises(AgentValidationError, match="devils_advocate"):
        await agent.run()


@pytest.mark.asyncio
async def test_run_rejects_empty_key_judgments():
    raw = json.loads(_good_supervisor_output())
    raw["key_judgments"] = []
    llm = MockLLM([json.dumps(raw), json.dumps(raw)])
    agent = _StubSupervisor(llm, valid_ids=["ev1"])
    with pytest.raises(AgentValidationError, match="key_judgments is empty"):
        await agent.run()


# ───────────────────────────────────────────────────────────────────────────────
# Brief assembly
# ───────────────────────────────────────────────────────────────────────────────
def test_assemble_brief_produces_canonical_brief():
    sup = SupervisorOutput(**json.loads(_good_supervisor_output()))
    brief = SupervisorAgent.assemble_brief(
        sup,
        watch_id="watch-123",
        agents_consulted=["geospatial", "osint", "devils_advocate", "supervisor"],
        processing_duration_seconds=2.5,
        sources_count=4,
    )
    assert isinstance(brief, Brief)
    assert brief.watch_id == "watch-123"
    assert brief.bluf.section_type == SectionType.BLUF
    assert len(brief.key_judgments) == 1
    assert brief.key_judgments[0].section_type == SectionType.KEY_JUDGMENT
    assert brief.devils_advocate is not None
    assert brief.devils_advocate.section_type == SectionType.DEVILS_ADVOCATE
    assert brief.devils_advocate.extra["devil_confidence"] == 0.7
    assert brief.recommendation is not None
    assert brief.recommendation.section_type == SectionType.RECOMMENDATION
    assert brief.recommendation.extra["urgency"] == "ROUTINE"
    assert brief.metadata["sources_count"] == 4
    assert "supervisor" in brief.metadata["agents_consulted"]


def test_assemble_brief_handles_missing_optional_blocks():
    raw = json.loads(_good_supervisor_output())
    raw["devils_advocate"] = None
    raw["recommended_action"] = None
    sup = SupervisorOutput(**raw)
    brief = SupervisorAgent.assemble_brief(
        sup,
        watch_id="w",
        agents_consulted=[],
        processing_duration_seconds=0.0,
        sources_count=0,
    )
    assert brief.devils_advocate is None
    assert brief.recommendation is None


# ───────────────────────────────────────────────────────────────────────────────
# run_supervisor_and_assemble convenience wrapper
# ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_run_supervisor_and_assemble_returns_brief():
    llm = MockLLM([_good_supervisor_output(citations=["ev1"])])
    agent = _StubSupervisor(llm, valid_ids=["ev1"])

    # Synthesize a couple of "prior outputs" to thread through.
    geo_out = AgentOutput(
        analysis="Vessel analysis", key_findings=["a finding"],
        confidence=0.8, citation_node_ids=["ev1"],
        uncertainty_flags=["partial AIS coverage"],
    )

    brief = await run_supervisor_and_assemble(
        agent=agent,
        composite_event_id="ce1",
        watch_id="w1",
        prior_outputs=[("geospatial_agent", geo_out)],
        sources_count=1,
    )
    assert isinstance(brief, Brief)
    assert brief.watch_id == "w1"
    assert "geospatial_agent" in brief.metadata["agents_consulted"]
    assert "supervisor" in brief.metadata["agents_consulted"]


# ───────────────────────────────────────────────────────────────────────────────
# Configuration sanity
# ───────────────────────────────────────────────────────────────────────────────
def test_supervisor_uses_zero_temperature():
    """Plan §6.5: supervisor uses 0.0 (pure synthesis, no creativity)."""
    assert SupervisorAgent.temperature == 0.0


def test_supervisor_uses_supervisor_output_model():
    assert SupervisorAgent.output_model is SupervisorOutput
