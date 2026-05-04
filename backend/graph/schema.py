"""Neo4j schema — node/edge declarations and uniqueness constraints.

Apply by running ``Neo4jClient.apply_schema()`` once at startup.
"""
from __future__ import annotations

NODE_TYPES = (
    "Watch",
    "Vessel",
    "NewsEvent",
    "SocialSignal",
    "AirspaceEvent",
    "CompositeEvent",
    "BriefSection",
    "Brief",
    "AuditEntry",
)

EDGE_TYPES = (
    "TRIGGERED",       # (Watch)-[:TRIGGERED]->(CompositeEvent)
    "PRODUCED",        # (Watch)-[:PRODUCED]->(Brief)
    "COMPOSED_OF",     # (CompositeEvent)-[:COMPOSED_OF {corr_score}]->(source)
    "CORROBORATES",    # (source)-[:CORROBORATES {score}]->(source)
    "CITES",           # (BriefSection)-[:CITES {node_type}]->(source)
    "CONTAINS",        # (Brief)-[:CONTAINS]->(BriefSection)
    "FOLLOWS",         # (AuditEntry)-[:FOLLOWS]->(AuditEntry) — Merkle chain
)

SCHEMA_CONSTRAINTS: tuple[str, ...] = (
    # Uniqueness on id for every primary node type
    "CREATE CONSTRAINT watch_id          IF NOT EXISTS FOR (n:Watch)          REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT vessel_id         IF NOT EXISTS FOR (n:Vessel)         REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT news_id           IF NOT EXISTS FOR (n:NewsEvent)      REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT social_id         IF NOT EXISTS FOR (n:SocialSignal)   REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT airspace_id       IF NOT EXISTS FOR (n:AirspaceEvent)  REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT composite_id      IF NOT EXISTS FOR (n:CompositeEvent) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT brief_id          IF NOT EXISTS FOR (n:Brief)          REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT brief_section_id  IF NOT EXISTS FOR (n:BriefSection)   REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT audit_id          IF NOT EXISTS FOR (n:AuditEntry)     REQUIRE n.id IS UNIQUE",

    # Lookup performance
    "CREATE INDEX vessel_timestamp  IF NOT EXISTS FOR (n:Vessel)        ON (n.timestamp)",
    "CREATE INDEX news_timestamp    IF NOT EXISTS FOR (n:NewsEvent)     ON (n.timestamp)",
    "CREATE INDEX social_timestamp  IF NOT EXISTS FOR (n:SocialSignal)  ON (n.timestamp)",
    "CREATE INDEX vessel_geo        IF NOT EXISTS FOR (n:Vessel)        ON (n.lat, n.lon)",
    "CREATE INDEX news_geo          IF NOT EXISTS FOR (n:NewsEvent)     ON (n.lat, n.lon)",
    "CREATE INDEX audit_timestamp   IF NOT EXISTS FOR (n:AuditEntry)    ON (n.timestamp)",
)
