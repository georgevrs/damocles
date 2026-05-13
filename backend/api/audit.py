"""Audit log endpoints.

GET  /api/audit           recent entries + chain verification verdict
GET  /api/audit/verify    full chain verify (slower, walks the entire log)
POST /api/audit/_tamper   DEMO_MODE only — flip a byte in the chain (W3-T1)
POST /api/audit/_restore  DEMO_MODE only — put the chain back as it was

The tamper/restore pair is the gold-medal moment in the pitch. The speaker
clicks Tamper byte, the verdict flips to TAMPER detected, then Restore +
Verify chain returns it to green — proving the chain is real, not a prop.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.audit.logger import MerkleAuditLogger
from backend.config import settings

from ._serialize import jsonable

router = APIRouter(prefix="/api/audit", tags=["audit"])

# In-memory snapshot of the JSONL file taken at tamper time, so /restore is a
# pure replay. Keyed by absolute log-file path so multiple test runs can't
# bleed into each other. Cleared on restore.
_TAMPER_BACKUP: dict[str, bytes] = {}


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


# ─── DEMO ONLY: tamper / restore ────────────────────────────────────────────
def _flip_hex_byte(h: str) -> str:
    """Flip the first hex character of a SHA-256 hexdigest deterministically.

    Used by /_tamper to make a chain link no longer verify. The flip rule
    ('0'→'1', everything else →'0') is reversible by /_restore replaying the
    in-memory backup, so this is *not* a real attack primitive — it just
    breaks the chain at one defined position for the demo.
    """
    if not h:
        return h
    head = "1" if h[0] == "0" else "0"
    return head + h[1:]


@router.post("/_tamper")
async def tamper_chain(request: Request) -> dict[str, Any]:
    """Flip a byte in a middle-of-chain entry's ``chain_hash`` on disk.

    The frontend's "Tamper byte" button calls this, then /verify. The
    verdict flips from OK to "TAMPER detected at index N". Hitting
    /_restore replays the original file from the in-memory backup.

    Gated on ``settings.DEMO_MODE`` — returns 404 outside demo mode so
    production deployments don't expose a self-tampering endpoint.

    Picks the middle entry on purpose: the logger's in-memory
    ``_last_hash`` is the LAST entry's chain_hash, so tampering anywhere
    upstream of that leaves new appends well-formed.
    """
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="not available")

    log_path: Path = settings.audit_log_path
    if not log_path.exists():
        raise HTTPException(status_code=400, detail="audit log file does not exist yet")

    raw = log_path.read_bytes()
    lines = [ln for ln in raw.split(b"\n") if ln.strip()]
    if len(lines) < 3:
        raise HTTPException(
            status_code=400,
            detail=f"chain too short to tamper ({len(lines)} entries) — need ≥3",
        )

    # Snapshot the file as-is so /_restore is a byte-for-byte replay.
    # Keep both an in-memory copy (fast path) and a sibling ``.demobak``
    # file so the chain is recoverable across backend restarts — without
    # the on-disk copy, tamper-then-restart-then-restore leaves the
    # JSONL stuck in a broken state with no way back.
    _TAMPER_BACKUP[str(log_path.resolve())] = raw
    backup_path = log_path.with_suffix(log_path.suffix + ".demobak")
    backup_path.write_bytes(raw)

    # Tamper the middle entry — never the last, so the logger's _last_hash
    # remains correct and any post-tamper appends stay well-formed.
    target_idx = len(lines) // 2
    entry = json.loads(lines[target_idx].decode("utf-8"))
    original_chain_hash = entry.get("chain_hash", "")
    tampered = _flip_hex_byte(original_chain_hash)
    entry["chain_hash"] = tampered
    lines[target_idx] = json.dumps(entry, separators=(",", ":")).encode("utf-8")

    log_path.write_bytes(b"\n".join(lines) + b"\n")

    audit_logger: MerkleAuditLogger | None = getattr(request.app.state, "audit", None)
    verified, first_bad_idx, total = (False, None, len(lines))
    if audit_logger is not None:
        verified, first_bad_idx, total = await audit_logger.verify()

    return {
        "tampered":          True,
        "tampered_index":    target_idx,
        "entry_id":          entry.get("id"),
        "original_chain":    original_chain_hash[:16] + "…",
        "tampered_chain":    tampered[:16] + "…",
        "verified":          verified,
        "first_bad_index":   first_bad_idx,
        "chain_total":       total,
        "verdict": (
            f"TAMPER injected at index {target_idx}; verify reports first_bad={first_bad_idx}"
        ),
    }


@router.post("/_restore")
async def restore_chain(request: Request) -> dict[str, Any]:
    """Replay the pre-tamper snapshot back onto disk."""
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="not available")

    log_path: Path = settings.audit_log_path
    backup = _TAMPER_BACKUP.pop(str(log_path.resolve()), None)
    backup_path = log_path.with_suffix(log_path.suffix + ".demobak")
    if backup is None and backup_path.exists():
        # Backend restarted between tamper and restore — pick up the
        # on-disk backup so the chain is still recoverable.
        backup = backup_path.read_bytes()
    if backup is None:
        raise HTTPException(
            status_code=400,
            detail="no tamper backup on record — nothing to restore",
        )

    log_path.write_bytes(backup)
    # Remove the on-disk backup now that we've recovered — leaving it
    # around would allow a stale snapshot to overwrite legitimate later
    # appends if /_restore were called a second time.
    if backup_path.exists():
        try:
            backup_path.unlink()
        except OSError:
            pass

    audit_logger: MerkleAuditLogger | None = getattr(request.app.state, "audit", None)
    verified, first_bad_idx, total = (False, None, 0)
    if audit_logger is not None:
        verified, first_bad_idx, total = await audit_logger.verify()

    return {
        "restored":          True,
        "verified":          verified,
        "first_bad_index":   first_bad_idx,
        "chain_total":       total,
        "verdict": (
            "Chain restored — every link rehashes correctly" if verified else
            f"Restore wrote bytes back but verify still fails at {first_bad_idx}"
        ),
    }
