"""WebSocket progress stream.

GET ws://.../ws/watches/{watch_id}
    Streams progress events from the in-memory broker as JSON. Buffered
    events arrive first (so a late-joining client catches up); live events
    follow until the pipeline emits ``stage=complete`` or the client
    disconnects.

GET ws://.../ws/scan-cinema?delay_ms=200
    W3-T4 scan-cinema replay. Pushes every persisted AoI as a separate
    GeoJSON Feature event with a configurable delay between each, so the
    map can animate the snapshot into existence as if a live standing
    scan were surfacing them in real time. Deterministic, snapshot-driven,
    no live sensor calls — the demo can't afford network unknowns.

This is single-process only — multi-worker deployment requires a Redis
pub/sub bridge. Documented as a limitation.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.aoi import _wkt_to_geojson
from backend.config import settings
from backend.store import get_store

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


# ─── W3-T4 scan cinema ──────────────────────────────────────────────────────
def _aoi_replay_rows() -> list[tuple[str, str, str | None, str | None, str]]:
    """Return all persisted AoIs ordered so the cinema reveals REDs last.

    RED appearing at the climax of the reveal is the demo affordance the
    speaker leans on: *"... and the standing scan has just surfaced six
    Areas of Interest scored RED."*
    """
    conn = get_store().connect()
    rows = conn.execute(
        """
        SELECT id, threat_grade, name_el, name_en, polygon_wkt
          FROM aoi
         WHERE polygon_wkt IS NOT NULL AND source = 'ai'
         ORDER BY CASE threat_grade WHEN 'GREEN' THEN 0 WHEN 'AMBER' THEN 1
                                    WHEN 'RED' THEN 2 ELSE 0 END,
                  id
        """
    ).fetchall()
    return rows


@router.websocket("/ws/scan-cinema")
async def scan_cinema(websocket: WebSocket) -> None:
    """Stream every snapshot AoI as a GeoJSON Feature with paced delivery.

    Query params:
      ``delay_ms`` (default 180, clamped 30..600) — milliseconds between
        consecutive feature events. Caller picks the pace; the backend
        clamps to keep the replay between ~0.5s and ~20s for ~80 AoIs.

    The endpoint is open in any mode — the data being replayed is the
    same data the regular ``/api/aoi`` endpoint serves, just paced.
    """
    await websocket.accept()
    try:
        delay_ms = int(websocket.query_params.get("delay_ms", 180))
        delay_ms = max(30, min(600, delay_ms))
        rows = _aoi_replay_rows()
        total = len(rows)

        await websocket.send_json({
            "type":  "start",
            "total": total,
            "demo":  bool(settings.DEMO_MODE),
        })

        for idx, (aoi_id, threat, name_el, name_en, wkt) in enumerate(rows):
            geometry = _wkt_to_geojson(wkt) if wkt else None
            if not geometry or not geometry.get("coordinates"):
                continue
            await websocket.send_json({
                "type":  "aoi",
                "index": idx,
                "total": total,
                "feature": {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "id":           aoi_id,
                        "threat_grade": threat,
                        "name_el":      name_el,
                        "name_en":      name_en,
                        "source":       "ai",
                    },
                },
            })
            await asyncio.sleep(delay_ms / 1000.0)

        await websocket.send_json({"type": "complete", "total": total})
    except WebSocketDisconnect:
        log.info("scan-cinema client disconnected")
    except Exception:
        log.exception("scan-cinema error")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    else:
        try:
            await websocket.close()
        except Exception:
            pass
