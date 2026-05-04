"""In-memory per-watch event broker.

Watch pipelines are launched as background tasks by ``POST /api/watches``.
The pipeline pushes progress events here; the WebSocket endpoint reads
them. This is single-process only — multi-worker deployment needs Redis
pub/sub, NATS, or equivalent. Documented as a limitation.

We keep events for ~5 minutes after a watch completes so a late-arriving
WebSocket client can catch up via the buffer rather than missing every
event before its connection.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import AsyncIterator

log = logging.getLogger(__name__)


class _Channel:
    """Per-watch event buffer + live subscriber set."""

    def __init__(self, max_buffer: int = 200):
        self.buffer: deque[dict] = deque(maxlen=max_buffer)
        self.subscribers: set[asyncio.Queue] = set()
        self.completed_at: float | None = None

    def append(self, event: dict) -> None:
        self.buffer.append(event)
        if event.get("stage") == "complete":
            self.completed_at = time.time()

    def is_done(self) -> bool:
        return self.completed_at is not None


class WatchEventBroker:
    """Process-local fan-out for watch pipeline progress events."""

    def __init__(self, retain_seconds: float = 300.0):
        self._channels: dict[str, _Channel] = {}
        self._retain_seconds = retain_seconds

    # ─── Producer side ──────────────────────────────────────────────────────
    async def publish(self, watch_id: str, event: dict) -> None:
        ch = self._channels.setdefault(watch_id, _Channel())
        ch.append(event)
        # Fan out to live subscribers; drop if a queue is closed.
        dead: list[asyncio.Queue] = []
        for q in ch.subscribers:
            try:
                q.put_nowait(event)
            except Exception:
                dead.append(q)
        for q in dead:
            ch.subscribers.discard(q)

    # ─── Consumer side ──────────────────────────────────────────────────────
    async def subscribe(self, watch_id: str) -> AsyncIterator[dict]:
        """Yield buffered events first, then live events until the pipeline completes
        (or the consumer disconnects).

        Race-safe under asyncio single-thread cooperative concurrency: the
        ``snapshot = list(...)`` + ``subscribers.add(q)`` pair is atomic
        against ``publish()`` because there's no ``await`` between them.
        Any event published after this block goes both into the buffer
        (after the snapshot) and into the live queue — we replay the
        snapshot then drain the queue, with no dupes and no lost events.
        """
        ch = self._channels.setdefault(watch_id, _Channel())
        q: asyncio.Queue = asyncio.Queue()

        # Atomic snapshot + registration — no await between these two lines.
        snapshot = list(ch.buffer)
        ch.subscribers.add(q)

        try:
            for event in snapshot:
                yield event
                if event.get("stage") == "complete":
                    return
            while True:
                event = await q.get()
                yield event
                if event.get("stage") == "complete":
                    break
        finally:
            ch.subscribers.discard(q)

    # ─── Inspection ─────────────────────────────────────────────────────────
    def buffered_events(self, watch_id: str) -> list[dict]:
        ch = self._channels.get(watch_id)
        return list(ch.buffer) if ch else []

    def is_done(self, watch_id: str) -> bool:
        ch = self._channels.get(watch_id)
        return bool(ch and ch.is_done())

    # ─── Housekeeping ───────────────────────────────────────────────────────
    def gc(self) -> int:
        """Drop channels that finished more than retain_seconds ago. Returns the
        number of channels evicted. Caller invokes periodically (e.g. on every
        new watch) — the evictions are O(channels) which is fine for our
        single-process scale.
        """
        cutoff = time.time() - self._retain_seconds
        stale = [
            wid for wid, ch in self._channels.items()
            if ch.completed_at is not None and ch.completed_at < cutoff and not ch.subscribers
        ]
        for wid in stale:
            self._channels.pop(wid, None)
        if stale:
            log.debug("WatchEventBroker.gc evicted %d stale channels", len(stale))
        return len(stale)


# Module-level singleton — wired into the FastAPI app state in main.py.
broker = WatchEventBroker()
