"""Smoke test for the LLM provider abstraction.

Runs against whatever provider is configured by LLM_PROVIDER.
Skipped automatically when neither provider is reachable.
"""
from __future__ import annotations

import pytest

from backend.llm.base import LLMMessage
from backend.llm.factory import get_provider


@pytest.mark.asyncio
async def test_provider_responds():
    try:
        provider = get_provider()
    except ValueError as exc:
        pytest.skip(f"No LLM provider configured: {exc}")

    if not await provider.health_check():
        pytest.skip(f"{provider.__class__.__name__} not reachable")

    response = await provider.complete(
        [LLMMessage(role="user", content="Reply with just the word: OK")],
        max_tokens=8,
    )
    assert "OK" in response.content.upper()
    assert response.provider in {"gemini", "ollama"}
    assert response.latency_ms > 0
