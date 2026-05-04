"""Live AIS smoke test — capture ~30 s of broadcasts over a busy Aegean patch.

Confirms that:
  - the AISStream API key authenticates
  - the WebSocket subscription frame is well-formed
  - PositionReport messages parse into AISRecord objects
  - we receive non-zero traffic over a known busy bbox

Then it shows what a cross-reference would look like by inventing a fake SAR
detection at the centroid of one of the captured AIS records — verifying the
matcher pairs them up correctly.

This script makes ONE live network connection and runs for ~30 s. Cost: zero
(AISStream free tier covers this comfortably).
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from backend.models.event import AISStatus, Vessel
from backend.sensors.ais import AISStreamClient
from backend.sensors.dark_vessel import cross_reference

console = Console()


async def main() -> int:
    bbox = (22.0, 35.0, 28.0, 42.0)   # full Aegean — very busy at any time of day
    duration = 30.0

    console.print("[bold]Live AIS capture[/]")
    console.print(f"  bbox     : {bbox}")
    console.print(f"  duration : {duration:.0f} s")
    console.print()

    client = AISStreamClient(bbox=bbox)
    records = await client.capture(duration_seconds=duration)

    if not records:
        console.print("[yellow]No AIS records received in the capture window.[/]")
        console.print("Possible causes: API key invalid, bbox empty, AISStream down. Check connectivity:")
        console.print("  uv run python scripts/verify_sources.py")
        return 1

    unique_mmsi = {r.mmsi for r in records}
    console.print(f"[green]Captured {len(records)} broadcasts from {len(unique_mmsi)} unique vessels[/]")
    console.print()

    # Show the most-active 8 vessels
    by_mmsi: dict[str, list] = {}
    for r in records:
        by_mmsi.setdefault(r.mmsi, []).append(r)
    most_active = sorted(by_mmsi.items(), key=lambda kv: -len(kv[1]))[:8]

    table = Table(title=f"Top {len(most_active)} most-active vessels in the Aegean right now")
    table.add_column("#", justify="right")
    table.add_column("MMSI")
    table.add_column("Name")
    table.add_column("lat",  justify="right")
    table.add_column("lon",  justify="right")
    table.add_column("sog",  justify="right")
    table.add_column("cog",  justify="right")
    table.add_column("msgs", justify="right")
    for i, (mmsi, recs) in enumerate(most_active, 1):
        last = recs[-1]
        table.add_row(
            str(i), mmsi, (last.name or "-")[:24],
            f"{last.lat:.4f}", f"{last.lon:.4f}",
            f"{last.sog_knots:.1f}" if last.sog_knots is not None else "-",
            f"{last.cog_deg:.0f}" if last.cog_deg is not None else "-",
            str(len(recs)),
        )
    console.print(table)
    console.print()

    # ─── Cross-reference smoke test ──────────────────────────────────────────
    # Plant a fake SAR detection AT one of the captured AIS positions; the
    # matcher must pair it (BROADCASTING). Plant another in the middle of the
    # Aegean far from any AIS; the matcher must mark it DARK.
    if records:
        first = records[0]
        fake_sar_at_ais = Vessel(
            lat=first.lat, lon=first.lon, timestamp=first.timestamp,
            detection_source="SAR", confidence=0.9, length_m=80.0,
        )
        fake_sar_dark = Vessel(
            lat=37.5, lon=27.0,                # eastern Aegean median line
            timestamp=datetime.now(tz=timezone.utc),
            detection_source="SAR", confidence=0.9, length_m=120.0,
        )
        out = cross_reference([fake_sar_at_ais, fake_sar_dark], records)
        console.print("[bold]Cross-reference smoke test[/]")
        console.print(f"  fake_at_AIS_position -> {out[0].ais_status.value} (mmsi={out[0].mmsi}, dist={out[0].ais_match_distance_km} km)")
        console.print(f"  fake_far_from_AIS    -> {out[1].ais_status.value} (dark_score={out[1].dark_vessel_score})")

        ok = (
            out[0].ais_status == AISStatus.BROADCASTING and
            out[1].ais_status == AISStatus.DARK
        )
        if not ok:
            console.print("[red]Cross-reference produced unexpected statuses![/]")
            return 2

    console.print()
    console.print("[bold green]Day 5 end-to-end OK[/] — AIS capture + cross-reference work.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
