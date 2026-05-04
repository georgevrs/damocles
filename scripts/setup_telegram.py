"""One-time interactive Telegram auth.

Run this ONCE before using TelegramSensor:

    uv run python scripts/setup_telegram.py

What happens:
1. Telethon connects to Telegram with your API_ID/API_HASH/PHONE.
2. Telegram sends a one-time login code (in the official Telegram app, or via
   SMS if you don't have the app).
3. You paste the code at the prompt below.
4. The session is pickled to data/cache/telegram/damocles.session.

After that, ``TelegramSensor`` runs unattended. The only time you'll need to
re-run this is if Telegram invalidates the session (revoking the app on
my.telegram.org, or 14+ days of inactivity).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich.console import Console
from telethon import TelegramClient

from backend.config import settings

console = Console()


async def main() -> int:
    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
        console.print("[red]TELEGRAM_API_ID / TELEGRAM_API_HASH not set in .env. See docs/credentials.md §5.[/]")
        return 2
    if not settings.TELEGRAM_PHONE:
        console.print("[red]TELEGRAM_PHONE not set in .env (international format, e.g. +306900000000).[/]")
        return 2

    session_path: Path = settings.cache_dir / "telegram" / "damocles.session"
    session_path.parent.mkdir(parents=True, exist_ok=True)

    console.print("[bold]Telegram interactive auth[/]")
    console.print(f"  api_id       : {settings.TELEGRAM_API_ID}")
    console.print(f"  phone        : {settings.TELEGRAM_PHONE}")
    console.print(f"  session file : {session_path}")
    console.print()
    console.print("Telegram will send a login code to your account.")
    console.print("Enter it at the prompt below. (You may also be asked for a 2FA password if enabled.)")
    console.print()

    client = TelegramClient(str(session_path), int(settings.TELEGRAM_API_ID), settings.TELEGRAM_API_HASH)
    await client.start(phone=settings.TELEGRAM_PHONE)

    me = await client.get_me()
    console.print(f"[green]Authenticated as[/] [bold]{me.first_name}[/] (id={me.id}, username=@{me.username or '-'})")
    await client.disconnect()
    console.print()
    console.print("[bold green]Setup complete.[/] You can now run:")
    console.print("  uv run python scripts/test_telegram.py")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
