"""Audit log entry — Merkle-chained for tamper-evident provenance.

EU AI Act Article 12 (record-keeping for high-risk AI) plus EYP brief
requirement for ιχνηλασιμότητα (traceability).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

GENESIS_HASH = "GENESIS"


class AuditEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action_type: str               # e.g. "watch.created", "agent.run", "llm.call"
    actor: str                     # e.g. "geospatial_agent", "supervisor", analyst email
    payload_hash: str
    previous_hash: str = GENESIS_HASH
    chain_hash: str
    chain_valid: bool = True
