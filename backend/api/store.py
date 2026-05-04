"""Store inspection endpoints.

Surfaces what's in the DuckDB fact store. Useful for the topbar "Data store"
badge (rows + freshest timestamp) and for ops/debug.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.store import get_store

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/store", tags=["store"])


@router.get("/stats")
async def stats() -> dict:
    try:
        return get_store().stats()
    except Exception as exc:
        log.exception("store stats failed")
        raise HTTPException(status_code=500, detail=str(exc))
