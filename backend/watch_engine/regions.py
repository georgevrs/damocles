"""Region GeoJSON loader.

Maps WatchRegion enum values to GeoJSON FeatureCollections in ``data/geojson/``.
The frontend MapPanel uses these to render region overlays; the WatchExecutor
attaches them to the Watch object before sensor dispatch.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.models.watch import WatchRegion

_REGION_FILES: dict[WatchRegion, str] = {
    WatchRegion.AEGEAN:      "aegean_sea.geojson",
    WatchRegion.IONIAN:      "ionian_sea.geojson",
    WatchRegion.EVROS:       "evros_border.geojson",
    WatchRegion.EASTERN_MED: "eastern_med.geojson",
}


@lru_cache(maxsize=None)
def load(region: WatchRegion) -> dict[str, Any] | None:
    """Return the region's GeoJSON FeatureCollection, or None if unmapped."""
    fname = _REGION_FILES.get(region)
    if fname is None:
        return None
    path = settings.data_dir / "geojson" / fname
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def all_regions() -> dict[str, dict[str, Any]]:
    """All region GeoJSONs keyed by region value, for the frontend overlay layer."""
    return {r.value: load(r) for r in WatchRegion if load(r) is not None}
