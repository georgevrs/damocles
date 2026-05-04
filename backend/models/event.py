"""Event models — sensor outputs and the fused CompositeEvent.

These map 1:1 to graph node types in ``backend.graph.schema``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ThreatGrade(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class AISStatus(str, Enum):
    BROADCASTING = "broadcasting"
    DARK = "dark"
    UNKNOWN = "unknown"


class Vessel(BaseModel):
    """A vessel detection — from SAR, AIS, or both."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lat: float
    lon: float
    timestamp: datetime
    detection_source: str  # "SAR" | "AIS" | "both"
    ais_status: AISStatus = AISStatus.UNKNOWN
    confidence: float = 0.0
    sar_tile_id: str | None = None
    mmsi: str | None = None
    vessel_name: str | None = None
    flag: str | None = None
    length_m: float | None = None
    # When ais_status=DARK, this is the suspiciousness score from the dark-vessel
    # cross-reference (base 0.7 + risk-factor boosts). Independent of the CFAR
    # detection confidence. None when broadcasting or status unknown.
    dark_vessel_score: float | None = None
    # Haversine distance to the matched AIS broadcast (km). None when DARK or unknown.
    ais_match_distance_km: float | None = None


class NewsEvent(BaseModel):
    """A GDELT geocoded event."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_url: str
    source_name: str
    headline: str
    timestamp: datetime
    lat: float
    lon: float
    goldstein_scale: float = 0.0
    cameo_code: str = ""
    language: str = "en"
    mentions: int = 1


class SocialSignal(BaseModel):
    """A Telegram message from a monitored public channel."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: str
    channel_verified: bool = False
    message_id: str
    text: str
    timestamp: datetime
    language: str = "und"
    views: int = 0
    forwards: int = 0
    has_media: bool = False
    lat: float | None = None
    lon: float | None = None


class AirspaceEvent(BaseModel):
    """A flight observation from OpenSky."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    icao24: str
    callsign: str | None = None
    lat: float
    lon: float
    altitude_m: float | None = None
    velocity_ms: float | None = None
    heading: float | None = None
    timestamp: datetime
    origin_country: str | None = None
    suspicious_patterns: list[str] = Field(default_factory=list)


class CompositeEvent(BaseModel):
    """The fusion engine's output — corroborated multi-source event.

    A CompositeEvent is what agents reason over. It points back to the constituent
    sensor events via ``source_node_ids``.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    threat_grade: ThreatGrade = ThreatGrade.GREEN
    confidence: float = 0.0
    corroboration_count: int = 1
    summary: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_node_ids: list[str] = Field(default_factory=list)
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    time_window_start: datetime | None = None
    time_window_end: datetime | None = None
