"""FastAPI entry point.

Wires the LLM provider, Neo4j client, and Watch executor into the request
lifecycle. All long-lived resources are created in the lifespan handler.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import aoi, audit, briefs, external, graph, map as map_api, preview, standing, store as store_api, watches, ws
from backend.audit.logger import MerkleAuditLogger
from backend.config import settings
from backend.graph.client import graph_client
from backend.llm.factory import get_provider
from backend.store import get_store
from backend.watch_engine.executor import WatchExecutor
from backend.watch_engine.standing import get_scheduler

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Damocles starting (env=%s, llm=%s, demo=%s)",
             settings.DAMOCLES_ENV, settings.LLM_PROVIDER, settings.DEMO_MODE)

    # DuckDB fact store — bootstrap before sensors run
    try:
        store = get_store()
        log.info("DuckDB store ready at %s", store.path)
    except Exception as exc:
        log.warning("DuckDB store unavailable at startup: %s", exc)

    # Neo4j
    try:
        await graph_client.connect()
        await graph_client.apply_schema()
    except Exception as exc:
        log.warning("Neo4j unavailable at startup: %s", exc)

    # LLM provider
    try:
        provider = get_provider()
        ok = await provider.health_check()
        log.info("LLM provider %s — health=%s, model=%s",
                 settings.LLM_PROVIDER, ok, provider.get_model_name())
    except Exception as exc:
        log.warning("LLM provider unavailable at startup: %s", exc)
        provider = None

    # Merkle audit logger — dual store (Neo4j + local JSONL).
    audit_logger = MerkleAuditLogger(
        graph=graph_client if graph_client._driver else None,
        log_file_path=settings.audit_log_path,
    )
    try:
        await audit_logger.bootstrap()
    except Exception as exc:
        log.warning("Audit logger bootstrap failed (will lazy-bootstrap on first log): %s", exc)
    app.state.audit = audit_logger

    # Wire executor + background-task registry for the pipeline runner
    if provider is not None:
        app.state.executor = WatchExecutor(
            graph=graph_client, llm=provider, audit=audit_logger,
        )
    else:
        app.state.executor = None
    app.state.pipeline_tasks = set()

    # Standing scan scheduler — daily Greece-wide coverage refresh.
    if app.state.executor is not None:
        try:
            sched = get_scheduler()
            sched.start(app.state.executor)
            app.state.scheduler = sched
        except Exception as exc:
            log.warning("standing-scan scheduler failed to start: %s", exc)
            app.state.scheduler = None
    else:
        app.state.scheduler = None

    try:
        yield
    finally:
        # Cancel any in-flight pipelines so the process can exit cleanly.
        for t in list(app.state.pipeline_tasks):
            t.cancel()
        if getattr(app.state, "scheduler", None):
            app.state.scheduler.stop()
        await graph_client.close()
        log.info("Damocles stopped")


app = FastAPI(
    title="Damocles",
    version="0.1.0",
    description="Sovereign Intelligence Analysis Platform — EYP 2026",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(watches.router)
app.include_router(briefs.router)
app.include_router(graph.router)
app.include_router(audit.router)
app.include_router(store_api.router)
app.include_router(standing.router)
app.include_router(aoi.router)
app.include_router(map_api.router)
app.include_router(external.router)
app.include_router(preview.router)
app.include_router(ws.router)

# Read-only static mount serving cached evidence files (SAR PNG previews,
# etc.). Only ``settings.cache_dir`` is exposed; nothing outside it is reachable.
app.mount("/static", StaticFiles(directory=settings.cache_dir), name="static")


@app.get("/health")
async def health() -> dict:
    """Liveness + dependency probe."""
    neo4j_ok = await graph_client.health_check() if graph_client._driver else False
    llm_ok = False
    llm_model = "unknown"
    try:
        provider = get_provider()
        llm_ok = await provider.health_check()
        llm_model = provider.get_model_name()
    except Exception as exc:
        log.debug("Health LLM check failed: %s", exc)

    return {
        "status":   "ok" if (neo4j_ok and llm_ok) else "degraded",
        "env":      settings.DAMOCLES_ENV,
        "demo_mode": settings.DEMO_MODE,
        "neo4j":    {"ok": neo4j_ok, "uri": settings.NEO4J_URI},
        "llm":      {"ok": llm_ok, "provider": settings.LLM_PROVIDER, "model": llm_model},
    }


@app.get("/")
async def root() -> dict:
    return {
        "service": "damocles",
        "version": app.version,
        "docs":    "/docs",
        "health":  "/health",
    }
