"""MerkleAuditLogger tests.

Covers:
  - hash primitives (canonical encoding stability, chain hash math)
  - verify_chain on healthy + tampered + reordered + truncated chains
  - logger append + auto-bootstrap from JSONL on startup
  - concurrent log() under asyncio.Lock keeps the chain linear
  - cross-restart continuity: a second logger picks up from the first's last hash
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.audit.logger import (
    GENESIS_HASH,
    MerkleAuditLogger,
    canonical_payload,
    hash_chain,
    hash_payload,
    verify_chain,
)
from backend.models.audit import AuditEntry


# ───────────────────────────────────────────────────────────────────────────────
# Pure primitives
# ───────────────────────────────────────────────────────────────────────────────
def test_canonical_payload_is_key_order_invariant():
    a = {"a": 1, "b": 2, "nested": {"x": 1, "y": 2}}
    b = {"nested": {"y": 2, "x": 1}, "b": 2, "a": 1}
    assert canonical_payload(a) == canonical_payload(b)


def test_hash_payload_changes_when_content_changes():
    h1 = hash_payload({"x": 1})
    h2 = hash_payload({"x": 2})
    assert h1 != h2
    assert len(h1) == 64   # sha256 hex


def test_hash_chain_is_deterministic_and_distinct():
    assert hash_chain("aa", "bb") == hash_chain("aa", "bb")
    assert hash_chain("aa", "bb") != hash_chain("bb", "aa")


# ───────────────────────────────────────────────────────────────────────────────
# verify_chain
# ───────────────────────────────────────────────────────────────────────────────
def _build_chain(payloads: list[dict]) -> list[AuditEntry]:
    entries: list[AuditEntry] = []
    prev = GENESIS_HASH
    for i, p in enumerate(payloads):
        ph = hash_payload(p)
        ch = hash_chain(ph, prev)
        entries.append(AuditEntry(
            id=f"id-{i}",
            timestamp=datetime(2024, 3, 17, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=i),
            action_type=f"act{i}", actor="test",
            payload_hash=ph, previous_hash=prev, chain_hash=ch,
        ))
        prev = ch
    return entries


def test_verify_intact_chain():
    chain = _build_chain([{"x": 1}, {"x": 2}, {"x": 3}])
    ok, idx = verify_chain(chain)
    assert ok is True
    assert idx is None


def test_verify_detects_payload_tamper():
    """Modify payload_hash on an entry → chain_hash no longer matches → bad index returned."""
    chain = _build_chain([{"x": 1}, {"x": 2}, {"x": 3}])
    chain[1].payload_hash = hash_payload({"x": 999})   # attacker rewrites the payload
    ok, idx = verify_chain(chain)
    assert ok is False
    assert idx == 1


def test_verify_detects_skipped_entry():
    """Drop the middle entry — entry[2]'s previous_hash no longer matches entry[1]'s chain_hash."""
    chain = _build_chain([{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4}])
    truncated = [chain[0], chain[2], chain[3]]
    ok, idx = verify_chain(truncated)
    assert ok is False
    assert idx == 1


def test_verify_detects_reorder():
    """Swap two entries — both will fail at the chain link."""
    chain = _build_chain([{"x": 1}, {"x": 2}, {"x": 3}])
    chain[1], chain[2] = chain[2], chain[1]
    ok, idx = verify_chain(chain)
    assert ok is False
    assert idx == 1


def test_verify_empty_chain_is_ok():
    ok, idx = verify_chain([])
    assert ok is True
    assert idx is None


# ───────────────────────────────────────────────────────────────────────────────
# Logger append + JSONL persistence
# ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_log_appends_to_jsonl_with_chain_intact(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    logger = MerkleAuditLogger(log_file_path=log_path)
    e1 = await logger.log("watch.created", "system", {"id": "w1"})
    e2 = await logger.log("agent.run",     "geospatial_agent", {"composite": "ce1"})
    e3 = await logger.log("brief.ingested","supervisor", {"brief": "b1", "sections": 9})

    # Chain links forward
    assert e1.previous_hash == GENESIS_HASH
    assert e2.previous_hash == e1.chain_hash
    assert e3.previous_hash == e2.chain_hash

    # JSONL has 3 lines, each parses as an AuditEntry
    raw_lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l]
    assert len(raw_lines) == 3
    parsed = [AuditEntry(**json.loads(l)) for l in raw_lines]
    ok, idx = verify_chain(parsed)
    assert ok and idx is None


@pytest.mark.asyncio
async def test_logger_rejects_when_no_backend_supplied():
    with pytest.raises(ValueError, match="at least one of"):
        MerkleAuditLogger()


# ───────────────────────────────────────────────────────────────────────────────
# Bootstrap continuity across restarts
# ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_second_logger_picks_up_from_existing_jsonl(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"

    # First logger writes a couple of entries.
    a = MerkleAuditLogger(log_file_path=log_path)
    e_a1 = await a.log("first",  "actor1", {"k": "v1"})
    e_a2 = await a.log("second", "actor1", {"k": "v2"})

    # Second logger picks up from the JSONL.
    b = MerkleAuditLogger(log_file_path=log_path)
    e_b1 = await b.log("third", "actor2", {"k": "v3"})

    # The new entry must chain to e_a2's chain_hash, not GENESIS.
    assert e_b1.previous_hash == e_a2.chain_hash

    # The full chain (read from JSONL) verifies.
    full = b._read_jsonl()
    ok, idx = verify_chain(full)
    assert ok and idx is None
    assert [e.action_type for e in full] == ["first", "second", "third"]
    _ = e_a1   # silence unused warning


@pytest.mark.asyncio
async def test_bootstrap_from_empty_uses_genesis(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    logger = MerkleAuditLogger(log_file_path=log_path)
    e = await logger.log("first", "actor1", {})
    assert e.previous_hash == GENESIS_HASH


# ───────────────────────────────────────────────────────────────────────────────
# Concurrency
# ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_concurrent_log_keeps_chain_linear(tmp_path: Path):
    """Many parallel log() calls must not race-corrupt the chain."""
    log_path = tmp_path / "audit.jsonl"
    logger = MerkleAuditLogger(log_file_path=log_path)

    async def add(i: int):
        return await logger.log(f"act-{i}", "tester", {"i": i})

    entries = await asyncio.gather(*(add(i) for i in range(50)))
    # Bootstrap path may have ordered them in any arrival order — read from JSONL.
    full = logger._read_jsonl()
    assert len(full) == 50
    ok, idx = verify_chain(full)
    assert ok, f"chain broken at index {idx}"
    # Every chain_hash should be unique (no two payloads collided)
    assert len({e.chain_hash for e in entries}) == 50


# ───────────────────────────────────────────────────────────────────────────────
# verify() async wrapper
# ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_logger_verify_returns_total_and_validity(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    logger = MerkleAuditLogger(log_file_path=log_path)
    await logger.log("a", "x", {})
    await logger.log("b", "x", {})
    ok, bad_idx, total = await logger.verify()
    assert ok is True
    assert bad_idx is None
    assert total == 2
