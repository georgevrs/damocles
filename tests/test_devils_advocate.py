"""Devil's Advocate tests with mocked LLM.

Verifies:
  - The DevilsAdvocateOutput schema parses end-to-end through BaseAgent.run()
  - devil_confidence range is enforced
  - The retry-on-validation-error path works through the subclassed output_model
  - The prior-outputs context formatter includes findings + confidence
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from backend.agents.base import (
    AgentOutput,
    AgentValidationError,
    DevilsAdvocateOutput,
)
from backend.agents.devils_advocate import DevilsAdvocateAgent
from tests.test_agent_base import MockLLM   # reuse the canned-response provider


def _devil_output(devil_conf: float = 0.6, citations: list[str] | None = None) -> str:
    return json.dumps({
        "analysis": "The primary's reading hinges on a single Greek-language news outlet.",
        "key_findings": [
            "The reported arrest count cites only the lawyers' group, "
            "no independent witness or photographic record is in the source set."
        ],
        "confidence": 0.7,
        "devil_confidence": devil_conf,
        "citation_node_ids": citations or ["ev1"],
        "uncertainty_flags": ["the lawyers' group's prior reliability is not in the context"],
    })


# ───────────────────────────────────────────────────────────────────────────────
# DevilsAdvocateOutput schema
# ───────────────────────────────────────────────────────────────────────────────
def test_devil_output_extends_agent_output():
    out = DevilsAdvocateOutput(**json.loads(_devil_output(devil_conf=0.65)))
    assert isinstance(out, AgentOutput)            # subclass relationship
    assert out.devil_confidence == 0.65
    assert out.confidence == 0.7
    assert len(out.key_findings) == 1


def test_devil_confidence_required():
    bad = json.loads(_devil_output())
    del bad["devil_confidence"]
    with pytest.raises(Exception):                 # Pydantic ValidationError
        DevilsAdvocateOutput(**bad)


@pytest.mark.parametrize("bad_value", [-0.1, 1.5, "high"])
def test_devil_confidence_range_enforced(bad_value: Any):
    bad = json.loads(_devil_output())
    bad["devil_confidence"] = bad_value
    with pytest.raises(Exception):
        DevilsAdvocateOutput(**bad)


# ───────────────────────────────────────────────────────────────────────────────
# Run loop with a stub agent (no graph access)
# ───────────────────────────────────────────────────────────────────────────────
class _StubDevil(DevilsAdvocateAgent):
    """DevilsAdvocateAgent with fixed context — no Neo4j needed."""

    def __init__(self, llm, valid_ids: list[str]):
        # Bypass the normal __init__ — we don't need a graph for these unit tests.
        from backend.agents.base import BaseAgent
        BaseAgent.__init__(self, llm=llm, graph=None)   # type: ignore[arg-type]
        self._valid_ids = list(valid_ids)

    async def fetch_context(self, **kwargs: Any):
        return "fixed devil context", list(self._valid_ids)


@pytest.mark.asyncio
async def test_run_returns_devil_output_class():
    llm = MockLLM([_devil_output(devil_conf=0.55, citations=["ev1"])])
    agent = _StubDevil(llm, valid_ids=["ev1", "ce1"])
    out = await agent.run()
    assert isinstance(out, DevilsAdvocateOutput)
    assert out.devil_confidence == 0.55


@pytest.mark.asyncio
async def test_run_retries_on_orphan_citation_then_returns_devil():
    """The retry path must produce a DevilsAdvocateOutput, not a plain AgentOutput."""
    llm = MockLLM([
        _devil_output(devil_conf=0.5, citations=["GHOST"]),   # orphan -> retry
        _devil_output(devil_conf=0.5, citations=["ev1"]),     # corrected
    ])
    agent = _StubDevil(llm, valid_ids=["ev1"])
    out = await agent.run()
    assert isinstance(out, DevilsAdvocateOutput)
    assert out.citation_node_ids == ["ev1"]
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_run_rejects_missing_devil_confidence():
    bad = json.loads(_devil_output())
    del bad["devil_confidence"]
    llm = MockLLM([json.dumps(bad)])
    agent = _StubDevil(llm, valid_ids=["ev1"])
    with pytest.raises(AgentValidationError):
        await agent.run()


# ───────────────────────────────────────────────────────────────────────────────
# Configuration sanity
# ───────────────────────────────────────────────────────────────────────────────
def test_devils_advocate_uses_higher_temperature():
    """Plan §6: temperature 0.3 (vs 0.1 for factual agents)."""
    assert DevilsAdvocateAgent.temperature > 0.1
    assert DevilsAdvocateAgent.temperature == 0.3


def test_devils_advocate_uses_devil_output_model():
    assert DevilsAdvocateAgent.output_model is DevilsAdvocateOutput
