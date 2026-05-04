"""Greece-wide standing scan.

A scheduled job that runs once a day, executes a watch covering the whole
of Greek territory + EEZ for the last N days, and persists every fetched
row into the DuckDB fact store. User watches that fall inside the scan's
coverage can then read from the cache instead of re-hitting upstream APIs.

Wired in `backend.main` lifespan: ``StandingScanScheduler.start(executor)``.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config import settings
from backend.models.watch import Watch, WatchDomain, WatchRegion, WatchSpec
from backend.store import get_store

log = logging.getLogger(__name__)

# Greek mainland + EEZ + Aegean + Ionian. min_lon, min_lat, max_lon, max_lat.
# Western Ionian to eastern Aegean, southern Crete waters to the FYROM border.
GREECE_BBOX: tuple[float, float, float, float] = (19.0, 34.5, 29.7, 41.8)


class StandingScanScheduler:
    """Singleton-ish APScheduler wrapper. ``start`` is idempotent."""

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._executor: Any = None  # WatchExecutor — late binding to avoid cycle
        self._inflight: asyncio.Task | None = None
        self._inflight_scan_id: str | None = None

    # ───────────────────────────── lifecycle ──────────────────────────────

    def start(self, executor: Any) -> None:
        if self._scheduler is not None:
            return
        self._executor = executor
        cron = (settings.STANDING_SCAN_CRON or "").strip()
        if not cron:
            log.info("STANDING_SCAN_CRON disabled; standing scans will only run on demand")
            return
        try:
            trigger = CronTrigger.from_crontab(cron, timezone="UTC")
        except ValueError as e:
            log.warning("invalid STANDING_SCAN_CRON %r (%s); scheduler not started", cron, e)
            return
        sched = AsyncIOScheduler(timezone="UTC")
        sched.add_job(self._cron_tick, trigger, id="standing_scan", replace_existing=True)
        sched.start()
        self._scheduler = sched
        log.info("standing scan scheduled: cron=%r tz=UTC", cron)

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        if self._inflight is not None and not self._inflight.done():
            self._inflight.cancel()

    # ─────────────────────────── public triggers ──────────────────────────

    async def trigger_now(self) -> dict[str, Any]:
        """Manual scan request. Idempotent: returns the in-flight scan id if
        one is already running."""
        if self._inflight is not None and not self._inflight.done():
            return {"scan_id": self._inflight_scan_id, "status": "running", "started": "earlier"}
        return await self._launch_scan(kind="manual")

    async def trigger_if_stale(self, max_age_hours: int = 24) -> dict[str, Any] | None:
        """Run a scan iff the most recent successful scan is older than max_age_hours.
        Used at boot — the scheduler may not fire for hours so we top up on cold-start.
        """
        last = self.last_successful()
        if last is not None:
            age = datetime.now(timezone.utc) - _aware(last)
            if age < timedelta(hours=max_age_hours):
                return None
        return await self._launch_scan(kind="standing")

    def status(self) -> dict[str, Any]:
        store = get_store()
        conn = store.connect()
        rows = conn.execute(
            """
            SELECT scan_id, kind, started_at, finished_at, status, sensor_counts_json
              FROM scan_runs ORDER BY started_at DESC LIMIT 5
            """
        ).fetchall()
        history = [
            {
                "scan_id": r[0], "kind": r[1],
                "started_at": _iso(r[2]), "finished_at": _iso(r[3]),
                "status": r[4], "sensor_counts": r[5],
            }
            for r in rows
        ]
        return {
            "scheduler_active": self._scheduler is not None,
            "cron": settings.STANDING_SCAN_CRON,
            "inflight_scan_id": self._inflight_scan_id if (self._inflight and not self._inflight.done()) else None,
            "history": history,
            "freshest_ok": history[0] if history and history[0]["status"] == "ok" else None,
        }

    def last_successful(self) -> datetime | None:
        store = get_store()
        conn = store.connect()
        row = conn.execute(
            "SELECT max(finished_at) FROM scan_runs WHERE status = 'ok'"
        ).fetchone()
        return row[0] if row and row[0] else None

    # ───────────────────────────── internals ──────────────────────────────

    async def _cron_tick(self) -> None:
        if self._inflight is not None and not self._inflight.done():
            log.info("standing scan: previous scan still running; skipping this tick")
            return
        await self._launch_scan(kind="standing")

    async def _launch_scan(self, *, kind: str) -> dict[str, Any]:
        if self._executor is None:
            raise RuntimeError("StandingScanScheduler not started; executor unbound")
        scan_id = f"scan-{uuid.uuid4().hex[:12]}"
        self._inflight_scan_id = scan_id

        async def runner() -> None:
            await self._run_scan(scan_id, kind)

        self._inflight = asyncio.create_task(runner())
        return {"scan_id": scan_id, "status": "running", "started": "now"}

    async def _run_scan(self, scan_id: str, kind: str) -> None:
        store = get_store()
        time_to = datetime.now(timezone.utc).replace(microsecond=0)
        time_from = time_to - timedelta(days=settings.STANDING_SCAN_DAYS)
        bbox = GREECE_BBOX
        started_at = datetime.now(timezone.utc)

        # Insert the row up-front so the UI sees an in-flight scan.
        conn = store.connect()
        conn.execute(
            """
            INSERT INTO scan_runs
                (scan_id, kind, bbox_min_lon, bbox_min_lat, bbox_max_lon, bbox_max_lat,
                 time_from, time_to, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            [scan_id, kind, *bbox, time_from, time_to, started_at],
        )

        spec = WatchSpec(
            region=WatchRegion.CUSTOM,
            custom_bbox=list(bbox),
            domain=WatchDomain.MULTI,
            time_window_days=settings.STANDING_SCAN_DAYS,
            keywords=[],
        )
        watch = Watch(raw_query=f"[STANDING] Greece full coverage — last {settings.STANDING_SCAN_DAYS} days", spec=spec)

        sensor_counts: dict[str, int] = {}
        status = "ok"
        error: str | None = None
        try:
            log.info("standing scan %s: starting (bbox=%s, %dd)", scan_id, bbox, settings.STANDING_SCAN_DAYS)
            async for evt in self._executor.execute(watch, scan_id=scan_id):
                stage = evt.get("stage", "")
                if stage.endswith("_sensor") and evt.get("status") == "complete":
                    name = stage.removesuffix("_sensor")
                    msg = evt.get("message", "")
                    if ":" in msg:
                        try:
                            n_part = msg.split(":", 1)[1].strip().split()[0]
                            sensor_counts[name] = int(n_part)
                        except (ValueError, IndexError):
                            pass
        except Exception as exc:  # pragma: no cover — we want the scan to land *something* in the DB
            log.exception("standing scan %s failed", scan_id)
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"

        finished_at = datetime.now(timezone.utc)
        import json
        conn.execute(
            """
            UPDATE scan_runs
               SET finished_at = ?, status = ?, sensor_counts_json = ?, error = ?
             WHERE scan_id = ?
            """,
            [finished_at, status, json.dumps(sensor_counts), error, scan_id],
        )
        log.info("standing scan %s: %s in %.1fs (counts=%s)",
                 scan_id, status, (finished_at - started_at).total_seconds(), sensor_counts)


_singleton: StandingScanScheduler | None = None


def get_scheduler() -> StandingScanScheduler:
    global _singleton
    if _singleton is None:
        _singleton = StandingScanScheduler()
    return _singleton


# ────────────────────────────── helpers ──────────────────────────────

def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
