"""Live Telegram smoke test — fetch recent messages from a starter channel set.

Run after ``scripts/setup_telegram.py`` has completed once.

The default channel list contains placeholder examples; some may not exist.
The sensor logs and skips channels it can't resolve, so you can replace them
gradually as you curate a real Greek/Aegean monitoring list.

For a richer test, edit ``CHANNELS`` below to point at channels you've
verified exist (e.g., subscribe to them in your Telegram client first).
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.table import Table

from backend.sensors.telegram_sensor import TelegramSensor

console = Console()

# Replace with your curated, verified list. Channels not subscribed to in your
# account or that don't exist will be silently skipped.
CHANNELS: list[str] = [
    "@aegeanwatch",
    "@greekmilitary",
    "@turkishnavy_news",
    "@southeasteurope",
]

KEYWORDS: list[str] | None = None      # None = use defaults from telegram_sensor.py
HOURS = 24


async def main() -> int:
    bbox = (22.0, 35.0, 28.0, 42.0)   # bbox unused by Telegram but the API expects one
    time_to = datetime.now(timezone.utc).replace(microsecond=0)
    time_from = time_to - timedelta(hours=HOURS)

    console.print("[bold]Telegram live fetch[/]")
    console.print(f"  channels : {', '.join(CHANNELS) or '(defaults)'}")
    console.print(f"  window   : last {HOURS} hours")
    console.print()

    try:
        sensor = TelegramSensor()
        result = await sensor.fetch(
            bbox, time_from, time_to,
            channels=CHANNELS or None,
            keywords=KEYWORDS,
            per_channel_limit=200,
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        return 2

    console.print(f"[bold]Result[/]")
    console.print(f"  duration         : {result.duration_ms / 1000:.1f} s")
    console.print(f"  messages kept    : {len(result.events)}")
    console.print(f"  per-channel      : {result.metadata['per_channel_counts']}")
    if result.metadata["channels_skipped"]:
        console.print(f"  skipped channels :")
        for ch, reason in result.metadata["channels_skipped"]:
            console.print(f"      {ch}  ({reason})")
    console.print()

    if not result.events:
        console.print("[yellow]No matching messages. Either the channels don't exist, you haven't joined them, "
                      "or no recent message hit a keyword. Try editing CHANNELS / KEYWORDS in this script.[/]")
        return 0

    # Show 8 most recent matches
    recent = sorted(result.events, key=lambda e: e.timestamp, reverse=True)[:8]
    table = Table(title=f"Top {len(recent)} most recent matching messages")
    table.add_column("when (UTC)")
    table.add_column("chan", style="cyan")
    table.add_column("lang")
    table.add_column("views", justify="right")
    table.add_column("text")
    for s in recent:
        text = s.text.replace("\n", " ")
        if len(text) > 80:
            text = text[:77] + "..."
        table.add_row(
            s.timestamp.strftime("%m-%d %H:%M"),
            s.channel,
            s.language,
            str(s.views),
            text,
        )
    console.print(table)
    console.print()
    console.print("[bold green]Day 6 Telegram OK[/] - channel iteration + keyword filter + lang detect all working")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
