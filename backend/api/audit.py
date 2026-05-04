"""Audit log endpoints.

GET /api/audit         recent entries + chain verification verdict
GET /api/audit/verify  full chain verify (slower, walks the entire log)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request

from backend.audit.logger import MerkleAuditLogger

from ._serialize import jsonable

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def list_audit_entries(
    request: Request, hours_back: int = 24, limit: int = 200,
) -> dict[str, Any]:
    """Return recent audit entries + a chain-verification verdict.

    ``verified=True`` means every chain link in the *entire* log re-hashes
    correctly — not just the recent slice. The slice is what's shown; the
    verdict applies to the whole chain because partial-window verification
    is meaningless (an attacker would just edit entries outside the window).
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    audit_logger: MerkleAuditLogger | None = getattr(request.app.state, "audit", None)
    graph = request.app.state.executor.graph if request.app.state.executor else None

    rows = []
    if graph is not None:
        rows = await graph.run(
            """
            MATCH (a:AuditEntry)
            WHERE a.timestamp >= datetime($since)
            RETURN a ORDER BY a.timestamp DESC LIMIT $limit
            """,
            since=since.isoformat(), limit=limit,
        )
    entries = [jsonable(dict(r["a"])) for r in rows]

    # Chain verification on the FULL log (not the slice).
    verified, first_bad_idx, total = (False, None, 0)
    if audit_logger is not None:
        try:
            verified, first_bad_idx, total = await audit_logger.verify()
        except Exception as exc:
            return {
                "entries":      entries,
                "count":        len(entries),
                "hours_back":   hours_back,
                "verified":     False,
                "verify_error": f"{type(exc).__name__}: {exc}",
                "note":         "verify() raised; chain status unknown",
            }

    return {
        "entries":           entries,
        "count":             len(entries),
        "hours_back":        hours_back,
        "verified":          verified,
        "chain_total":       total,
        "first_bad_index":   first_bad_idx,
        "note":              None if total > 0 else "audit log is empty",
    }


@router.get("/verify")
async def verify_chain_endpoint(request: Request) -> dict[str, Any]:
    """Run the chain verifier and return a single verdict.

    This is what the demo's [3:30] script calls live: *"Any parliamentary
    committee can verify this log has not been tampered with."*
    """
    audit_logger: MerkleAuditLogger | None = getattr(request.app.state, "audit", None)
    if audit_logger is None:
        return {"verified": False, "note": "audit logger not initialized"}

    verified, first_bad_idx, total = await audit_logger.verify()
    return {
        "verified":         verified,
        "chain_total":      total,
        "first_bad_index":  first_bad_idx,
        "verdict": (
            "OK — every chain link rehashes correctly" if verified else
            f"TAMPER DETECTED at entry index {first_bad_idx}"
        ),
    }
