"""Sensor output → Neo4j node ingestion.

Each sensor produces Pydantic event objects; this module persists them as
graph nodes with the right labels and edges.
"""
from __future__ import annotations

import json
import logging

from backend.models.brief import Brief, BriefSection
from backend.models.event import (
    AirspaceEvent,
    CompositeEvent,
    NewsEvent,
    SocialSignal,
    Vessel,
)
from backend.models.watch import Watch

from .client import Neo4jClient

log = logging.getLogger(__name__)


async def ingest_watch(client: Neo4jClient, watch: Watch) -> None:
    await client.run(
        """
        MERGE (w:Watch {id: $id})
        SET w.raw_query  = $raw_query,
            w.region     = $region,
            w.domain     = $domain,
            w.created_at = datetime($created_at),
            w.status     = $status
        """,
        id=watch.id,
        raw_query=watch.raw_query,
        region=watch.spec.region.value,
        domain=watch.spec.domain.value,
        created_at=watch.created_at.isoformat(),
        status=watch.status.value,
    )


async def ingest_vessel(client: Neo4jClient, v: Vessel) -> None:
    await client.run(
        """
        MERGE (n:Vessel {id: $id})
        SET n.lat              = $lat,
            n.lon              = $lon,
            n.timestamp        = datetime($timestamp),
            n.detection_source = $detection_source,
            n.ais_status       = $ais_status,
            n.confidence       = $confidence,
            n.sar_tile_id      = $sar_tile_id,
            n.mmsi             = $mmsi,
            n.vessel_name      = $vessel_name,
            n.flag             = $flag,
            n.length_m         = $length_m
        """,
        id=v.id, lat=v.lat, lon=v.lon, timestamp=v.timestamp.isoformat(),
        detection_source=v.detection_source, ais_status=v.ais_status.value,
        confidence=v.confidence, sar_tile_id=v.sar_tile_id,
        mmsi=v.mmsi, vessel_name=v.vessel_name, flag=v.flag, length_m=v.length_m,
    )


async def ingest_news(client: Neo4jClient, e: NewsEvent) -> None:
    await client.run(
        """
        MERGE (n:NewsEvent {id: $id})
        SET n.source_url      = $source_url,
            n.source_name     = $source_name,
            n.headline        = $headline,
            n.timestamp       = datetime($timestamp),
            n.lat             = $lat,
            n.lon             = $lon,
            n.goldstein_scale = $goldstein_scale,
            n.cameo_code      = $cameo_code,
            n.language        = $language,
            n.mentions        = $mentions
        """,
        **e.model_dump(mode="json"),
    )


async def ingest_social(client: Neo4jClient, s: SocialSignal) -> None:
    await client.run(
        """
        MERGE (n:SocialSignal {id: $id})
        SET n.channel          = $channel,
            n.channel_verified = $channel_verified,
            n.message_id       = $message_id,
            n.text             = $text,
            n.timestamp        = datetime($timestamp),
            n.language         = $language,
            n.views            = $views,
            n.forwards         = $forwards,
            n.has_media        = $has_media,
            n.lat              = $lat,
            n.lon              = $lon
        """,
        **s.model_dump(mode="json"),
    )


async def ingest_airspace(client: Neo4jClient, a: AirspaceEvent) -> None:
    await client.run(
        """
        MERGE (n:AirspaceEvent {id: $id})
        SET n.icao24              = $icao24,
            n.callsign            = $callsign,
            n.lat                 = $lat,
            n.lon                 = $lon,
            n.altitude_m          = $altitude_m,
            n.velocity_ms         = $velocity_ms,
            n.heading             = $heading,
            n.timestamp           = datetime($timestamp),
            n.origin_country      = $origin_country,
            n.suspicious_patterns = $suspicious_patterns
        """,
        **a.model_dump(mode="json"),
    )


async def ingest_composite(
    client: Neo4jClient,
    ce: CompositeEvent,
    watch_id: str,
) -> None:
    """Persist a CompositeEvent and link it to its sources and the parent Watch."""
    await client.run(
        """
        MERGE (ce:CompositeEvent {id: $id})
        SET ce.threat_grade        = $threat_grade,
            ce.confidence          = $confidence,
            ce.corroboration_count = $corroboration_count,
            ce.summary             = $summary,
            ce.created_at          = datetime($created_at),
            ce.centroid_lat        = $centroid_lat,
            ce.centroid_lon        = $centroid_lon
        """,
        id=ce.id, threat_grade=ce.threat_grade.value, confidence=ce.confidence,
        corroboration_count=ce.corroboration_count, summary=ce.summary,
        created_at=ce.created_at.isoformat(),
        centroid_lat=ce.centroid_lat, centroid_lon=ce.centroid_lon,
    )

    # Link Watch -> CompositeEvent
    await client.run(
        """
        MATCH (w:Watch {id: $watch_id})
        MATCH (ce:CompositeEvent {id: $ce_id})
        MERGE (w)-[r:TRIGGERED]->(ce)
        SET r.at = datetime()
        """,
        watch_id=watch_id, ce_id=ce.id,
    )

    # Link CompositeEvent -> source nodes
    for source_id in ce.source_node_ids:
        await client.run(
            """
            MATCH (ce:CompositeEvent {id: $ce_id})
            MATCH (s {id: $source_id})
            MERGE (ce)-[:COMPOSED_OF]->(s)
            """,
            ce_id=ce.id, source_id=source_id,
        )


# ─── Brief ingestion ─────────────────────────────────────────────────────────
async def ingest_brief_section(
    client: Neo4jClient, section: BriefSection, brief_id: str
) -> None:
    """Persist a BriefSection node and link it to its parent Brief and the source
    nodes it cites (CITES edges — the gold-medal citation chain)."""
    await client.run(
        """
        MERGE (bs:BriefSection {id: $id})
        SET bs.section_type      = $section_type,
            bs.text              = $text,
            bs.citation_node_ids = $citation_node_ids,
            bs.confidence        = $confidence,
            bs.agent_source      = $agent_source,
            bs.extra             = $extra
        """,
        id=section.id,
        section_type=section.section_type.value,
        text=section.text,
        citation_node_ids=list(section.citation_node_ids),
        confidence=float(section.confidence or 0.0),
        agent_source=section.agent_source,
        extra=json.dumps(section.extra or {}, default=str),
    )

    # Link Brief -> BriefSection
    await client.run(
        """
        MATCH (b:Brief {id: $brief_id})
        MATCH (bs:BriefSection {id: $section_id})
        MERGE (b)-[:CONTAINS]->(bs)
        """,
        brief_id=brief_id, section_id=section.id,
    )

    # Link BriefSection -> each cited source node (the CITES edges)
    for source_id in section.citation_node_ids:
        await client.run(
            """
            MATCH (bs:BriefSection {id: $section_id})
            MATCH (s {id: $source_id})
            MERGE (bs)-[r:CITES]->(s)
            SET r.node_type = labels(s)[0]
            """,
            section_id=section.id, source_id=source_id,
        )


async def ingest_brief(client: Neo4jClient, brief: Brief) -> None:
    """Persist a Brief and all of its BriefSections, linking each to the
    cited source nodes already present in the graph.
    """
    await client.run(
        """
        MERGE (b:Brief {id: $id})
        SET b.watch_id   = $watch_id,
            b.created_at = datetime($created_at),
            b.metadata   = $metadata
        WITH b
        MATCH (w:Watch {id: $watch_id})
        MERGE (w)-[:PRODUCED]->(b)
        """,
        id=brief.id,
        watch_id=brief.watch_id,
        created_at=brief.created_at.isoformat(),
        metadata=json.dumps(brief.metadata or {}, default=str),
    )

    for section in brief.all_sections():
        await ingest_brief_section(client, section, brief.id)
