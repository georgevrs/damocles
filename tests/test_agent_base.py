"""BaseAgent / AgentOutput tests.

We exercise the validation and retry-on-failure paths via a mock LLM
provider so no quota is burned. The mock provider returns a queue of
canned responses, one per ``complete()`` call.
"""
from __future__ import annotations

import json
import time
from typing import Any

import pytest

from backend.agents.base import (
    AgentOutput,
    AgentValidationError,
    BaseAgent,
    validate_agent_output,
)
from backend.llm.base import LLMMessage, LLMProvider, LLMResponse


# ───────────────────────────────────────────────────────────────────────────────
# Mock LLM
# ───────────────────────────────────────────────────────────────────────────────
class MockLLM(LLMProvider):
    """Returns the next queued response per call. Records every call."""

    def __init__(self, responses: list[str]):
        self._queue = list(responses)
        self.calls: list[list[LLMMessage]] = []

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        _ = temperature, max_tokens, json_mode
        self.calls.append(messages)
        if not self._queue:
            raise RuntimeError("MockLLM ran out of queued responses")
        content = self._queue.pop(0)
        return LLMResponse(
            content=content, model="mock", provider="mock",
            input_tokens=10, output_tokens=20, latency_ms=1.0,
        )

    def get_model_name(self) -> str:
        return "mock"

    async def health_check(self) -> bool:
        return True


# A minimal concrete agent — no graph, fixed context.
class _DummyAgent(BaseAgent):
    name = "dummy"

    def __init__(self, llm, valid_ids: list[str]):
        super().__init__(llm=llm, graph=None)  # type: ignore[arg-type]
        self._valid_ids = valid_ids

    def system_prompt(self) -> str:
        return "be a good agent"

    async def fetch_context(self, **kwargs: Any):
        return "fixed context", list(self._valid_ids)


def _good_output(citation_ids: list[str]) -> str:
    return json.dumps({
        "analysis": "Two vessels detected in central Aegean.",
        "key_findings": ["A 50m vessel was detected"],
        "confidence": 0.8,
        "citation_node_ids": citation_ids,
        "uncertainty_flags": ["AIS may have missed transmissions"],
    })


# ───────────────────────────────────────────────────────────────────────────────
# validate_agent_output
# ───────────────────────────────────────────────────────────────────────────────
def test_valid_output_passes():
    out = AgentOutput(**json.loads(_good_output(["v1"])))
    validate_agent_output(out, ["v1", "v2"])   # no raise


def test_orphan_citation_fails():
    out = AgentOutput(**json.loads(_good_output(["GHOST_ID"])))
    with pytest.raises(AgentValidationError, match="unknown graph nodes"):
        validate_agent_output(out, ["v1"])


def test_empty_citations_fails():
    out = AgentOutput(**json.loads(_good_output([])))
    with pytest.raises(AgentValidationError, match="citation_node_ids is empty"):
        validate_agent_output(out, ["v1"])


def test_empty_uncertainty_fails():
    bad = json.loads(_good_output(["v1"]))
    bad["uncertainty_flags"] = []
    out = AgentOutput(**bad)
    with pytest.raises(AgentValidationError, match="uncertainty_flags is empty"):
        validate_agent_output(out, ["v1"])


def test_empty_findings_fails():
    bad = json.loads(_good_output(["v1"]))
    bad["key_findings"] = []
    out = AgentOutput(**bad)
    with pytest.raises(AgentValidationError, match="key_findings is empty"):
        validate_agent_output(out, ["v1"])


# ───────────────────────────────────────────────────────────────────────────────
# BaseAgent.run() — happy path, retry path, fatal path
# ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_run_happy_path_one_call():
    llm = MockLLM([_good_output(["v1"])])
    agent = _DummyAgent(llm, valid_ids=["v1", "v2"])
    out = await agent.run()
    assert out.confidence == 0.8
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_run_retries_once_on_orphan_citation_then_succeeds():
    llm = MockLLM([
        _good_output(["GHOST"]),       # invalid first try
        _good_output(["v1"]),           # corrected
    ])
    agent = _DummyAgent(llm, valid_ids=["v1"])
    out = await agent.run()
    assert out.citation_node_ids == ["v1"]
    assert len(llm.calls) == 2

    # The retry message must include the validation error and the assistant's prior reply
    retry_messages = llm.calls[1]
    role_tags = [m.role for m in retry_messages]
    assert role_tags == ["system", "user", "assistant", "user"]
    assert "GHOST" in retry_messages[2].content   # prior bad output echoed
    assert "validation error" in retry_messages[3].content.lower()


@pytest.mark.asyncio
async def test_run_fails_when_retry_also_invalid():
    llm = MockLLM([
        _good_output(["GHOST"]),
        _good_output(["GHOST_AGAIN"]),
    ])
    agent = _DummyAgent(llm, valid_ids=["v1"])
    with pytest.raises(AgentValidationError, match="unknown graph nodes"):
        await agent.run()


@pytest.mark.asyncio
async def test_run_handles_invalid_json():
    llm = MockLLM([
        "this is not json at all",   # parse failure on first call
        _good_output(["v1"]),         # valid on retry
    ])
    agent = _DummyAgent(llm, valid_ids=["v1"])
    with pytest.raises(AgentValidationError):
        # The first call's JSON parse failure throws AgentValidationError
        # before validation-retry path even fires.
        await agent.run()


@pytest.mark.asyncio
async def test_run_strips_markdown_fences():
    fenced = "```json\n" + _good_output(["v1"]) + "\n```"
    llm = MockLLM([fenced])
    agent = _DummyAgent(llm, valid_ids=["v1"])
    out = await agent.run()   # should not raise — fence-stripping handles it
    assert out.confidence == 0.8


@pytest.mark.parametrize("bad_confidence", [-0.1, 1.5, "high"])
@pytest.mark.asyncio
async def test_run_rejects_out_of_range_confidence(bad_confidence):
    bad = json.loads(_good_output(["v1"]))
    bad["confidence"] = bad_confidence
    llm = MockLLM([json.dumps(bad)])
    agent = _DummyAgent(llm, valid_ids=["v1"])
    with pytest.raises(AgentValidationError):
        await agent.run()


# Latency budget sanity — synthetic LLM should make run() finish in < 50ms
@pytest.mark.asyncio
async def test_run_is_fast_with_mocked_llm():
    llm = MockLLM([_good_output(["v1"])])
    agent = _DummyAgent(llm, valid_ids=["v1"])
    t0 = time.time()
    await agent.run()
    assert (time.time() - t0) < 0.5
