"""Ollama local LLM provider — used for the demo and production deployment.

Runs entirely on-prem. No data leaves the machine. This is what powers the
sovereignty argument in the EYP pitch.

Recommended models:
    - llama3.1:8b   primary reasoning  (~4.7 GB)
    - qwen2.5:7b    devil's advocate   (~4.4 GB)
    - llama3.2:3b   fast query parser  (~2.0 GB)

Hardware budget for smooth demo:
    - GPU: 8 GB VRAM (RTX 3070 / M2 Pro / A10G on GCP)
    - RAM: 16 GB
"""
from __future__ import annotations

import time

import ollama as _ollama

from .base import LLMMessage, LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
    ):
        self.base_url = base_url
        self.model = model
        self._client = _ollama.AsyncClient(host=base_url)

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        start = time.time()

        ollama_messages = [{"role": m.role, "content": m.content} for m in messages]

        response = await self._client.chat(
            model=self.model,
            messages=ollama_messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            format="json" if json_mode else "",
        )

        latency_ms = (time.time() - start) * 1000.0
        return LLMResponse(
            content=response["message"]["content"],
            model=self.model,
            provider="ollama",
            input_tokens=response.get("prompt_eval_count", 0),
            output_tokens=response.get("eval_count", 0),
            latency_ms=latency_ms,
        )

    def get_model_name(self) -> str:
        return self.model

    async def health_check(self) -> bool:
        try:
            listing = await self._client.list()
            available = {m.get("name", "") for m in listing.get("models", [])}
            # Allow tag-less match too: "llama3.1" should match "llama3.1:8b"
            return self.model in available or any(
                m.startswith(self.model.split(":")[0]) for m in available
            )
        except Exception:
            return False
