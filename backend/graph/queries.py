"""Cypher query library — every read/write the app performs lives here.

Queries are plain strings parametrized at call time. The agents call into
specific functions in this module rather than crafting Cypher directly.
"""
from __future__ import annotations

from typing import Any

from .client import Neo4jClient

# ─── The gold-medal query ────────────────────────────────────────────────────
CYPHER_CITATION_CHAIN = """
MATCH (bs:BriefSection {id: $section_id})
OPTIONAL MATCH (bs)-[:CITES]->(source)
OPTIONAL MATCH (source)<-[:COMPOSED_OF]-(ce:CompositeEvent)
OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(sibling)
WHERE sibling <> source
RETURN bs            AS section,
       collect(DISTINCT source)  AS source_nodes,
       collect(DISTINCT sibling) AS corroboration_chain
"""

# ─── Watch lifecycle ─────────────────────────────────────────────────────────
CYPHER_UPSERT_WATCH = """
MERGE (w:Watch {id: $id})
SET   w.raw_query   = $raw_query,
      w.region      = $region,
      w.domain      = $domain,
      w.created_at  = datetime($created_at),
      w.status      = $status
RETURN w
"""

CYPHER_GET_WATCH = "MATCH (w:Watch {id: $id}) RETURN w"

CYPHER_LIST_WATCHES = """
MATCH (w:Watch)
RETURN w
ORDER BY w.created_at DESC
LIMIT $limit
"""

# ─── Watch results ───────────────────────────────────────────────────────────
CYPHER_WATCH_EVENTS = """
MATCH (w:Watch {id: $watch_id})-[:TRIGGERED]->(ce:CompositeEvent)
OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(source)
RETURN ce, collect(source) AS sources
ORDER BY ce.confidence DESC
"""

# ─── Map / graph visualization ───────────────────────────────────────────────
CYPHER_GRAPH_FOR_WATCH = """
MATCH (w:Watch {id: $watch_id})-[:TRIGGERED]->(ce:CompositeEvent)
OPTIONAL MATCH (ce)-[r:COMPOSED_OF]->(source)
RETURN ce, r, source
"""

CYPHER_GEO_FEATURES_FOR_WATCH = """
MATCH (w:Watch {id: $watch_id})-[:TRIGGERED]->(:CompositeEvent)-[:COMPOSED_OF]->(source)
WHERE source.lat IS NOT NULL AND source.lon IS NOT NULL
RETURN labels(source)[0] AS node_type,
       source.id         AS id,
       source.lat        AS lat,
       source.lon        AS lon,
       source.confidence AS confidence,
       source            AS props
"""

# ─── Audit chain ─────────────────────────────────────────────────────────────
CYPHER_APPEND_AUDIT = """
MERGE (a:AuditEntry {id: $id})
SET   a.timestamp     = datetime($timestamp),
      a.action_type   = $action_type,
      a.actor         = $actor,
      a.payload_hash  = $payload_hash,
      a.previous_hash = $previous_hash,
      a.chain_hash    = $chain_hash,
      a.chain_valid   = $chain_valid
WITH a
OPTIONAL MATCH (prev:AuditEntry {chain_hash: $previous_hash})
FOREACH (_ IN CASE WHEN prev IS NULL THEN [] ELSE [1] END |
    MERGE (a)-[:FOLLOWS]->(prev)
)
RETURN a
"""

CYPHER_AUDIT_CHAIN = """
MATCH (a:AuditEntry)
WHERE a.timestamp >= datetime($from)
RETURN a ORDER BY a.timestamp ASC
"""

# ─── Functions ────────────────────────────────────────────────────────────────
async def get_citation_chain(client: Neo4jClient, section_id: str) -> list[dict[str, Any]]:
    return await client.run(CYPHER_CITATION_CHAIN, section_id=section_id)


async def list_watches(client: Neo4jClient, limit: int = 50) -> list[dict[str, Any]]:
    return await client.run(CYPHER_LIST_WATCHES, limit=limit)


async def get_watch(client: Neo4jClient, watch_id: str) -> dict[str, Any] | None:
    rows = await client.run(CYPHER_GET_WATCH, id=watch_id)
    return rows[0]["w"] if rows else None
