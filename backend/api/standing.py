"""Standing-scan endpoints — manual trigger + status."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.watch_engine.standing import get_scheduler

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/standing", tags=["standing"])


@router.get("/status")
async def status() -> dict:
    return get_scheduler().status()


@router.post("/scan")
async def scan() -> dict:
    sched = get_scheduler()
    if sched._executor is None:
        raise HTTPException(status_code=503, detail="executor not ready")
    return await sched.trigger_now()
