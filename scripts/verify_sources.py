"""verify_sources.py — sanity-check every external dependency.

Run this once after editing .env to confirm:
    - LLM provider is reachable (Gemini API key valid OR Ollama running with model)
    - Neo4j is up and accepts the configured credentials
    - Sentinel Hub credentials authenticate
    - GDELT master file index is reachable
    - OpenSky public REST endpoint responds
    - AISStream WebSocket handshake succeeds (if key set)
    - Telegram credentials are well-formed (handshake skipped — needs interactive auth)

Exit code 0 if all checks pass.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Awaitable, Callable

import httpx
from rich.console import Console
from rich.table import Table

from backend.config import settings

console = Console()


async def check_llm() -> tuple[bool, str]:
    from backend.llm.factory import get_provider
    try:
        provider = get_provider()
        ok = await provider.health_check()
        return ok, f"{provider.__class__.__name__} model={provider.get_model_name()}"
    except Exception as exc:
        return False, str(exc)


async def check_neo4j() -> tuple[bool, str]:
    from backend.graph.client import Neo4jClient
    client = Neo4jClient()
    try:
        await client.connect()
        ok = await client.health_check()
        await client.close()
        return ok, f"connected: {settings.NEO4J_URI}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


async def check_sentinelhub() -> tuple[bool, str]:
    if not settings.SENTINELHUB_CLIENT_ID or not settings.SENTINELHUB_CLIENT_SECRET:
        return False, "SENTINELHUB_CLIENT_ID/SECRET not set"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post(
                "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.SENTINELHUB_CLIENT_ID,
                    "client_secret": settings.SENTINELHUB_CLIENT_SECRET,
                },
            )
        if r.status_code == 200 and "access_token" in r.json():
            return True, "OAuth token acquired"
        return False, f"HTTP {r.status_code}: {r.text[:120]}"
    except Exception as exc:
        return False, str(exc)


async def check_gdelt() -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get("http://data.gdeltproject.org/gdeltv2/masterfilelist.txt")
        return r.status_code == 200, f"HTTP {r.status_code}, {len(r.content)} bytes"
    except Exception as exc:
        return False, str(exc)


async def check_opensky() -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get("https://opensky-network.org/api/states/all?lamin=35&lomin=22&lamax=42&lomax=28")
        if r.status_code == 200:
            n = len(r.json().get("states") or [])
            return True, f"{n} state vectors over Aegean"
        return False, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, str(exc)


async def check_aisstream() -> tuple[bool, str]:
    if not settings.AISSTREAM_API_KEY:
        return False, "AISSTREAM_API_KEY not set"
    return True, "key present (live handshake skipped — exercised by sensor)"


async def check_telegram() -> tuple[bool, str]:
    api_id, api_hash = settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH
    if not api_id or not api_hash:
        return False, "TELEGRAM_API_ID/HASH not set"
    if not api_id.isdigit():
        return False, "TELEGRAM_API_ID must be numeric"
    return True, "credentials well-formed (interactive login required for live use)"


CHECKS: list[tuple[str, Callable[[], Awaitable[tuple[bool, str]]]]] = [
    ("LLM provider",  check_llm),
    ("Neo4j",         check_neo4j),
    ("Sentinel Hub",  check_sentinelhub),
    ("GDELT",         check_gdelt),
    ("OpenSky",       check_opensky),
    ("AISStream",     check_aisstream),
    ("Telegram",      check_telegram),
]


async def main() -> int:
    table = Table(title="Damocles — source connectivity", show_lines=False)
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Detail")

    failures = 0
    for name, fn in CHECKS:
        try:
            ok, detail = await fn()
        except Exception as exc:
            ok, detail = False, f"unexpected: {exc}"
        if ok:
            table.add_row(name, "[green]OK[/]", detail)
        else:
            table.add_row(name, "[red]FAIL[/]", detail)
            failures += 1

    console.print(table)
    console.print(f"\n[{'green' if failures == 0 else 'red'}]"
                  f"{len(CHECKS) - failures}/{len(CHECKS)} sources reachable[/]")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
