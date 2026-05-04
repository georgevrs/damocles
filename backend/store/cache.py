"""Sensor cache mixin.

Sensors with cacheable fetches inherit ``CachedSensorMixin`` and call
``await self._run_with_cache(...)`` from their ``fetch()`` body. The mixin:

  1. Looks up DuckDB by (sensor, bbox, time-window). If a fresh row exists,
     reads the cached events back as Pydantic models and returns a
     ``SensorResult`` with ``metadata['cache_hit']=True``.
  2. Otherwise calls the wrapped ``fetcher(...)`` (the real upstream fetch),
     persists the events, records the cache marker, and returns the
     fresh result with ``metadata['cache_hit']=False``.

The mixin never silently swallows fetcher errors — the caller (executor)
already wraps each sensor in try/except.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Iterable

from backend.sensors.base import BBox, SensorResult

log = logging.getLogger(__name__)


# Mapping of "kind" → (upsert_method_name, read_method_name).
# Adding a new sensor kind = adding a row here + the matching DuckDBStore methods.
CACHE_KINDS = {
    "ais":    ("upsert_vessels",  "read_vessels"),
    "sar":    ("upsert_sar",      "read_vessels"),  # SAR vessels are still Vessel objects
    "news":   ("upsert_news",     "read_news"),
    "social": ("upsert_social",   "read_social"),
    "flight": ("upsert_flights",  "read_flights"),
}


class CachedSensorMixin:
    """Mix into any sensor whose ``fetch()`` is deterministic given a
    (bbox, time_window) pair."""

    cache_ttl_seconds: int = 0
    cache_kind: str = ""  # one of CACHE_KINDS keys

    async def _run_with_cache(
        self,
        *,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        sensor_name: str,
        fetcher: Callable[[], Awaitable[SensorResult]],
        kind: str | None = None,
        ttl_seconds: int | None = None,
        extra: dict | None = None,
    ) -> SensorResult:
        # Late import to keep ``backend.sensors`` free of duckdb at import time.
        from backend.store import get_store

        kind = kind or self.cache_kind
        ttl = ttl_seconds if ttl_seconds is not None else self.cache_ttl_seconds
        if not kind or kind not in CACHE_KINDS:
            log.debug("cache mixin: kind=%r unknown; skipping cache", kind)
            return await fetcher()

        store = get_store()
        upsert_name, read_name = CACHE_KINDS[kind]

        # 1. Read-through
        hit_key = await asyncio.to_thread(
            store.cache_lookup, sensor_name, bbox, time_from, time_to, ttl, extra
        )
        if hit_key:
            t0 = time.perf_counter()
            events = await asyncio.to_thread(getattr(store, read_name), hit_key)
            duration_ms = (time.perf_counter() - t0) * 1000
            log.info("cache HIT %s %s rows=%d in %.1fms", sensor_name, hit_key[:8], len(events), duration_ms)
            return SensorResult(
                sensor_name=sensor_name,
                events=events,
                bbox=bbox,
                time_from=time_from,
                time_to=time_to,
                duration_ms=duration_ms,
                metadata={"cache_hit": True, "cache_key": hit_key},
            )

        # 2. Live fetch
        result = await fetcher()

        # 3. Write-through
        cache_key = store.cache_key(sensor_name, bbox, time_from, time_to, extra)
        try:
            upsert = getattr(store, upsert_name)
            n = await asyncio.to_thread(upsert, cache_key, result.events)
            await asyncio.to_thread(
                store.cache_record,
                cache_key, sensor_name, bbox, time_from, time_to, n,
                {"source": "live", **(result.metadata or {})},
            )
            # Mirror SAR vessels into raw_sar in addition to raw_ais when AIS+SAR fused.
            if kind == "ais" and any(getattr(v, "detection_source", "") in ("SAR", "both") for v in result.events):
                await asyncio.to_thread(store.upsert_sar, cache_key, result.events)
            result.metadata = {**(result.metadata or {}), "cache_hit": False, "cache_key": cache_key, "cached_rows": n}
        except Exception as e:  # never let cache write break the live result
            log.warning("cache write failed for %s: %s", sensor_name, e)
            result.metadata = {**(result.metadata or {}), "cache_hit": False, "cache_error": str(e)}
        return result
