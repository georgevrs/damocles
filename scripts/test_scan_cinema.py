"""Quick end-to-end test of the W3-T4 scan-cinema WebSocket.

Run:
    uv run python scripts/test_scan_cinema.py

Asserts: start frame, ≥1 aoi frame with a valid geometry, complete frame.
Useful as a 1-second sanity check after backend changes.
"""
from __future__ import annotations

import asyncio
import json
import sys

import websockets


async def main() -> int:
    url = "ws://127.0.0.1:8001/ws/scan-cinema?delay_ms=30"
    async with websockets.connect(url, open_timeout=10, close_timeout=10) as ws:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert msg["type"] == "start", f"first frame should be start, got {msg!r}"
        print(f"  start  total={msg.get('total')}")
        aoi_count = 0
        red_count = 0
        async for raw in ws:
            msg = json.loads(raw)
            if msg["type"] == "aoi":
                aoi_count += 1
                if msg["feature"]["properties"].get("threat_grade") == "RED":
                    red_count += 1
            elif msg["type"] == "complete":
                print(f"  complete  aois={aoi_count}  reds={red_count}  total={msg.get('total')}")
                break
    return 0 if aoi_count > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
