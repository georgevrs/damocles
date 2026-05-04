"""Live GDELT smoke test — last few hours of Greek/Turkish/Cypriot events.

Fetches the GDELT 2.0 master file index, filters to a recent time window,
downloads each 15-min ZIP, and prints the events that pass the
country + CAMEO + bbox filters.

Default: last 3 hours = 12 slots ~= 20-30 MB of downloads. Bump
``HOURS`` for a richer sample.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.table import Table

from backend.sensors.gdelt import GDELTSensor

console = Console()

HOURS = 6


async def main() -> int:
    # GDELT geocodes events to where they HAPPENED, not where they're ABOUT.
    # A Greek-Turkish dispute at the UN geocodes to Geneva, an EU summit decision
    # geocodes to Brussels. For a smoke test we want all events with a Greek/
    # Turkish/Cypriot ACTOR regardless of location, so we pass the global bbox.
    # The seed pipeline (Day 7) will use the real Aegean bbox for stricter filtering.
    bbox = (-180.0, -90.0, 180.0, 90.0)
    time_to = datetime.now(timezone.utc).replace(microsecond=0)
    time_from = time_to - timedelta(hours=HOURS)

    console.print("[bold]GDELT live fetch[/]")
    console.print(f"  bbox     : {bbox}")
    console.print(f"  window   : {time_from.isoformat()}  ->  {time_to.isoformat()}")
    console.print()

    sensor = GDELTSensor()
    result = await sensor.fetch(bbox, time_from, time_to)

    console.print(f"[bold]Result[/]")
    console.print(f"  duration       : {result.duration_ms / 1000:.1f} s")
    console.print(f"  slots fetched  : {result.metadata['slots_fetched']}")
    console.print(f"  bytes downloaded: {result.metadata['bytes_downloaded'] / 1_000_000:.1f} MB")
    console.print(f"  events kept    : {len(result.events)}")
    console.print()

    if not result.events:
        console.print("[yellow]No filtered events. The GDELT pipeline may have a quiet hour, or the window is too short.[/]")
        return 0

    # Sort by goldstein (most negative = most conflictual) and show top 10
    top = sorted(result.events, key=lambda e: e.goldstein_scale)[:10]
    table = Table(title=f"Top {len(top)} most-conflictual events (most-negative Goldstein)")
    table.add_column("#",    justify="right")
    table.add_column("when (UTC)")
    table.add_column("CAMEO", justify="right")
    table.add_column("gold", justify="right")
    table.add_column("ment", justify="right")
    table.add_column("lat",  justify="right")
    table.add_column("lon",  justify="right")
    table.add_column("source")
    for i, e in enumerate(top, 1):
        table.add_row(
            str(i),
            e.timestamp.strftime("%m-%d %H:%M"),
            e.cameo_code,
            f"{e.goldstein_scale:.1f}",
            str(e.mentions),
            f"{e.lat:.2f}",
            f"{e.lon:.2f}",
            e.source_name[:40],
        )
    console.print(table)
    console.print()
    console.print("[bold green]Day 6 GDELT OK[/] - master file fetch + parse + filter all working")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
