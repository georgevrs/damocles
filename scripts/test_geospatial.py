"""End-to-end smoke test: fetch one real Sentinel-1 tile, run CFAR, save preview.

Patch: ~50×55 km centered over the central Aegean (between Crete and the Cyclades),
where Sentinel-1A IW coverage is dense. Window: last 14 days — long enough that
at least one acquisition will exist regardless of the day this is run on.

Cost: ~5-10 Sentinel Hub processing units. Free tier is 30,000/month, so safe.

Outputs:
- prints tile shape, detection count, top-5 vessels by confidence
- saves PNG preview to data/cache/sar/<tile_id>.png with red boxes on detections
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.table import Table

from backend.sensors.geospatial import GeospatialSensor

console = Console()


async def main() -> int:
    bbox = (25.0, 37.0, 25.5, 37.5)   # central Aegean, ~50×55 km
    time_to = datetime.now(timezone.utc).replace(microsecond=0)
    time_from = time_to - timedelta(days=14)

    console.print(f"[bold]Fetching Sentinel-1 IW tile[/]")
    console.print(f"  bbox        : {bbox}")
    console.print(f"  time window : {time_from.isoformat()}  ->  {time_to.isoformat()}")
    console.print()

    sensor = GeospatialSensor()
    result = await sensor.fetch(bbox, time_from, time_to)

    console.print(f"[bold]Result[/]")
    console.print(f"  duration      : {result.duration_ms:.0f} ms")
    console.print(f"  tiles fetched : {result.metadata.get('tiles', 0)}")
    console.print(f"  image shape   : {result.metadata.get('image_shape')}")
    console.print(f"  detections    : {len(result.events)}")
    if "preview_path" in result.metadata:
        console.print(f"  preview PNG   : {result.metadata['preview_path']}")
    console.print()

    if not result.events:
        console.print("[yellow]No vessels detected. This can happen on a quiet patch — try a larger bbox or different window.[/]")
        return 0

    # Top 5 by confidence
    top = sorted(result.events, key=lambda v: v.confidence, reverse=True)[:5]
    table = Table(title=f"Top {len(top)} vessel detections")
    table.add_column("#", justify="right")
    table.add_column("lat",       justify="right")
    table.add_column("lon",       justify="right")
    table.add_column("length_m",  justify="right")
    table.add_column("conf",      justify="right")
    for i, v in enumerate(top, 1):
        table.add_row(
            str(i),
            f"{v.lat:.5f}",
            f"{v.lon:.5f}",
            f"{v.length_m:.0f}" if v.length_m else "-",
            f"{v.confidence:.2f}",
        )
    console.print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
