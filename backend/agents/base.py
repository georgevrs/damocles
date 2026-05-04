"""BaseAgent abstraction.

Every agent in Damocles produces a structured ``AgentOutput`` and follows the
same hard rules (from the plan's Prompt Engineering Rules):

  1. **Schema enforcement:** the LLM is asked to emit JSON only, validated
     against ``AgentOutput`` with retry-on-invalid path.
  2. **Citation enforcement:** every key finding must reference a graph node
     ID present in the supplied context. Orphan claims fail validation.
  3. **Uncertainty enforcement:** ``uncertainty_flags`` must be non-empty —
     there is always uncertainty.
  4. **Token discipline:** prompts are bounded (default ≤4000 tokens of
     context for an 8B local model); no streaming the entire graph.
  5. **Retry once on invalid output** with an error-correction prompt.

Architectural choice: agents do NOT have tool-calling. Each ``run()`` call:
   pre-fetch graph context → format as compact prompt → LLM call → validate.

Tool calling adds two failure modes (wrong tool name, malformed args) for no
practical benefit on a focused 5-agent pipeline. If we later need ad-hoc
graph exploration, we can layer it on without changing this contract.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Iterable

from pydantic import BaseModel, Field, ValidationError

from backend.graph.client import Neo4jClient
from backend.llm.base import LLMMessage, LLMProvider

log = logging.getLogger(__name__)


class AgentOutput(BaseModel):
    """The strict output contract every agent must satisfy.

    ``key_findings`` is a list of analyst-grade statements. Each statement
    MUST be backed by at least one ID in ``citation_node_ids`` — otherwise
    the output is rejected and a retry is attempted.

    ``uncertainty_flags`` lists what the agent is *not* sure about. The plan
    requires at least one entry (no agent is omniscient).
    """
    analysis: str = Field(description="One-paragraph synthesis. <300 words.")
    key_findings: list[str] = Field(description="Discrete factual claims, max 5.")
    confidence: float = Field(ge=0.0, le=1.0)
    citation_node_ids: list[str] = Field(
        description="Every node ID referenced anywhere in analysis or findings.",
    )
    uncertainty_flags: list[str] = Field(
        description="What you are NOT sure about. Must be non-empty.",
    )


class DevilsAdvocateOutput(AgentOutput):
    """AgentOutput plus the devil's signature counter-signal.

    ``confidence`` retains its standard meaning ("how solid is THIS output —
    the counter-analysis itself"). ``devil_confidence`` is the new field:
    probability that the PRIMARY assessment is wrong. The two can diverge:
    a strong counter-argument backed by data might score 0.85 confidence
    even if devil_confidence is only 0.5 because the evidence is genuinely
    ambiguous.
    """
    devil_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Probability the primary assessment is WRONG (not right).",
    )


class AgentValidationError(ValueError):
    """Raised when an agent output fails citation/uncertainty validation."""


def validate_agent_output(
    out: AgentOutput,
    valid_node_ids: Iterable[str],
) -> None:
    """Reject orphan claims and empty uncertainty.

    Raises ``AgentValidationError`` with a precise message; callers use the
    message in the retry-correction prompt.
    """
    valid = set(valid_node_ids)

    if not out.uncertainty_flags:
        raise AgentValidationError(
            "uncertainty_flags is empty. Every analytical output must declare "
            "at least one source of uncertainty."
        )

    if not out.citation_node_ids:
        raise AgentValidationError(
            "citation_node_ids is empty. Every key finding must cite a graph node."
        )

    unknown = [nid for nid in out.citation_node_ids if nid not in valid]
    if unknown:
        raise AgentValidationError(
            f"citation_node_ids reference unknown graph nodes: {unknown[:3]}"
            f"{'…' if len(unknown) > 3 else ''}. "
            f"Valid IDs in this context: {list(valid)[:5]}{'…' if len(valid) > 5 else ''}"
        )

    if not out.key_findings:
        raise AgentValidationError("key_findings is empty.")


def _strip_markdown_fence(text: str) -> str:
    """Strip ``` and ```json fences some models add despite json_mode."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


class BaseAgent(ABC):
    """All concrete agents subclass this.

    Subclasses provide:
        - ``name``  : short identifier used in logs and audit
        - ``model`` : optional provider override (e.g. devil's advocate uses qwen)
        - ``system_prompt()``  : returns the system message
        - ``fetch_context(...)``: pre-fetches graph data and returns
          ``(context_str, valid_node_ids)``
    """

    name: str = "base"
    temperature: float = 0.1
    # 2048 instead of the plan's original 1024: Gemini 2.5/3 spend ~30% of the
    # output budget on internal "thinking" tokens before producing visible JSON.
    # 1024 caused mid-string truncation on long agent outputs. 2048 leaves
    # ~1400 tokens for visible output, plenty for our schema.
    max_tokens: int = 2048
    # Subclasses override to change the output Pydantic model (e.g. Devil's
    # Advocate uses DevilsAdvocateOutput which adds a devil_confidence field).
    output_model: type[AgentOutput] = AgentOutput

    def __init__(self, llm: LLMProvider, graph: Neo4jClient):
        self.llm = llm
        self.graph = graph

    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    async def fetch_context(self, **kwargs: Any) -> tuple[str, list[str]]:
        """Return ``(context_text, valid_node_ids)`` for the LLM call."""

    async def run(self, **kwargs: Any) -> AgentOutput:
        """The full agent loop: fetch → call → validate (retry once on failure)."""
        context_text, valid_node_ids = await self.fetch_context(**kwargs)

        first = await self._call_llm(context_text)
        first_error: str | None = None
        try:
            validate_agent_output(first, valid_node_ids)
            return first
        except AgentValidationError as exc:
            first_error = str(exc)
            log.warning("%s: invalid output, retrying once: %s", self.name, first_error)

        retried = await self._call_llm_with_correction(context_text, first, first_error)
        validate_agent_output(retried, valid_node_ids)
        return retried

    # ─── internals ───────────────────────────────────────────────────────────
    async def _call_llm(self, context_text: str) -> AgentOutput:
        response = await self.llm.complete(
            messages=[
                LLMMessage(role="system", content=self.system_prompt()),
                LLMMessage(role="user", content=context_text),
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            json_mode=True,
        )
        return self._parse(response.content)

    async def _call_llm_with_correction(
        self,
        context_text: str,
        previous: AgentOutput,
        error_msg: str,
    ) -> AgentOutput:
        response = await self.llm.complete(
            messages=[
                LLMMessage(role="system", content=self.system_prompt()),
                LLMMessage(role="user", content=context_text),
                LLMMessage(role="assistant", content=previous.model_dump_json()),
                LLMMessage(
                    role="user",
                    content=(
                        "Your previous output had this validation error:\n\n"
                        f"  {error_msg}\n\n"
                        "Produce a corrected output. Only use citation_node_ids "
                        "from the context above. Output ONLY valid JSON matching "
                        "the AgentOutput schema. No preamble, no markdown."
                    ),
                ),
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            json_mode=True,
        )
        return self._parse(response.content)

    def _parse(self, raw: str) -> AgentOutput:
        cleaned = _strip_markdown_fence(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise AgentValidationError(f"output is not valid JSON: {exc}") from exc
        try:
            return self.output_model(**data)
        except ValidationError as exc:
            raise AgentValidationError(f"output does not match schema: {exc}") from exc
