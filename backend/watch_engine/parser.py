"""Watch query parser — natural language → WatchSpec via the LLM provider.

The analyst types anything ("Aegean — last 7 days", "Turkish military activity
near Rhodes last 2 weeks", etc.). The parser uses the LLM in JSON mode with a
strict schema. No regex.
"""
from __future__ import annotations

import json
import logging

from backend.llm.base import LLMMessage, LLMProvider
from backend.models.watch import WatchSpec

log = logging.getLogger(__name__)

WATCH_PARSE_SYSTEM_PROMPT = """\
You are a query parser for Damocles, a sovereign intelligence platform.
The analyst has typed a free-text query. Parse it into a structured WatchSpec JSON.

The analyst may type anything. Examples of valid queries:
- "Aegean — last 7 days"
- "Turkish military activity near Rhodes last 2 weeks"
- "Information operations targeting Greek elections last month"
- "Unusual flights over Thrace past 3 days"
- "Evros border activity since Monday"
- "Maritime incidents Eastern Mediterranean Q1 2024"
- "Coordinated social media campaigns about Cyprus dispute"
- "Port of Piraeus vessel anomalies last 48 hours"

Output ONLY valid JSON. No preamble. Schema:
{
  "region": "aegean" | "ionian" | "evros" | "eastern_med" | "custom",
  "custom_bbox": [min_lon, min_lat, max_lon, max_lat] | null,
  "domain": "maritime" | "border" | "airspace" | "information" | "multi",
  "time_window_days": integer,
  "keywords": [string, ...],
  "threat_indicators": [string, ...],
  "confidence": float (0.0-1.0, your confidence in this parse),
  "parse_notes": string (one sentence explaining ambiguity, or empty)
}

Rules:
- "last X days/weeks/months" → time_window_days (week=7, month=30, quarter=90).
- If no time mentioned, default time_window_days = 7.
- If region is unclear, default to "aegean" with parse_notes explaining.
- "multi" domain when the query spans multiple domains or is generic.
- Translate Greek place names (Αιγαίο=aegean, Έβρος=evros, Ιόνιο=ionian).
"""


class WatchParser:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def parse(self, raw_query: str) -> WatchSpec:
        response = await self.llm.complete(
            messages=[
                LLMMessage(role="system", content=WATCH_PARSE_SYSTEM_PROMPT),
                LLMMessage(role="user", content=f'Parse this query: "{raw_query}"'),
            ],
            temperature=0.0,
            max_tokens=512,
            json_mode=True,
        )

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as exc:
            log.warning("WatchParser got invalid JSON, retrying once: %s", exc)
            data = await self._retry(raw_query, response.content, str(exc))

        return WatchSpec(**data)

    async def _retry(self, raw_query: str, prior_output: str, error: str) -> dict:
        retry = await self.llm.complete(
            messages=[
                LLMMessage(role="system", content=WATCH_PARSE_SYSTEM_PROMPT),
                LLMMessage(role="user", content=f'Parse this query: "{raw_query}"'),
                LLMMessage(role="assistant", content=prior_output),
                LLMMessage(
                    role="user",
                    content=(
                        f"Your previous output was not valid JSON ({error}). "
                        "Output only valid JSON matching the schema. No preamble, no markdown."
                    ),
                ),
            ],
            temperature=0.0,
            max_tokens=512,
            json_mode=True,
        )
        return json.loads(retry.content)
