"""Area of Interest model — AI-inferred or analyst-drawn polygons."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AoISource(str, Enum):
    AI = "ai"
    USER = "user"


class AoI(BaseModel):
    """A named polygon. AI ones come from clustering composite events;
    user ones from analyst drawing on the map.
    """
    id: str = Field(default_factory=lambda: f"aoi-{uuid.uuid4().hex[:10]}")
    source: AoISource = AoISource.AI
    name_el: str
    name_en: str | None = None
    description: str | None = None
    polygon_wkt: str
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    threat_grade: Literal["GREEN", "AMBER", "RED"] | None = None
    threat_summary: str | None = None
    citation_event_ids: list[str] = Field(default_factory=list)
    scan_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
