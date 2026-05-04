"""LLM provider abstraction — the single boundary between agents and any LLM.

Agents call ``LLMProvider.complete()``. They never import Gemini or Ollama.
The concrete provider is chosen by ``LLM_PROVIDER`` env var via ``factory.get_provider()``.
"""
from .base import LLMMessage, LLMProvider, LLMResponse
from .factory import get_provider

__all__ = ["LLMMessage", "LLMProvider", "LLMResponse", "get_provider"]
