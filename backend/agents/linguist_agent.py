"""LinguistAgent — geocode Telegram signals, then summarize the batch.

Two-phase contract:

  1. ``enrich(signals)`` — pure-function gazetteer geocoding. No LLM. Returns
     a list of (signal_id, lat, lon, matched_place) tuples for every
     SocialSignal whose text matched the gazetteer. Caller writes the lat/lon
     back to Neo4j (via ``persist_enrichments``). This step is what closes
     limitations §4c.3 (Telegram messages have no native geocoding).

  2. ``run(composite_event_id=...)`` — standard BaseAgent pattern. Pre-fetches
     the SocialSignals attached to a CompositeEvent, includes their (newly
     enriched) lat/lon and detected language in the prompt, asks the LLM for
     a structured AgentOutput.

Run-order in the pipeline:
    sensor fan-out
        -> LinguistAgent.enrich(all_signals_in_watch)        # pre-fusion
        -> persist enriched lat/lon back to Neo4j
        -> fusion (now SocialSignals correlate spatially)
        -> per-composite agent runs (LinguistAgent.run, OSINTAgent.run, ...)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from backend.graph.client import Neo4jClient
from backend.models.event import SocialSignal

from ._geocoder import GeoMatch, Geocoder
from .base import BaseAgent

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "linguist.txt"


@dataclass(frozen=True)
class SignalEnrichment:
    signal_id: str
    lat: float
    lon: float
    matched_place: str
    matched_alias: str
    country: str


class LinguistAgent(BaseAgent):
    name = "linguist_agent"
    temperature = 0.1
    max_tokens = 2048

    def __init__(self, llm, graph: Neo4jClient, geocoder: Geocoder | None = None):
        super().__init__(llm=llm, graph=graph)
        self.geocoder = geocoder or Geocoder()

    # ─── Phase 1: deterministic enrichment ───────────────────────────────────
    def enrich(self, signals: list[SocialSignal]) -> list[SignalEnrichment]:
        """Run gazetteer geocoder over each signal's text. No LLM."""
        out: list[SignalEnrichment] = []
        for s in signals:
            match: GeoMatch | None = self.geocoder.geocode_text(s.text)
            if match is None:
                continue
            out.append(SignalEnrichment(
                signal_id=s.id,
                lat=match.lat,
                lon=match.lon,
                matched_place=match.canonical,
                matched_alias=match.matched_alias,
                country=match.country,
            ))
        log.info("LinguistAgent.enrich: %d/%d signals geocoded", len(out), len(signals))
        return out

    async def persist_enrichments(self, enrichments: list[SignalEnrichment]) -> int:
        """Write lat/lon back to the SocialSignal nodes in Neo4j.

        Returns the number of nodes updated. Idempotent — overwrites lat/lon
        on every call. Use this in the pipeline AFTER ingest_social() and
        BEFORE fusion so the fusion engine sees the enriched coordinates.
        """
        if not enrichments:
            return 0
        await self.graph.run(
            """
            UNWIND $rows AS r
            MATCH (s:SocialSignal {id: r.id})
            SET s.lat            = r.lat,
                s.lon            = r.lon,
                s.matched_place  = r.place,
                s.matched_alias  = r.alias,
                s.matched_country= r.country
            """,
            rows=[{
                "id":      e.signal_id,
                "lat":     e.lat,
                "lon":     e.lon,
                "place":   e.matched_place,
                "alias":   e.matched_alias,
                "country": e.country,
            } for e in enrichments],
        )
        return len(enrichments)

    # ─── Phase 2: per-composite analytical pass ──────────────────────────────
    def system_prompt(self) -> str:
        return _PROMPT_PATH.read_text(encoding="utf-8")

    async def fetch_context(self, composite_event_id: str, **_kwargs):
        rows = await self.graph.run(
            """
            MATCH (ce:CompositeEvent {id: $id})
            OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(s:SocialSignal)
            RETURN ce, collect(s) AS signals
            """,
            id=composite_event_id,
        )
        if not rows or not rows[0].get("ce"):
            raise ValueError(f"CompositeEvent {composite_event_id!r} not found")

        ce = rows[0]["ce"]
        signals = [s for s in (rows[0]["signals"] or []) if s]

        valid_ids = [ce["id"]] + [s["id"] for s in signals if s.get("id")]
        sigs_compact = [{
            "id":      s.get("id"),
            "channel": s.get("channel"),
            "language": s.get("language"),
            "timestamp": str(s.get("timestamp", "")),
            "views":   s.get("views"),
            "matched_place": s.get("matched_place"),
            "lat":     s.get("lat"),
            "lon":     s.get("lon"),
            "text":    (s.get("text") or "")[:300],
        } for s in signals]

        ctx = (
            f"Valid citation_node_ids you may reference (and only these):\n"
            f"  {valid_ids}\n\n"
            f"CompositeEvent under analysis:\n"
            f"  {json.dumps({'id': ce['id'], 'threat_grade': ce.get('threat_grade'), 'summary': ce.get('summary')}, default=str)}\n\n"
            f"SocialSignals attached ({len(sigs_compact)}):\n"
            f"  {json.dumps(sigs_compact, default=str, ensure_ascii=False)}\n\n"
            f"Produce your structured AgentOutput now."
        )
        return ctx, valid_ids
