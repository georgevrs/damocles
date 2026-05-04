"""AISStream.io WebSocket client.

AISStream provides a free real-time AIS feed; **historical replay is paid**.
That mismatch with Sentinel-1's 6-day SAR revisit cadence is the reason the
demo runs against pre-seeded data — the ``scripts/seed_neo4j.py`` pipeline
captures live AIS during the seed window and pickles it alongside SAR tiles.

Protocol gotchas
----------------
- AISStream uses ``[[lat, lon]]`` ordering in BoundingBoxes — NOT ``[lon, lat]``.
  Most GeoJSON libraries do the opposite, so this is the #1 source of "no
  messages received" errors.
- BoundingBoxes is doubly nested: outer = list of boxes, each box =
  ``[[sw_lat, sw_lon], [ne_lat, ne_lon]]``.
- Auth is passed in the subscription frame, not as a header. The connection
  itself opens unauthenticated — wrong API key triggers a graceful close,
  not a 401.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Iterable

import websockets

from backend.config import settings

from .base import BBox
from .dark_vessel import AISRecord

log = logging.getLogger(__name__)

WS_URL = "wss://stream.aisstream.io/v0/stream"


def _bbox_to_aisstream(bbox: BBox) -> list[list[list[float]]]:
    """Damocles bbox is (min_lon, min_lat, max_lon, max_lat).
    AISStream expects [[[sw_lat, sw_lon], [ne_lat, ne_lon]]]."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return [[[min_lat, min_lon], [max_lat, max_lon]]]


def _parse_position_report(msg: dict) -> AISRecord | None:
    """AISStream position-report shape:
        {
          "MessageType": "PositionReport",
          "MetaData": { "MMSI": int, "ShipName": "...", "time_utc": "...", "latitude": .., "longitude": .. },
          "Message": { "PositionReport": { "Latitude": .., "Longitude": .., "Sog": .., "Cog": .. } }
        }
    """
    md = msg.get("MetaData") or {}
    body = (msg.get("Message") or {}).get("PositionReport") or {}
    if not md or not body:
        return None

    mmsi = md.get("MMSI")
    if mmsi is None:
        return None

    lat = body.get("Latitude") or md.get("latitude")
    lon = body.get("Longitude") or md.get("longitude")
    if lat is None or lon is None:
        return None

    ts_raw = md.get("time_utc")
    timestamp = _parse_iso(ts_raw) if ts_raw else datetime.now(tz=timezone.utc)

    name = (md.get("ShipName") or "").strip() or None
    return AISRecord(
        mmsi=str(mmsi),
        lat=float(lat),
        lon=float(lon),
        timestamp=timestamp,
        name=name,
        sog_knots=body.get("Sog"),
        cog_deg=body.get("Cog"),
    )


def _parse_iso(s: str) -> datetime:
    """AISStream's time_utc looks like ``2024-03-17 14:30:00.123456789 +0000 UTC``.
    Best-effort parser — fall back to ``datetime.now(UTC)`` on weird shapes.
    """
    s = s.strip()
    # Strip the trailing " UTC" tag if present.
    if s.endswith(" UTC"):
        s = s[:-4]
    # Normalize "+0000" to "+00:00" so fromisoformat accepts it on 3.11+.
    if len(s) >= 5 and (s[-5] == "+" or s[-5] == "-") and s[-3] != ":":
        s = s[:-2] + ":" + s[-2:]
    # Truncate sub-microsecond precision to 6 digits if longer.
    if "." in s:
        date_part, dot, frac_tz = s.partition(".")
        # frac_tz might be "123456789 +00:00"
        frac, sep, tz = frac_tz.partition(" ")
        frac = frac[:6]
        s = f"{date_part}.{frac}{sep}{tz}" if tz else f"{date_part}.{frac}"
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(tz=timezone.utc)


class AISStreamClient:
    """Live AIS capture over a bbox.

    Use as::

        client = AISStreamClient(bbox=(22.0, 35.0, 28.0, 42.0))
        records = await client.capture(duration_seconds=30)
    """

    def __init__(
        self,
        bbox: BBox,
        api_key: str | None = None,
        message_types: Iterable[str] = ("PositionReport",),
        ws_url: str = WS_URL,
    ):
        self.bbox = bbox
        self.api_key = api_key or settings.AISSTREAM_API_KEY
        if not self.api_key:
            raise ValueError(
                "AISStreamClient needs AISSTREAM_API_KEY. See docs/credentials.md §4."
            )
        self.message_types = list(message_types)
        self.ws_url = ws_url

    def _subscription_frame(self) -> str:
        return json.dumps({
            "APIKey": self.api_key,
            "BoundingBoxes": _bbox_to_aisstream(self.bbox),
            "FilterMessageTypes": self.message_types,
        })

    async def capture(self, duration_seconds: float = 30.0) -> list[AISRecord]:
        """Subscribe to the stream and collect messages for ``duration_seconds``.

        Returns whatever AIS records were received. Empty list on a quiet
        bbox is normal, not an error.
        """
        records: list[AISRecord] = []
        deadline = asyncio.get_event_loop().time() + duration_seconds

        log.info("AISStream capture: bbox=%s duration=%.1fs", self.bbox, duration_seconds)
        try:
            async with websockets.connect(self.ws_url) as ws:
                await ws.send(self._subscription_frame())
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    except asyncio.TimeoutError:
                        break
                    rec = self._handle_frame(raw)
                    if rec is not None:
                        records.append(rec)
        except websockets.exceptions.ConnectionClosed as exc:
            log.warning("AISStream closed connection: code=%s reason=%r", exc.code, exc.reason)
        except Exception:
            log.exception("AISStream capture failed")
            raise

        log.info("AISStream capture done: %d records", len(records))
        return records

    @staticmethod
    def _handle_frame(raw: str | bytes) -> AISRecord | None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if msg.get("MessageType") != "PositionReport":
            return None
        return _parse_position_report(msg)
