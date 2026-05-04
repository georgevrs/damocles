"""Google Gemini provider — used during development.

Uses the new ``google-genai`` SDK (Gemini 3-aware). The old
``google-generativeai`` 0.8.x SDK doesn't expose ``thinking_config`` at all,
which made Gemini 2.5/3 outputs flaky — the model spent a non-deterministic
share of the output budget on internal "thinking" tokens, sometimes leaving
only 70 visible tokens for a JSON answer that needed 600. The new SDK lets
us pin ``thinking_level="minimal"`` so output budgeting is predictable.

Sovereignty note: Gemini is ONLY used during local development on the
Windows dev machine. The demo and production deployment run Ollama locally
with no external API calls — selected by the same ``LLM_PROVIDER`` env var.

Fallback chain
--------------
``GEMINI_MODEL`` may be a single model name or a comma-separated chain like
``"gemini-3-flash-preview,gemini-2.5-flash,gemini-2.0-flash"``. The provider
tries each in order. On a daily-quota error it marks the model exhausted for
the rest of the process; on a per-minute rate limit it just hops to the next
model momentarily. Once every model in the chain is exhausted we raise.
"""
from __future__ import annotations

import asyncio
import logging
import time

from google import genai
from google.genai import types as genai_types

from .base import LLMMessage, LLMProvider, LLMResponse

log = logging.getLogger(__name__)


def _is_quota_error(exc: Exception) -> bool:
    """Any 429-class quota / rate-limit response (per-minute OR per-day)."""
    msg = str(exc)
    return "429" in msg or "ResourceExhausted" in msg or "RESOURCE_EXHAUSTED" in msg


def _is_daily_quota_error(exc: Exception) -> bool:
    """Per-day quota only — these stay exhausted until Pacific midnight."""
    msg = str(exc)
    return ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and "PerDay" in msg


def _is_thinking_capable(model: str) -> bool:
    """Gemini 2.5+ and 3 family use thinking budgets. 2.0 family does not."""
    return "2.5" in model or "-3-" in model or "/3-" in model or model.startswith("gemini-3")


class GeminiProvider(LLMProvider):
    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: str, model: str | None = None):
        if not api_key:
            raise ValueError("GeminiProvider requires a non-empty api_key")
        self._client = genai.Client(api_key=api_key)
        chain_raw = model or self.DEFAULT_MODEL
        self._chain: list[str] = [m.strip() for m in chain_raw.split(",") if m.strip()]
        self._exhausted: set[str] = set()

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        start = time.time()
        system_instruction, contents = self._normalize_messages(messages)

        last_exc: Exception | None = None
        for model_name in self._chain:
            if model_name in self._exhausted:
                continue
            try:
                content, in_tokens, out_tokens = await self._call_one(
                    model_name=model_name,
                    system_instruction=system_instruction,
                    contents=contents,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
                return LLMResponse(
                    content=content,
                    model=model_name,
                    provider="gemini",
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    latency_ms=(time.time() - start) * 1000.0,
                )
            except Exception as exc:
                last_exc = exc
                if _is_daily_quota_error(exc):
                    log.warning("Gemini model %s daily quota exhausted; skipping for this process", model_name)
                    self._exhausted.add(model_name)
                    continue
                if _is_quota_error(exc):
                    log.info("Gemini model %s hit a transient rate limit; trying next in chain", model_name)
                    continue
                # Non-quota errors abort immediately — don't burn the chain on a bug.
                raise

        raise RuntimeError(
            f"All Gemini models in the fallback chain are quota-exhausted: {self._chain}. "
            f"Wait for daily reset (Pacific midnight) or add a model with headroom to GEMINI_MODEL."
        ) from last_exc

    @staticmethod
    def _normalize_messages(messages: list[LLMMessage]) -> tuple[str | None, list[dict]]:
        """Map provider-agnostic LLMMessage list onto Gemini's structure.

        Gemini takes ``system_instruction`` separately and ``contents`` as a
        list of ``{role, parts}`` records. Roles in ``contents`` are
        ``"user"`` or ``"model"`` (assistant -> model).
        """
        system_instruction: str | None = None
        contents: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                system_instruction = (
                    msg.content if system_instruction is None
                    else f"{system_instruction}\n\n{msg.content}"
                )
            elif msg.role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg.content}]})

        if not contents or contents[-1]["role"] != "user":
            raise ValueError("GeminiProvider.complete() requires the last message to be from role=user")
        return system_instruction, contents

    async def _call_one(
        self,
        *,
        model_name: str,
        system_instruction: str | None,
        contents: list[dict],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> tuple[str, int, int]:
        config_kwargs: dict = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        if _is_thinking_capable(model_name):
            # "minimal" is the documented Gemini 3 default; pinning it explicitly
            # makes output token budgeting predictable across runs.
            config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_level="minimal")

        config = genai_types.GenerateContentConfig(**config_kwargs)

        # The new SDK exposes an async client at .aio
        response = await self._client.aio.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )

        text = (response.text or "")
        if not text and response.candidates:
            # Fallback: pull text from parts manually if .text accessor is empty.
            cand = response.candidates[0]
            if cand and cand.content and cand.content.parts:
                text = "".join(p.text for p in cand.content.parts if getattr(p, "text", None))

        usage = getattr(response, "usage_metadata", None)
        in_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        out_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        return text, in_tokens, out_tokens

    def get_model_name(self) -> str:
        for m in self._chain:
            if m not in self._exhausted:
                return m
        return self._chain[0] if self._chain else self.DEFAULT_MODEL

    async def health_check(self) -> bool:
        try:
            r = await self.complete(
                [LLMMessage(role="user", content="Reply with the single word: OK")],
                max_tokens=64,
            )
            return "OK" in r.content.upper()
        except Exception:
            return False


# Re-exports for backward compatibility (a couple of older paths import these names)
__all__ = ["GeminiProvider"]


# Add a small async shim used only by ``asyncio.to_thread`` callers — the
# previous codepath used to_thread; the new SDK is async-native so we no
# longer need it. The export stays here in case external code references it.
async def _legacy_offload(_func):  # pragma: no cover - keeps old import paths safe
    return await asyncio.to_thread(_func)
