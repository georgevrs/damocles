"""OSINTAgent — reasons over the OSINT slice (NewsEvent + SocialSignal) of a
CompositeEvent.

Same pattern as GeospatialAgent: pre-fetch the COMPOSED_OF sources, format
them compactly with the explicit list of valid citation IDs, ask the LLM
for a structured AgentOutput.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .base import BaseAgent

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "osint.txt"


class OSINTAgent(BaseAgent):
    name = "osint_agent"
    temperature = 0.1
    max_tokens = 2048

    def system_prompt(self) -> str:
        return _PROMPT_PATH.read_text(encoding="utf-8")

    async def fetch_context(self, composite_event_id: str, **_kwargs):
        # Neo4j first → DuckDB fallback via shared helper. Then filter to
        # information-strand sources (News + Social) since OSINT doesn't
        # reason over vessel detections directly.
        from ._context import fetch_ce_with_sources
        ce, all_sources = await fetch_ce_with_sources(self.graph, composite_event_id)
        sources_raw = [s for s in all_sources if s["type"] in ("NewsEvent", "SocialSignal")]

        valid_ids: list[str] = [ce["id"]]
        sources_compact: list[dict] = []
        for s in sources_raw:
            t = s["type"]
            p = dict(s["props"])
            sid = p.get("id")
            if sid:
                valid_ids.append(sid)
            sources_compact.append({"type": t, **self._compact(t, p)})

        ce_compact = {
            "id":           ce["id"],
            "threat_grade": ce.get("threat_grade"),
            "summary":      ce.get("summary"),
            "confidence":   ce.get("confidence"),
            "centroid":     [ce.get("centroid_lat"), ce.get("centroid_lon")],
        }

        ctx = (
            f"Valid citation_node_ids you may reference (and only these):\n"
            f"  {valid_ids}\n\n"
            f"CompositeEvent under analysis:\n"
            f"  {json.dumps(ce_compact, default=str)}\n\n"
            f"OSINT source nodes ({len(sources_compact)}):\n"
            f"  {json.dumps(sources_compact, default=str, ensure_ascii=False)}\n\n"
            f"Produce your structured AgentOutput now."
        )
        return ctx, valid_ids

    @staticmethod
    def _compact(node_type: str, p: dict) -> dict:
        if node_type == "NewsEvent":
            return {
                "id":        p.get("id"),
                "headline":  (p.get("headline") or "")[:120],
                "source":    p.get("source_name"),
                "url":       p.get("source_url"),
                "lat":       p.get("lat"),
                "lon":       p.get("lon"),
                "timestamp": str(p.get("timestamp", "")),
                "goldstein": p.get("goldstein_scale"),
                "cameo":     p.get("cameo_code"),
                "mentions":  p.get("mentions"),
                "language":  p.get("language"),
            }
        if node_type == "SocialSignal":
            return {
                "id":            p.get("id"),
                "channel":       p.get("channel"),
                "text":          (p.get("text") or "")[:300],
                "language":      p.get("language"),
                "timestamp":     str(p.get("timestamp", "")),
                "views":         p.get("views"),
                "forwards":      p.get("forwards"),
                "matched_place": p.get("matched_place"),
                "lat":           p.get("lat"),
                "lon":           p.get("lon"),
            }
        return {"id": p.get("id")}
