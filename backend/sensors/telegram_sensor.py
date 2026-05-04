"""Telegram OSINT sensor.

Reads **public** channels via Telethon (the MTProto Telegram client). Curated
channel list lives in ``DEFAULT_CHANNELS``; the seed pipeline can pass a
custom list via the ``channels=`` kwarg to ``fetch()``.

Authentication
--------------
Telegram requires phone-number-based MTProto auth. The first time a session
is created Telegram sends a one-time code that the user must enter at the
terminal. After that, the session pickles to ``data/cache/telegram/<name>.session``
and subsequent connects are silent.

We DELIBERATELY split the interactive auth into a separate script
(``scripts/setup_telegram.py``) so this sensor can be called from the live
backend without ever blocking on user input. If you call ``fetch()`` without
having run the setup script, the sensor raises immediately with a helpful
pointer.

Privacy
-------
- Public channels only. Reading restricted/private channels would require
  joining them, which is out of scope.
- Storing channel content locally is acceptable under Telegram's TOS for
  research and OSINT, but we don't redistribute messages — they stay in the
  Damocles graph for analyst review.
"""
from __future__ import annotations

import asyncio
import logging
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from langdetect import LangDetectException, detect

from backend.config import settings
from backend.models.event import SocialSignal

from .base import BaseSensor, BBox, SensorResult

log = logging.getLogger(__name__)

# Starter channel list — REPLACE with your curated, verified list during Week 1.
# These are placeholder examples; some may not exist or may be private. The
# sensor logs and skips channels it can't resolve; it does not raise.
DEFAULT_CHANNELS: tuple[str, ...] = (
    # Aegean / Greek-Turkish OSINT
    "@aegeanwatch",
    "@greekmilitary",
    "@turkishnavy_news",
    "@southeasteurope",
)

DEFAULT_KEYWORDS: tuple[str, ...] = (
    # English
    "aegean", "vessel", "warship", "frigate", "navy", "violation", "incursion",
    "fighter", "drone", "sortie",
    # Greek
    "Αιγαίο", "πλοίο", "φρεγάτα", "πολεμικό",
    # Turkish
    "Ege", "savaş gemisi", "ihlal", "uçuş",
)


def _default_session_path() -> Path:
    p = settings.cache_dir / "telegram"
    p.mkdir(parents=True, exist_ok=True)
    return p / "damocles.session"


def _detect_language(text: str) -> str:
    try:
        return detect(text)
    except LangDetectException:
        return "und"


def _normalize(s: str) -> str:
    """Casefold + strip combining diacritical marks.

    This handles two real problems for the Aegean keyword set:
      - **Monotonic Greek**: capitalized words drop the tonos (ΑΙΓΑΙΟ has no
        accent, αιγαίο does). Plain casefold won't substring-match across
        the two; NFD + strip-Mn does.
      - **Turkish dotted/dotless I**: I/ı/İ/i. casefold handles this; we keep
        it and just add the diacritic stripping on top.
    """
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.casefold()


def _matches_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    """Diacritic- and case-insensitive substring match."""
    if not text:
        return False
    haystack = _normalize(text)
    return any(_normalize(kw) in haystack for kw in keywords)


class TelegramSensor(BaseSensor[SocialSignal]):
    name = "telegram"

    def __init__(
        self,
        api_id: str | int | None = None,
        api_hash: str | None = None,
        session_path: Path | None = None,
        default_channels: Iterable[str] = DEFAULT_CHANNELS,
        default_keywords: Iterable[str] = DEFAULT_KEYWORDS,
    ):
        self.api_id = int(api_id) if api_id is not None else int(settings.TELEGRAM_API_ID or 0)
        self.api_hash = api_hash or settings.TELEGRAM_API_HASH
        if not self.api_id or not self.api_hash:
            raise ValueError(
                "TelegramSensor needs TELEGRAM_API_ID and TELEGRAM_API_HASH. "
                "See docs/credentials.md §5."
            )
        self.session_path = session_path or _default_session_path()
        self.default_channels = tuple(default_channels)
        self.default_keywords = tuple(default_keywords)

    async def fetch(
        self,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        *,
        channels: Iterable[str] | None = None,
        keywords: Iterable[str] | None = None,
        per_channel_limit: int = 200,
        **_kwargs,
    ) -> SensorResult[SocialSignal]:
        # bbox is unused — Telegram messages are not geocoded. We keep the
        # signature aligned with BaseSensor so the pipeline can dispatch
        # uniformly.
        _ = bbox
        start = time.time()

        from telethon import TelegramClient
        from telethon.errors import AuthKeyUnregisteredError, ChannelPrivateError, UsernameNotOccupiedError

        if not self.session_path.exists():
            raise RuntimeError(
                f"No Telethon session at {self.session_path}. "
                f"Run `uv run python scripts/setup_telegram.py` once for interactive auth."
            )

        chans = tuple(channels) if channels else self.default_channels
        kws = tuple(keywords) if keywords else self.default_keywords

        # Make timestamps tz-aware UTC so Telethon's offset_date comparison works.
        if time_from.tzinfo is None:
            time_from = time_from.replace(tzinfo=timezone.utc)
        if time_to.tzinfo is None:
            time_to = time_to.replace(tzinfo=timezone.utc)

        events: list[SocialSignal] = []
        per_channel_counts: dict[str, int] = {}
        skipped_channels: list[tuple[str, str]] = []  # (channel, reason)

        client = TelegramClient(str(self.session_path), self.api_id, self.api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError(
                    "Telethon session present but not authorized. "
                    "Re-run `uv run python scripts/setup_telegram.py`."
                )

            for channel in chans:
                try:
                    n = 0
                    async for msg in client.iter_messages(
                        channel,
                        offset_date=time_to,
                        limit=per_channel_limit,
                    ):
                        if msg.date is None or msg.date < time_from:
                            break
                        text = (msg.text or "").strip()
                        if not text:
                            continue
                        if kws and not _matches_any_keyword(text, kws):
                            continue
                        events.append(self._to_signal(channel, msg, text))
                        n += 1
                    per_channel_counts[channel] = n
                except (UsernameNotOccupiedError, ChannelPrivateError) as exc:
                    skipped_channels.append((channel, type(exc).__name__))
                    log.warning("Telegram skip %s: %s", channel, exc)
                except AuthKeyUnregisteredError as exc:
                    raise RuntimeError(
                        f"Telethon session invalidated ({exc}). "
                        f"Delete {self.session_path} and re-run scripts/setup_telegram.py."
                    ) from exc
                except Exception as exc:
                    skipped_channels.append((channel, str(exc)[:80]))
                    log.warning("Telegram skip %s: %s", channel, exc)

                # Politeness pause to stay well under FloodWait thresholds.
                await asyncio.sleep(0.2)
        finally:
            await client.disconnect()

        return SensorResult(
            sensor_name=self.name,
            events=events,
            bbox=bbox,
            time_from=time_from,
            time_to=time_to,
            metadata={
                "channels_attempted": list(chans),
                "channels_skipped": skipped_channels,
                "per_channel_counts": per_channel_counts,
                "keyword_filter_size": len(kws),
            },
            duration_ms=(time.time() - start) * 1000,
        )

    @staticmethod
    def _to_signal(channel: str, msg, text: str) -> SocialSignal:
        return SocialSignal(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"telegram://{channel}/{msg.id}")),
            channel=channel,
            channel_verified=False,   # filled in by the linguist agent if relevant
            message_id=str(msg.id),
            text=text,
            timestamp=msg.date.astimezone(timezone.utc),
            language=_detect_language(text),
            views=int(getattr(msg, "views", 0) or 0),
            forwards=int(getattr(msg, "forwards", 0) or 0),
            has_media=bool(msg.media is not None),
        )
