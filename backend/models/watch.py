"""Watch — the analyst's query, parsed into a structured spec.

A Watch supports any free-text query. ``WatchParser`` (in ``backend.watch_engine``)
turns the raw string into a ``WatchSpec`` via the LLM provider.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class WatchDomain(str, Enum):
    MARITIME = "maritime"
    BORDER = "border"
    AIRSPACE = "airspace"
    INFORMATION = "information"
    MULTI = "multi"


class WatchRegion(str, Enum):
    AEGEAN = "aegean"
    IONIAN = "ionian"
    EVROS = "evros"
    EASTERN_MED = "eastern_med"
    CUSTOM = "custom"


class WatchStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


# bbox = (min_lon, min_lat, max_lon, max_lat)
_REGION_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "aegean":      (22.0, 35.0, 28.0, 42.0),
    "ionian":      (19.0, 36.0, 23.5, 41.0),
    "evros":       (25.8, 40.8, 26.8, 42.2),
    "eastern_med": (20.0, 30.0, 37.0, 38.0),
}


class WatchSpec(BaseModel):
    """Structured query — produced by WatchParser from raw analyst text."""
    region: WatchRegion = WatchRegion.AEGEAN
    custom_bbox: list[float] | None = None
    domain: WatchDomain = WatchDomain.MULTI
    time_window_days: int = 7
    keywords: list[str] = Field(default_factory=list)
    threat_indicators: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    parse_notes: str | None = None

    def get_bbox(self) -> tuple[float, float, float, float]:
        if self.region == WatchRegion.CUSTOM and self.custom_bbox and len(self.custom_bbox) == 4:
            return tuple(self.custom_bbox)  # type: ignore[return-value]
        return _REGION_BBOXES.get(self.region.value, _REGION_BBOXES["aegean"])


class Watch(BaseModel):
    """A Watch as stored and tracked through its processing lifecycle."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_query: str
    spec: WatchSpec
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: WatchStatus = WatchStatus.PENDING
    brief_id: str | None = None
    error: str | None = None
