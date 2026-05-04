"""WebSocket progress stream.

GET ws://.../ws/watches/{watch_id}
    Streams progress events from the in-memory broker as JSON. Buffered
    events arrive first (so a late-joining client catches up); live events
    follow until the pipeline emits ``stage=complete`` or the client
    disconnects.

This is single-process only — multi-worker deployment requires a Redis
pub/sub bridge. Documented as a limitation.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ._broker import broker

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/watches/{watch_id}")
async def watch_progress(websocket: WebSocket, watch_id: str) -> None:
    await websocket.accept()
    try:
        async for event in broker.subscribe(watch_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        log.info("WS subscriber for watch %s disconnected", watch_id)
    except Exception:
        log.exception("WS error for watch %s", watch_id)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    else:
        try:
            await websocket.close()
        except Exception:
            pass
