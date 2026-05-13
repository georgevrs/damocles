"""System-level endpoints — runtime configuration swaps for the demo.

The only endpoint here right now is ``POST /api/system/llm/switch``, the
W3-T2 LLM provider swap. The pitch needs to show the SystemPill flipping
from ``gemini-…`` to ``llama3.1`` without restarting the backend, to back
the claim *"on a sovereign deployment this runs on a local model the
analyst can audit byte-for-byte — same brief pipeline, different brain."*

Gated on ``settings.DEMO_MODE`` so production deploys don't expose a
runtime provider switcher.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.config import settings
from backend.llm import factory as llm_factory

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


class LlmSwitchBody(BaseModel):
    provider: Literal["gemini", "ollama"]


@router.post("/llm/switch")
async def switch_llm(body: LlmSwitchBody, request: Request) -> dict[str, Any]:
    """Swap the in-process LLM provider singleton.

    Mutates ``settings.LLM_PROVIDER``, clears the ``get_provider`` lru cache,
    and rebinds ``app.state.executor.llm`` so subsequent agent calls go to
    the new provider. The factory's ``get_devil_provider`` reads
    ``settings.LLM_PROVIDER`` lazily so it picks up the change for free.

    Does NOT roll back on provider-down — the SystemPill will show a red
    dot if the new provider's ``health_check`` fails, which is the honest
    representation of state. The point of this endpoint is to demonstrate
    the swap, not to gate it on remote liveness.
    """
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="not available")

    previous = settings.LLM_PROVIDER
    settings.LLM_PROVIDER = body.provider  # type: ignore[assignment]
    llm_factory.get_provider.cache_clear()

    try:
        new_provider = llm_factory.get_provider()
    except Exception as exc:
        # Roll back so we don't leave the process in an unusable state if
        # the new provider can't even be instantiated (e.g. Gemini key
        # missing). The caller will see the failure in the response.
        settings.LLM_PROVIDER = previous  # type: ignore[assignment]
        llm_factory.get_provider.cache_clear()
        raise HTTPException(
            status_code=400,
            detail=f"cannot instantiate {body.provider!r}: {type(exc).__name__}: {exc}",
        )

    # Rebind the executor's bound provider so already-constructed pipelines
    # pick up the new brain on their next agent step.
    executor = getattr(request.app.state, "executor", None)
    if executor is not None:
        executor.llm = new_provider

    # Probe liveness so the UI can render an accurate red/green dot
    # immediately rather than waiting for the next /health poll.
    try:
        live = await new_provider.health_check()
    except Exception as exc:
        log.info("post-switch health_check raised: %s", exc)
        live = False

    return {
        "swapped":         True,
        "previous":        previous,
        "current":         settings.LLM_PROVIDER,
        "model":           new_provider.get_model_name(),
        "alive":           live,
    }
