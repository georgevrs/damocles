"""Sensor abstraction.

Sensors *collect*. They produce typed event objects (Vessel, NewsEvent, ...).
They do not reason — that is the job of the agent layer. They do not write to
the graph directly — that is the job of ``backend.graph.ingestion``.

A sensor takes a time window + spatial bbox and returns a SensorResult
containing the events it detected and metadata about the acquisition (which
tiles, which API calls, latency, etc.). The metadata is what the audit log
hashes; that's what makes the citation chain auditable down to the raw fetch.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

T = TypeVar("T")  # event type — Vessel, NewsEvent, SocialSignal, AirspaceEvent

# bbox = (min_lon, min_lat, max_lon, max_lat) — matches WatchSpec.get_bbox()
BBox = tuple[float, float, float, float]


@dataclass
class SensorResult(Generic[T]):
    """Output of a sensor run.

    ``events`` are typed Pydantic models ready for graph ingestion.
    ``metadata`` is everything the audit log needs to reproduce or verify
    the fetch (tile IDs, query parameters, response sizes, durations).
    """
    sensor_name: str
    events: list[T]
    bbox: BBox
    time_from: datetime
    time_to: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def __len__(self) -> int:
        return len(self.events)


class BaseSensor(ABC, Generic[T]):
    """All sensors implement this interface.

    Concrete subclasses live in ``backend.sensors.<name>`` and are wired into
    the WatchExecutor pipeline.
    """

    name: str = "base"

    @abstractmethod
    async def fetch(
        self,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        **kwargs: Any,
    ) -> SensorResult[T]:
        """Fetch + process. Returns a SensorResult; never raises on no-data —
        empty list is a valid outcome. Raises only on hard errors (auth,
        network failure, malformed response)."""
