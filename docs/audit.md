# Audit — Merkle-chained tamper evidence

The single most-asked-about technical detail in the EYP demo: *"how do you know the log hasn't been tampered with?"*. This document explains the answer.

## Why this exists

Three pressures converge on the audit log:

1. **EU AI Act, Article 12 (record-keeping for high-risk AI)** — high-risk systems must maintain technical logs of their operation that capture model invocations, inputs, outputs, and operator actions, retained for the system's lifetime. Damocles is operationally a high-risk system (national-security analysis affecting persons of interest).
2. **EYP brief — ιχνηλασιμότητα (traceability)** — the request explicitly calls for traceability of every analytical claim back to the data and reasoning that produced it.
3. **Demo theatre at [3:30]** — *"Every model call, every analyst action, hashed and chained. Any parliamentary committee can verify this log has not been tampered with."* The frontend's "Verify chain" button has to actually do something meaningful.

## Architecture

```
Pipeline event (sensor fetch / agent run / citation click / ...)
       ↓
   MerkleAuditLogger.log(action_type, actor, payload)
       ↓
   payload_hash = SHA256( canonical_json(payload) )
   chain_hash   = SHA256( payload_hash + previous_hash )
       ↓
   Append to JSONL file  ←──┐
   Append to Neo4j       ←──┴── two independent stores
       ↓
   _last_hash := chain_hash
```

Verifier walks entries in timestamp order, recomputes `chain_hash` from `(payload_hash, previous_hash)` of each, and returns the index of the first mismatch. O(N) over the whole log.

## The pure-function primitives

[`backend/audit/logger.py`](../backend/audit/logger.py)

```python
GENESIS_HASH = "GENESIS"

def canonical_payload(payload: dict) -> str:
    """Stable JSON encoding for hashing. sort_keys + default=str."""
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))

def hash_payload(payload: dict) -> str:
    return hashlib.sha256(canonical_payload(payload).encode()).hexdigest()

def hash_chain(payload_hash: str, previous_hash: str) -> str:
    return hashlib.sha256((payload_hash + previous_hash).encode()).hexdigest()

def verify_chain(entries: list[AuditEntry]) -> tuple[bool, int | None]:
    """Returns (True, None) if intact, (False, idx) at first tampered entry."""
    expected_prev = GENESIS_HASH
    for i, e in enumerate(entries):
        if e.previous_hash != expected_prev:
            return False, i
        expected = hash_chain(e.payload_hash, e.previous_hash)
        if e.chain_hash != expected:
            return False, i
        expected_prev = e.chain_hash
    return True, None
```

These are pure — no I/O, no async, fully deterministic. They're the foundation of the chain's claims and are unit-tested in isolation ([`tests/test_audit_logger.py`](../tests/test_audit_logger.py) — 14 tests covering tamper detection, reorder detection, truncation, key-order invariance).

## The two-store persistence

```python
class MerkleAuditLogger:
    def __init__(self, *, graph: Neo4jClient | None = None, log_file_path: Path | str | None = None):
        if graph is None and log_file_path is None:
            raise ValueError("Need at least one of `graph` or `log_file_path`")
        ...
```

Both stores are recommended in production. The redundancy is the security model — an attacker has to modify **both** stores **AND keep them consistent** to get away with tampering, which is significantly harder than tampering with a single store.

### JSONL store
- Appends one JSON line per entry to `data/audit_log.jsonl` (configurable via `settings.audit_log_path`)
- Append-only file — easy to back up via `cp`, easy to grep with standard tools
- The simpler / "canonical" store: `read_chain()` and `bootstrap()` prefer it on tied lengths

### Neo4j store
- `(:AuditEntry)` nodes with a `[:FOLLOWS]` edge to the previous entry
- Queryable via Cypher (e.g., "show me all `agent.failed` entries from the last hour")
- Indexed on `timestamp` for fast windowed reads

### Cross-store consistency

The two stores can drift if a Neo4j write fails after the JSONL succeeds. `read_chain()` and `bootstrap()` always pick the **store with more entries** — JSONL wins ties since it's append-only and harder to silently truncate.

This was the bug fixed at the end of Day 14: the e2e test failed audit verification at index 0 because Day 13's smoke had written to JSONL only, then Day 14's executor wrote to both stores, and `read_chain()` was preferring Neo4j (which only had Day-14 entries whose `previous_hash` pointed back to Day-13 hashes that lived only in JSONL). Documented in [limitations.md §5d.6](limitations.md).

A `reconcile` CLI that diffs the two stores and replays missing entries into the lagging one is documented as DEBT but not yet built.

## Concurrency

`log()` is async-safe via `asyncio.Lock`:
```python
async def log(self, action_type, actor, payload):
    if not self._bootstrapped:
        await self.bootstrap()
    async with self._lock:
        payload_h = hash_payload(payload)
        prev_h    = self._last_hash
        chain_h   = hash_chain(payload_h, prev_h)
        # ... persist to both stores ...
        self._last_hash = chain_h
        return entry
```

Without the lock, parallel agent calls could race the `previous_hash → chain_hash → write → update last_hash` sequence and produce a fork in the chain. Test pinned: `test_concurrent_log_keeps_chain_linear` fires 50 parallel `log()` calls and asserts the resulting chain verifies cleanly.

## Bootstrap

On startup, the logger reads both stores, picks the one with more entries (JSONL ties), and sets `_last_hash` to that store's most recent `chain_hash`. New entries chain forward from there.

If both stores are empty: `_last_hash = GENESIS`, the first appended entry's `previous_hash = "GENESIS"`.

The `_bootstrapped` flag prevents re-running on every `log()` call (idempotent, but wasteful).

## What gets logged

The `WatchExecutor` calls `audit.log()` at every stage boundary:

| action_type | actor | payload contents |
| --- | --- | --- |
| `watch.created` | `watch_executor` | `watch_id, raw_query, region, domain, window_days, bbox` |
| `sensor.{name}.fetched` | `{name}_sensor` | `watch_id, event_count, duration_ms` |
| `sensor.{name}.failed` | `{name}_sensor` | `watch_id, error` |
| `fusion.complete` | `fusion_engine` | `watch_id, composites, edges, by_sensor` |
| `agent.{name}.run` | `{name}` | `watch_id, composite_id, confidence, finding_count, citation_count, model` |
| `agent.{name}.failed` | `{name}` | `watch_id, composite_id, error` |
| `agent.devils_advocate.run` | `devils_advocate` | `watch_id, composite_id, confidence, devil_confidence, finding_count, model` |
| `agent.supervisor.run` | `supervisor_agent` | `watch_id, composite_id, brief_id, section_count, model` |
| `brief.ingested` | `supervisor_agent` | `watch_id, brief_id, composite_id, section_count, agents_consulted, bluf_confidence, has_devil, has_recommendation` |
| `brief.citation_accessed` | `analyst` | `brief_id, section_id, section_type, source_count` |
| `agent_layer.failed` | `watch_executor` | `watch_id, error` |

A typical 1-watch run produces ~13 entries. Multi-citation analyst sessions add more `brief.citation_accessed` rows.

**Never logged**: raw LLM outputs (full text), raw sensor data (SAR pixel arrays, AIS positions). Only their hashes and metadata. The full text lives in the structured Brief / SourceNode / Vessel that the chain references — the chain proves *that the artefact was produced and persisted*; the persistence layer holds the artefact.

## Verification — the demo's [3:30] payoff

```python
async def verify(self) -> tuple[bool, int | None, int]:
    """Returns (ok, first_bad_idx, total_count)."""
    entries = await self.read_chain()
    ok, idx = verify_chain(entries)
    return ok, idx, len(entries)
```

Exposed via:

- `GET /api/audit/verify` — REST endpoint, returns `{verified, chain_total, first_bad_index, verdict}`
- The frontend's top-bar `SystemBadges` polls every 15s — the chain status is always-visible
- The `AuditLog` panel has a "Verify chain" button that triggers an immediate refresh

The frontend renders three states:
- **`audit OK · 41`** (emerald) — chain rehashes correctly
- **`audit empty`** (amber) — pre-first-run
- **`TAMPER @ 4`** (red, with bright background) — verify failed at index 4

## The tamper-detection demo

`scripts/test_audit.py` is the live two-pass test:

**PASS A** — populate the chain via the real pipeline:
```
1. smoke.start (smoke_runner)
2. agent.geospatial_agent.run (geospatial_agent)
3. agent.osint_agent.run (osint_agent)
4. agent.devils_advocate.run (devils_advocate)
5. brief.ingested (supervisor_agent)
6. brief.citation_accessed (analyst)
7. brief.citation_accessed (analyst)
8. brief.citation_accessed (analyst)
9. smoke.end (smoke_runner)

verify_chain → (True, None)
```

**PASS B** — deliberately corrupt entry #5's `payload_hash` to all zeros:
```
verify_chain → (False, 4)    ← index 4 = entry #5, exactly the right index

TAMPER DETECTED at the right index
```

Restore the entry → re-verify → `(True, None)` again.

This is the demo's payoff. The "Verify chain" button takes ~50ms to re-walk the whole chain and either returns "OK — every chain link rehashes correctly" or pinpoints the bad index.

## What the chain proves vs. what it doesn't

**It proves**:
- Nobody truncated the chain (you can't drop entries without breaking subsequent `chain_hash` linkages)
- Nobody reordered entries (same reason)
- Nobody rewrote `payload_hash` of any entry (the chain links wouldn't recompute correctly)
- For any specific entry, the action and payload-hash were as recorded *at that moment in time*

**It does NOT prove**:
- That the payload referenced is what it claims to be — payload-tampering (rewrite both the payload itself AND its `payload_hash` AND every downstream `chain_hash`) would re-link correctly. This is detected by the **cross-store consistency** check, not by `verify_chain`. We don't store payloads in the chain itself because that bloats it ~100×.
- That the operator with full host access didn't atomically rewrite both the JSONL and Neo4j stores. A determined operator with root can do this. Standard Merkle-tree systems anchor by publishing the daily root hash to a public timestamp authority — see "External anchoring" below.

## External anchoring (what production needs)

The chain is internally consistent and tamper-evident *given access to the local stores*. To raise the bar against a hostile operator with root:

**Daily root publication.** Publish the current `chain_hash` (the hash of the most recent entry) to a public bulletin every day. Options:
- **OpenTimestamps + Bitcoin** — free, decentralized, the `ots` CLI submits a hash to a calendar server which aggregates and anchors to Bitcoin every ~hour. Verifiable by anyone, no trusted third party.
- **A Greek government PKI** — sign the daily root with a national-PKI key; archive in a public-records system.
- **A git-only mirror** — commit the daily root to a public git repo (`damocles-attestations`). Not as cryptographically strong as Bitcoin anchoring but easy to set up; rewriting committed history is detectable via fork comparisons.

Once a root is anchored externally, **rewriting the local chain to be internally consistent doesn't help the attacker** — the rewritten root won't match the externally anchored one.

This is a Day-21 pre-deployment polish task. Damocles ships today with internal consistency only; the demo's "parliamentary committee" claim holds against any party WITHOUT root on the host. Worth being precise in the live pitch.

## Audit log retention

No GC today. The chain grows unboundedly. A 7-day window with one watch/day produces ~50-100 entries; a long-running deployment with many analysts could accumulate millions over a year.

Production plan: epoch the chain quarterly. Each new epoch's first entry has `previous_hash = chain_hash_of_last_entry_in_previous_epoch`. The closed epoch is moved to cold storage, with the closing root anchored externally. The "live" chain stays small and fast to verify.

Documented as DEBT in [limitations.md §5d.4](limitations.md).

## Future hardening — what production needs

1. **Authenticated `actor` field** ([§5d.1](limitations.md)) — today the `actor` is a literal string set by the executor. Production needs OIDC/SAML auth flowing through to a verified principal in every audit row. Possibly per-actor signing of the entry so even an operator with full DB access can't forge another actor's row.
2. **Cross-store reconcile CLI** — a tool that diffs JSONL ↔ Neo4j and replays missing entries into the lagging store. ~50 lines.
3. **External anchoring** — daily root to OpenTimestamps or a national PKI (above).
4. **Epoch GC** — quarterly chain rollover with cold-storage archival.
5. **Audit query API** — Cypher for the analyst to run ad-hoc filters: "show me every `brief.citation_accessed` from analyst X this week". Today the audit endpoint returns chronological slices only.

## Reading the chain manually

```cypher
// recent entries, newest first
MATCH (a:AuditEntry)
WHERE a.timestamp >= datetime() - duration('PT1H')
RETURN a.timestamp, a.action_type, a.actor, a.chain_hash
ORDER BY a.timestamp DESC

// every model invocation in the last 24 hours
MATCH (a:AuditEntry)
WHERE a.action_type STARTS WITH 'agent.' AND a.action_type ENDS WITH '.run'
  AND a.timestamp >= datetime() - duration('P1D')
RETURN a

// all brief citations accessed by analysts
MATCH (a:AuditEntry {actor: 'analyst', action_type: 'brief.citation_accessed'})
RETURN a ORDER BY a.timestamp DESC

// walk the Merkle chain edges
MATCH path = (start:AuditEntry)-[:FOLLOWS*..50]->(end:AuditEntry)
WHERE NOT (end)-[:FOLLOWS]->()
RETURN length(path), end.chain_hash
```

The Cypher library in [`backend/graph/queries.py`](../backend/graph/queries.py) has `CYPHER_AUDIT_CHAIN` for the windowed read.

## What "Verify chain" actually does, step by step

When the analyst clicks the button:
1. Frontend `verifyAuditChain()` calls `GET /api/audit/verify`
2. Endpoint calls `MerkleAuditLogger.verify()`
3. `read_chain()` reads from whichever store has more entries (JSONL or Neo4j)
4. `verify_chain()` walks the entries in timestamp order, recomputing `chain_hash = SHA256(payload_hash + previous_hash)` for each
5. First mismatch → return `(False, index)`. All match → return `(True, None)`
6. Endpoint shapes a parliamentary-committee-friendly verdict string
7. Frontend renders the result in the badge (top bar) AND the panel banner (bottom right)

50ms for ~100 entries. ~500ms for 10k entries. Fast enough to run on every page load if needed.

## Test coverage

[`tests/test_audit_logger.py`](../tests/test_audit_logger.py) — 14 tests:
- Hash primitive stability (key-order invariance, content sensitivity, SHA-256 length)
- `verify_chain` correctness on intact / payload-tampered / reordered / truncated / empty chains
- JSONL append: shape, structure, parses back to `AuditEntry`
- Constructor rejects when no backend supplied
- Cross-restart continuity: a second logger picks up from the first's last hash
- Bootstrap from empty → uses GENESIS
- **Concurrency**: 50 parallel `log()` calls under `asyncio.Lock` produce a verifiable chain
- `verify()` async wrapper returns `(ok, first_bad_idx, total_count)`

All deterministic. No network, no Neo4j, no LLM. Fast (<1 s for the whole file).

The live tamper test ([`scripts/test_audit.py`](../scripts/test_audit.py)) covers the cross-cutting integration: real pipeline → real audit chain → real tamper → real recovery.
