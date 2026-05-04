"""LLM provider factory.

Reads ``LLM_PROVIDER`` from settings and returns the matching concrete provider.
Called once at startup and injected via FastAPI dependency.

Switching from Gemini (dev) to Ollama (demo/prod):
    1. Edit .env: LLM_PROVIDER=ollama
    2. Ensure Ollama is running: `ollama serve`
    3. Ensure model is pulled: `ollama pull llama3.1:8b`
    4. Restart the backend.
Zero code changes required.
"""
from __future__ import annotations

from functools import lru_cache

from backend.config import settings

from .base import LLMProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    """Return the singleton provider for this process."""
    if settings.LLM_PROVIDER == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "LLM_PROVIDER=gemini but GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com and add it to .env."
            )
        return GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)

    if settings.LLM_PROVIDER == "ollama":
        return OllamaProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER!r}")


def get_devil_provider() -> LLMProvider:
    """The Devil's Advocate uses a slightly more creative model (qwen2.5).

    Under Gemini in development this is identical to ``get_provider()`` — the
    differentiation only kicks in when running under Ollama (the demo target).
    """
    if settings.LLM_PROVIDER == "ollama":
        return OllamaProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_DEVIL_MODEL,
        )
    return get_provider()
