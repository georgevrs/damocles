"""WatchEventBroker tests — the in-memory pub/sub the WS endpoint reads from."""
from __future__ import annotations

import asyncio

import pytest

from backend.api._broker import WatchEventBroker


@pytest.mark.asyncio
async def test_publish_and_subscribe_late_joiner_replays_buffer():
    """A WS that connects AFTER the pipeline already emitted events should
    catch up on the buffered ones, not miss them."""
    b = WatchEventBroker()
    await b.publish("w1", {"stage": "geo", "status": "complete", "progress_pct": 30})
    await b.publish("w1", {"stage": "osint", "status": "complete", "progress_pct": 60})

    received = []
    async for ev in b.subscribe("w1"):
        received.append(ev)
        # Simulate a complete event after we've consumed the buffer
        if len(received) == 2:
            await b.publish("w1", {"stage": "complete", "status": "complete", "progress_pct": 100})

    assert len(received) == 3
    assert [r["stage"] for r in received] == ["geo", "osint", "complete"]


@pytest.mark.asyncio
async def test_subscribe_returns_immediately_when_already_done():
    b = WatchEventBroker()
    await b.publish("w2", {"stage": "complete", "status": "complete", "progress_pct": 100})

    received = []
    async for ev in b.subscribe("w2"):
        received.append(ev)
    # The single complete event from the buffer.
    assert received == [{"stage": "complete", "status": "complete", "progress_pct": 100}]


@pytest.mark.asyncio
async def test_publish_fans_out_to_live_subscribers():
    b = WatchEventBroker()

    async def consume(out: list):
        async for ev in b.subscribe("w3"):
            out.append(ev)

    out_a, out_b = [], []
    task_a = asyncio.create_task(consume(out_a))
    task_b = asyncio.create_task(consume(out_b))
    # Yield so the consumers register their queues
    await asyncio.sleep(0.05)

    await b.publish("w3", {"stage": "fusion", "status": "started", "progress_pct": 80})
    await b.publish("w3", {"stage": "complete", "status": "complete", "progress_pct": 100})

    await asyncio.gather(task_a, task_b)
    assert [e["stage"] for e in out_a] == ["fusion", "complete"]
    assert [e["stage"] for e in out_b] == ["fusion", "complete"]


@pytest.mark.asyncio
async def test_is_done_flag_flips_on_complete():
    b = WatchEventBroker()
    assert b.is_done("w4") is False
    await b.publish("w4", {"stage": "geo", "status": "complete"})
    assert b.is_done("w4") is False
    await b.publish("w4", {"stage": "complete", "status": "complete"})
    assert b.is_done("w4") is True


def test_buffered_events_returns_buffer():
    b = WatchEventBroker()
    asyncio.run(b.publish("w5", {"stage": "x"}))
    asyncio.run(b.publish("w5", {"stage": "y"}))
    events = b.buffered_events("w5")
    assert [e["stage"] for e in events] == ["x", "y"]


def test_gc_evicts_only_completed_channels_past_retention():
    # Negative retention makes `completed_at < (now - retain_seconds)` always true,
    # so any completed channel is evictable on the very next gc.
    b = WatchEventBroker(retain_seconds=-1.0)
    asyncio.run(b.publish("w_old", {"stage": "complete"}))
    asyncio.run(b.publish("w_active", {"stage": "geo"}))   # not done

    evicted = b.gc()
    assert evicted == 1
    assert b.buffered_events("w_old") == []     # gone
    assert len(b.buffered_events("w_active")) == 1   # retained
