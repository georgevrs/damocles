"""Watch endpoints.

POST /api/watches launches the full pipeline as a background task and
returns the watch_id immediately. Clients then connect to
WS /ws/watches/{watch_id} for live progress events, and poll
GET /api/watches/{watch_id} for the final status.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from backend.graph.client import Neo4jClient
from backend.models.watch import Watch
from backend.watch_engine.registry import WATCH_TEMPLATES

from ._broker import broker
from ._serialize import jsonable

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watches", tags=["watches"])


@router.get("/templates")
async def list_templates() -> list[dict]:
    """Quick-launch chips for the WatchInput UI."""
    return WATCH_TEMPLATES


@router.post("", response_model=Watch)
async def create_watch(
    body: dict, request: Request, background: BackgroundTasks,
) -> Watch:
    """Parse a free-text query, persist the Watch, kick off the pipeline.

    Returns the Watch object immediately. The pipeline runs in the
    background and streams progress to ``ws/watches/{watch_id}``.
    """
    raw_query = (body.get("query") or "").strip()
    if not raw_query:
        raise HTTPException(status_code=400, detail="query is required")

    executor = request.app.state.executor
    if executor is None:
        raise HTTPException(
            status_code=503,
            detail="WatchExecutor not initialized — LLM provider or Neo4j unavailable",
        )

    watch = await executor.parse_query(raw_query)

    # Evict stale channels before adding a new one.
    broker.gc()

    # Launch the pipeline as a fire-and-forget task. We attach to the app
    # state's task set to prevent gc and to enable shutdown coordination later.
    task = asyncio.create_task(_run_pipeline(watch, executor))
    request.app.state.pipeline_tasks.add(task)
    task.add_done_callback(request.app.state.pipeline_tasks.discard)
    _ = background  # kept in signature for FastAPI dep injection consistency
    return watch


@router.get("/{watch_id}")
async def get_watch(watch_id: str, request: Request) -> dict[str, Any]:
    """Return Watch metadata + the most recent progress event."""
    rows = await _graph(request).run(
        "MATCH (w:Watch {id: $id}) RETURN w", id=watch_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"watch {watch_id} not found")
    w = rows[0]["w"]
    events = broker.buffered_events(watch_id)
    return jsonable({
        "watch": dict(w),
        "is_done": broker.is_done(watch_id),
        "last_event": events[-1] if events else None,
        "event_count": len(events),
    })


@router.get("")
async def list_watches(request: Request, limit: int = 20) -> list[dict[str, Any]]:
    rows = await _graph(request).run(
        "MATCH (w:Watch) RETURN w ORDER BY w.created_at DESC LIMIT $limit",
        limit=limit,
    )
    return [jsonable(dict(r["w"])) for r in rows]


# ─── Pipeline runner ─────────────────────────────────────────────────────────
async def _run_pipeline(watch: Watch, executor) -> None:
    """Drive the executor, push every yielded event into the broker.

    Caught-and-logged exception path keeps the broker in a sane state — the
    WS subscriber sees a `pipeline / failed` event and closes cleanly.
    """
    try:
        async for event in executor.execute(watch):
            await broker.publish(watch.id, event)
    except Exception as exc:
        log.exception("Watch %s pipeline raised", watch.id)
        await broker.publish(watch.id, {
            "stage":        "pipeline",
            "status":       "failed",
            "detail":       f"{type(exc).__name__}: {exc}",
            "progress_pct": 100,
        })
        # Mark complete so subscribers exit cleanly.
        await broker.publish(watch.id, {
            "stage":        "complete",
            "status":       "failed",
            "detail":       "pipeline aborted",
            "progress_pct": 100,
        })


def _graph(request: Request) -> Neo4jClient:
    g: Neo4jClient = request.app.state.executor.graph
    return g
