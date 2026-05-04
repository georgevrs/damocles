"""LLM provider abstract interface.

This is the most important architectural decision in the codebase.
Every agent calls ``LLMProvider.complete()``. No agent imports Gemini or Ollama.
Switching providers is a single env var change with zero code changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """Provider-agnostic chat message."""
    role: str = Field(description='"system" | "user" | "assistant"')
    content: str


class LLMResponse(BaseModel):
    """Provider-agnostic completion result."""
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class LLMProvider(ABC):
    """Abstract LLM backend.

    Selected at startup via the ``LLM_PROVIDER`` env var. Every agent receives
    a concrete provider via dependency injection — agents never instantiate
    a provider themselves.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Run a chat completion.

        ``json_mode=True`` instructs the provider to constrain output to valid
        JSON. Both Gemini (``response_mime_type="application/json"``) and
        Ollama (``format="json"``) support this natively.
        """

    @abstractmethod
    def get_model_name(self) -> str: ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the provider is reachable and the model is loaded."""
