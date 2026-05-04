"""Geospatial agent — maritime-domain reasoning over a single CompositeEvent.

Fetches the CompositeEvent + its COMPOSED_OF Vessel/NewsEvent/SocialSignal
sources from Neo4j, formats them as a compact context block, and asks the
LLM for a structured ``AgentOutput`` with citations to actual graph node IDs.

The system prompt lives in ``backend/agents/prompts/geospatial.txt`` so it
can be edited without touching code (and so it stays consistent between dev
and demo).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .base import BaseAgent

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "geospatial.txt"


class GeospatialAgent(BaseAgent):
    name = "geospatial_agent"
    temperature = 0.1
    max_tokens = 2048

    def system_prompt(self) -> str:
        return _PROMPT_PATH.read_text(encoding="utf-8")

    async def fetch_context(
        self,
        composite_event_id: str,
        **_kwargs,
    ) -> tuple[str, list[str]]:
        """Pull the CompositeEvent + its sources, format as compact JSON-ish context."""
        rows = await self.graph.run(
            """
            MATCH (ce:CompositeEvent {id: $id})
            OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(source)
            RETURN ce, collect({type: labels(source)[0], props: source}) AS sources
            """,
            id=composite_event_id,
        )
        if not rows or not rows[0].get("ce"):
            raise ValueError(f"CompositeEvent {composite_event_id!r} not found")

        row = rows[0]
        ce = row["ce"]
        sources_raw = [s for s in (row["sources"] or []) if s and s.get("type")]

        valid_ids: list[str] = [ce["id"]]
        sources_compact: list[dict] = []
        for s in sources_raw:
            t = s["type"]
            p = dict(s["props"])  # neo4j Node -> dict
            sid = p.get("id")
            if sid:
                valid_ids.append(sid)
            sources_compact.append({"type": t, **self._compact_source_props(t, p)})

        ce_compact = {
            "id":                  ce["id"],
            "threat_grade":        ce.get("threat_grade"),
            "confidence":          ce.get("confidence"),
            "corroboration_count": ce.get("corroboration_count"),
            "summary":             ce.get("summary"),
            "centroid":            [ce.get("centroid_lat"), ce.get("centroid_lon")],
        }

        # Compact prompt: list valid IDs explicitly so the model can copy-paste.
        ctx = (
            f"Valid citation_node_ids you may reference (and only these):\n"
            f"  {valid_ids}\n\n"
            f"CompositeEvent under analysis:\n"
            f"  {json.dumps(ce_compact, default=str)}\n\n"
            f"Source nodes ({len(sources_compact)}) the fusion engine attached:\n"
            f"  {json.dumps(sources_compact, default=str)}\n\n"
            f"Produce your structured AgentOutput now."
        )
        return ctx, valid_ids

    @staticmethod
    def _compact_source_props(node_type: str, p: dict) -> dict:
        """Trim a graph node down to fields useful for maritime reasoning,
        keeping prompts well under 4k tokens even on busy composites."""
        keep_id = p.get("id")
        if node_type == "Vessel":
            return {
                "id": keep_id,
                "lat": p.get("lat"), "lon": p.get("lon"),
                "timestamp": str(p.get("timestamp", "")),
                "ais_status": p.get("ais_status"),
                "mmsi": p.get("mmsi"),
                "name": p.get("vessel_name"),
                "flag": p.get("flag"),
                "length_m": p.get("length_m"),
                "confidence": p.get("confidence"),
                "dark_score": p.get("dark_vessel_score"),
            }
        if node_type == "NewsEvent":
            return {
                "id": keep_id,
                "lat": p.get("lat"), "lon": p.get("lon"),
                "timestamp": str(p.get("timestamp", "")),
                "headline": (p.get("headline") or "")[:120],
                "source": p.get("source_name"),
                "goldstein": p.get("goldstein_scale"),
                "cameo": p.get("cameo_code"),
                "mentions": p.get("mentions"),
            }
        if node_type == "SocialSignal":
            return {
                "id": keep_id,
                "channel": p.get("channel"),
                "timestamp": str(p.get("timestamp", "")),
                "language": p.get("language"),
                "text": (p.get("text") or "")[:200],
                "views": p.get("views"),
            }
        return {"id": keep_id, **{k: v for k, v in p.items() if k in {"timestamp"}}}
