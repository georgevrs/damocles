"""Watch executor — the live pipeline orchestrator.

Invoked by ``POST /api/watches`` and by ``scripts/seed_neo4j.py``. Drives:

    parse query (LLM) -> sensor fan-out -> AIS cross-reference (optional)
        -> fusion -> graph ingest -> citation chain ready

Yields ``stage`` events which the WebSocket layer broadcasts to the frontend
ProgressStream component.

Failure handling
----------------
Each sensor is wrapped in try/except. A sensor failing logs a warning, emits
a `stage=*_failed` event, and the pipeline continues with the survivors.
This is deliberate — a transient AISStream disconnect or a Sentinel Hub
quota error should degrade the brief, not kill it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Iterable

from backend.agents.base import AgentOutput
from backend.audit.logger import MerkleAuditLogger
from backend.agents.devils_advocate import DevilsAdvocateAgent
from backend.agents.geospatial_agent import GeospatialAgent
from backend.agents.osint_agent import OSINTAgent
from backend.agents.supervisor_agent import SupervisorAgent, run_supervisor_and_assemble
from backend.graph.client import Neo4jClient
from backend.graph.ingestion import (
    ingest_airspace,
    ingest_brief,
    ingest_composite,
    ingest_news,
    ingest_social,
    ingest_vessel,
    ingest_watch,
)
from backend.llm.base import LLMProvider
from backend.llm.factory import get_devil_provider
from backend.models.brief import Brief
from backend.models.event import (
    AISStatus,
    AirspaceEvent,
    CompositeEvent,
    NewsEvent,
    SocialSignal,
    Vessel,
)
from backend.models.watch import Watch, WatchStatus
from backend.sensors.dark_vessel import cross_reference
from backend.sensors.fusion import FusionEngine, FusionResult
from backend.sensors.gdelt import GDELTSensor
from backend.sensors.geospatial import GeospatialSensor

from .parser import WatchParser

log = logging.getLogger(__name__)


class WatchExecutor:
    def __init__(
        self,
        graph: Neo4jClient,
        llm: LLMProvider,
        *,
        geo_sensor: GeospatialSensor | None = None,
        gdelt_sensor: GDELTSensor | None = None,
        # Telegram and AIS are constructed lazily because they may not be configured
        enable_ais: bool = True,
        enable_telegram: bool = True,
        ais_capture_seconds: float = 30.0,
        fusion: FusionEngine | None = None,
        audit: MerkleAuditLogger | None = None,
    ):
        self.graph = graph
        self.llm = llm
        self.parser = WatchParser(llm)
        self._geo_sensor = geo_sensor
        self._gdelt_sensor = gdelt_sensor
        self.enable_ais = enable_ais
        self.enable_telegram = enable_telegram
        self.ais_capture_seconds = ais_capture_seconds
        self.fusion = fusion or FusionEngine()
        self.audit = audit

    async def _audit(self, action_type: str, actor: str, payload: dict) -> None:
        """Log to the Merkle chain if an audit logger is wired. No-op otherwise."""
        if self.audit is None:
            return
        try:
            await self.audit.log(action_type, actor, payload)
        except Exception:
            log.exception("Audit log failed for %s/%s — pipeline continues", action_type, actor)

    # ─── Public ──────────────────────────────────────────────────────────────
    async def parse_query(self, raw_query: str) -> Watch:
        spec = await self.parser.parse(raw_query)
        return Watch(raw_query=raw_query, spec=spec)

    async def execute(self, watch: Watch, *, scan_id: str | None = None) -> AsyncIterator[dict]:
        watch.status = WatchStatus.PROCESSING
        bbox = watch.spec.get_bbox()
        time_to = datetime.now(tz=timezone.utc).replace(microsecond=0)
        time_from = time_to - timedelta(days=watch.spec.time_window_days)

        await ingest_watch(self.graph, watch)
        await self._audit("watch.created", "watch_executor", {
            "watch_id":  watch.id,
            "raw_query": watch.raw_query,
            "region":    watch.spec.region.value,
            "domain":    watch.spec.domain.value,
            "window_days": watch.spec.time_window_days,
            "bbox":      list(bbox),
        })
        yield self._evt("watch_created", "complete",
                        f"watch {watch.id} ingested into graph", 5)

        # ─── Sensor fan-out ──────────────────────────────────────────────────
        # Run sensors concurrently; AIS capture is shorter than its window so we don't block.
        yield self._evt("sensors", "started", "dispatching sensors", 10)

        sensor_tasks: dict[str, asyncio.Task] = {}
        sensor_tasks["geospatial"] = asyncio.create_task(
            self._run_geospatial(bbox, time_from, time_to)
        )
        sensor_tasks["gdelt"] = asyncio.create_task(
            self._run_gdelt(bbox, time_from, time_to)
        )
        if self.enable_ais:
            sensor_tasks["ais"] = asyncio.create_task(self._run_ais(bbox))
        if self.enable_telegram:
            sensor_tasks["telegram"] = asyncio.create_task(
                self._run_telegram(bbox, time_from, time_to)
            )

        # Stream completion as each sensor finishes.
        results: dict[str, object] = {}
        pct = 10
        per_sensor_pct = 60 // max(1, len(sensor_tasks))
        for name in list(sensor_tasks):
            try:
                results[name] = await sensor_tasks[name]
                count = self._count_for(name, results[name])
                duration_ms = getattr(results[name], "duration_ms", None)
                await self._audit(f"sensor.{name}.fetched", f"{name}_sensor", {
                    "watch_id":     watch.id,
                    "event_count":  count,
                    "duration_ms":  duration_ms,
                })
                pct += per_sensor_pct
                yield self._evt(f"{name}_sensor", "complete",
                                f"{name}: {count} events", min(pct, 70))
            except Exception as exc:
                log.exception("%s sensor failed", name)
                results[name] = None
                await self._audit(f"sensor.{name}.failed", f"{name}_sensor", {
                    "watch_id": watch.id,
                    "error":    f"{type(exc).__name__}: {exc}",
                })
                pct += per_sensor_pct
                yield self._evt(f"{name}_sensor", "failed",
                                f"{name}: {type(exc).__name__}: {exc}", min(pct, 70))

        # ─── AIS cross-reference ─────────────────────────────────────────────
        # Always run — even with zero AIS records, so SAR detections get tagged
        # DARK (not left as UNKNOWN). cross_reference() with an empty ais_records
        # list correctly marks every vessel DARK and computes dark_vessel_score.
        vessels: list[Vessel] = list(getattr(results.get("geospatial"), "events", []) or [])
        ais_records = results.get("ais") or []
        if vessels:
            yield self._evt("ais_cross_ref", "started",
                            f"matching {len(vessels)} SAR detections vs {len(ais_records)} AIS records", 72)
            vessels = cross_reference(vessels, ais_records)
            n_dark = sum(1 for v in vessels if v.ais_status.value == "dark")
            n_bcast = sum(1 for v in vessels if v.ais_status.value == "broadcasting")

            from backend.store import get_store
            _store = get_store()

            # Write enriched vessels back to DuckDB — the initial cache write
            # happened before cross_reference(), so the map layer was reading
            # UNKNOWN rows with no name/MMSI. This upsert overwrites those rows
            # with the post-correlation AIS status, vessel_name, dark_score, etc.
            geo_result = results.get("geospatial")
            geo_cache_key = (getattr(geo_result, "metadata", None) or {}).get("cache_key")
            if geo_cache_key:
                try:
                    await asyncio.to_thread(_store.upsert_vessels, geo_cache_key, vessels)
                    await asyncio.to_thread(_store.upsert_sar, geo_cache_key, vessels)
                except Exception:
                    log.exception("post-cross-reference DuckDB update failed (continuing)")

            # Persist unmatched AIS records as pure-AIS broadcasting vessels.
            # Without this step AIS broadcasts that weren't spatially matched to a
            # SAR detection are discarded, so cyan/red dots never appear on the map.
            n_ais_only = 0
            if ais_records:
                matched_mmsis = {
                    v.mmsi for v in vessels
                    if v.mmsi and v.ais_status == AISStatus.BROADCASTING
                }
                # Deduplicate by MMSI — keep the most-recent position per vessel.
                # AISStream may send multiple position reports in the capture window.
                dedup: dict[str, object] = {}
                for r in ais_records:
                    if r.mmsi not in matched_mmsis:
                        prev = dedup.get(r.mmsi)
                        if prev is None or r.timestamp > prev.timestamp:  # type: ignore[union-attr]
                            dedup[r.mmsi] = r
                ais_only_vessels: list[Vessel] = [
                    Vessel(
                        # Deterministic UUID per MMSI so consecutive scans overwrite
                        # the same row rather than accumulating stale positions.
                        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ais:{r.mmsi}")),
                        lat=r.lat,
                        lon=r.lon,
                        timestamp=r.timestamp,
                        detection_source="AIS",
                        ais_status=AISStatus.BROADCASTING,
                        confidence=1.0,
                        mmsi=r.mmsi,
                        vessel_name=r.name,
                        flag=r.flag,
                    )
                    for r in dedup.values()  # type: ignore[union-attr]
                ]
                n_ais_only = len(ais_only_vessels)
                if ais_only_vessels:
                    try:
                        # Stable cache key: all AIS-live vessels share one bucket
                        # so the deterministic UUIDs actually overwrite on each run.
                        ais_ck = _store.cache_key("ais_live", bbox, time_to, time_to)
                        await asyncio.to_thread(_store.upsert_vessels, ais_ck, ais_only_vessels)
                    except Exception:
                        log.exception("AIS-only vessel upsert failed (continuing)")

            yield self._evt("ais_cross_ref", "complete",
                            f"{n_bcast} SAR+AIS / {n_dark} dark / {n_ais_only} AIS-only", 75)

        news: list[NewsEvent] = list(getattr(results.get("gdelt"), "events", []) or [])
        social: list[SocialSignal] = list(getattr(results.get("telegram"), "events", []) or [])
        airspace: list[AirspaceEvent] = []   # wired in a future day

        # ─── Graph ingestion (sources first, then composites) ───────────────
        yield self._evt("graph_ingest", "started",
                        f"writing {len(vessels)+len(news)+len(social)} sensor events", 78)
        for v in vessels:    await ingest_vessel(self.graph, v)
        for n in news:       await ingest_news(self.graph, n)
        for s in social:     await ingest_social(self.graph, s)
        for a in airspace:   await ingest_airspace(self.graph, a)
        yield self._evt("graph_ingest", "complete", "sensor events written", 82)

        # ─── Fusion ──────────────────────────────────────────────────────────
        yield self._evt("fusion", "started", "running spatiotemporal correlation", 85)
        cen_lat = (bbox[1] + bbox[3]) / 2
        cen_lon = (bbox[0] + bbox[2]) / 2
        fusion_result: FusionResult = self.fusion.fuse(
            vessels=vessels, news=news, social=social, airspace=airspace,
            default_lat=cen_lat, default_lon=cen_lon,
        )
        await self._audit("fusion.complete", "fusion_engine", {
            "watch_id":   watch.id,
            "composites": len(fusion_result.composites),
            "edges":      fusion_result.stats["edges"],
            "by_sensor":  fusion_result.stats.get("by_sensor", {}),
        })
        yield self._evt("fusion", "complete",
                        f"{len(fusion_result.composites)} composite events "
                        f"({fusion_result.stats['edges']} cross-sensor edges)", 90)

        # ─── Composite ingestion ─────────────────────────────────────────────
        for ce in fusion_result.composites:
            await ingest_composite(self.graph, ce, watch.id)
        # Phase 2: also persist composites to DuckDB so they're queryable across
        # watches and so the AoI agent (Day 24) can cluster on them.
        try:
            from backend.store import get_store
            get_store().upsert_composite(scan_id, fusion_result.composites)
        except Exception:
            log.exception("composite upsert to DuckDB failed (continuing)")
        yield self._evt("graph_ingest", "complete",
                        f"{len(fusion_result.composites)} composites linked to watch", 88)

        # ─── AoI inference (Phase 2 / Day 24) ───────────────────────────────
        try:
            from backend.agents.aoi_agent import AoIAgent
            from backend.store import get_store
            aoi_agent = AoIAgent(llm=self.llm)
            aois = await aoi_agent.infer(fusion_result.composites, scan_id=scan_id)
            if aois:
                get_store().upsert_aoi(aois)
                await self._audit("aoi.inferred", "aoi_agent", {
                    "watch_id": watch.id, "scan_id": scan_id, "count": len(aois),
                    "names": [a.name_el for a in aois],
                })
                yield self._evt("aoi", "complete",
                                f"{len(aois)} areas-of-interest inferred", 89)
        except Exception:
            log.exception("AoI inference failed (continuing)")
            yield self._evt("aoi", "failed", "AoI inference failed", 89)

        # ─── Agent layer + brief assembly ────────────────────────────────────
        # Pick the top composite (AMBER/RED preferred, fall back to highest confidence).
        top_composite = self._pick_top_composite(fusion_result.composites)
        if top_composite is None:
            yield self._evt("agent_layer", "skipped",
                            "no composites to reason over - no brief produced", 95)
            watch.status = WatchStatus.COMPLETE
            yield self._evt("complete", "complete",
                            f"watch {watch.id} pipeline finished (no brief)", 100)
            return

        yield self._evt("agent_layer", "started",
                        f"running 4 agents on composite {top_composite.id[:8]} "
                        f"({top_composite.threat_grade.value}, {top_composite.corroboration_count} sources)", 90)
        try:
            brief = await self._run_agent_layer(top_composite, watch)
            await ingest_brief(self.graph, brief)
            watch.brief_id = brief.id
            await self._audit("brief.ingested", "supervisor_agent", {
                "watch_id":         watch.id,
                "brief_id":         brief.id,
                "composite_id":     top_composite.id,
                "section_count":    len(brief.all_sections()),
                "agents_consulted": brief.metadata.get("agents_consulted", []),
                "bluf_confidence":  brief.bluf.confidence,
                "has_devil":        brief.devils_advocate is not None,
                "has_recommendation": brief.recommendation is not None,
            })
            yield self._evt("brief", "complete",
                            f"brief {brief.id[:8]} ingested "
                            f"({len(brief.all_sections())} sections, "
                            f"{len(brief.bluf.citation_node_ids)} BLUF citations)", 98)
        except Exception as exc:
            log.exception("Agent layer failed")
            await self._audit("agent_layer.failed", "watch_executor", {
                "watch_id": watch.id,
                "error":    f"{type(exc).__name__}: {exc}",
            })
            yield self._evt("agent_layer", "failed",
                            f"{type(exc).__name__}: {exc}", 98)

        watch.status = WatchStatus.COMPLETE
        yield self._evt("complete", "complete",
                        f"watch {watch.id} pipeline finished", 100)

    # ─── Sensor wrappers ─────────────────────────────────────────────────────
    async def _run_geospatial(self, bbox, time_from, time_to):
        if self._geo_sensor is None:
            self._geo_sensor = GeospatialSensor()
        return await self._geo_sensor.fetch(bbox, time_from, time_to)

    async def _run_gdelt(self, bbox, time_from, time_to):
        if self._gdelt_sensor is None:
            self._gdelt_sensor = GDELTSensor()
        # For fusion-driven runs we pass the watch bbox (with a small ±2° expansion
        # to accommodate GDELT's coarse geocoding). Events outside this still match
        # via Actor1/2 country code, but we only keep those whose ActionGeo lands in
        # the watch's area of interest. Standalone browsing (scripts/test_gdelt.py)
        # uses a global bbox separately.
        expanded = (bbox[0] - 2.0, bbox[1] - 2.0, bbox[2] + 2.0, bbox[3] + 2.0)
        return await self._gdelt_sensor.fetch(expanded, time_from, time_to)

    async def _run_ais(self, bbox):
        from backend.sensors.ais import AISStreamClient
        client = AISStreamClient(bbox=bbox)
        return await client.capture(duration_seconds=self.ais_capture_seconds)

    async def _run_telegram(self, bbox, time_from, time_to):
        from backend.sensors.telegram_sensor import TelegramSensor
        try:
            sensor = TelegramSensor()
        except ValueError as exc:
            log.warning("Telegram sensor not configured: %s", exc)
            return None
        try:
            return await sensor.fetch(bbox, time_from, time_to)
        except RuntimeError as exc:
            # Most common cause: no Telethon session. Don't fail the whole pipeline.
            log.warning("Telegram sensor skipped: %s", exc)
            return None

    # ─── Agent layer ─────────────────────────────────────────────────────────
    @staticmethod
    def _pick_top_composite(composites: list[CompositeEvent]) -> CompositeEvent | None:
        """Top composite for the brief — prefer AMBER/RED with multi-source corroboration."""
        if not composites:
            return None

        def rank(ce: CompositeEvent) -> tuple:
            grade_score = {"RED": 2, "AMBER": 1, "GREEN": 0}.get(ce.threat_grade.value, 0)
            return (grade_score, ce.corroboration_count, ce.confidence)

        return max(composites, key=rank)

    async def _run_agent_layer(self, composite: CompositeEvent, watch: Watch) -> Brief:
        """Run 3 primaries + devil + supervisor on one composite, return canonical Brief.

        Geospatial and OSINT run concurrently (independent); the Devil's Advocate
        waits on both before firing; the Supervisor takes everyone's outputs.
        Each agent's run + outcome is logged to the audit chain.
        """
        prior_outputs: list[tuple[str, AgentOutput]] = []

        geo_task = asyncio.create_task(
            GeospatialAgent(llm=self.llm, graph=self.graph).run(composite_event_id=composite.id)
        )
        osint_task = asyncio.create_task(
            OSINTAgent(llm=self.llm, graph=self.graph).run(composite_event_id=composite.id)
        )
        results = await asyncio.gather(geo_task, osint_task, return_exceptions=True)
        names = ["geospatial_agent", "osint_agent"]
        for name, res in zip(names, results, strict=True):
            if isinstance(res, BaseException):
                log.warning("%s failed during agent layer: %s", name, res)
                await self._audit(f"agent.{name}.failed", name, {
                    "watch_id": watch.id, "composite_id": composite.id,
                    "error": f"{type(res).__name__}: {res}",
                })
                continue
            prior_outputs.append((name, res))
            await self._audit(f"agent.{name}.run", name, {
                "watch_id":      watch.id,
                "composite_id":  composite.id,
                "confidence":    res.confidence,
                "finding_count": len(res.key_findings),
                "citation_count": len(res.citation_node_ids),
                "model":          self.llm.get_model_name(),
            })

        # Devil's advocate — only meaningful if at least one primary produced output.
        if prior_outputs:
            try:
                devil_provider = get_devil_provider()
                devil_out = await DevilsAdvocateAgent(llm=devil_provider, graph=self.graph).run(
                    composite_event_id=composite.id, prior_outputs=prior_outputs,
                )
                prior_outputs.append(("devils_advocate", devil_out))
                await self._audit("agent.devils_advocate.run", "devils_advocate", {
                    "watch_id":         watch.id,
                    "composite_id":     composite.id,
                    "confidence":       devil_out.confidence,
                    "devil_confidence": getattr(devil_out, "devil_confidence", None),
                    "finding_count":    len(devil_out.key_findings),
                    "model":            devil_provider.get_model_name(),
                })
            except Exception as exc:
                log.warning("DevilsAdvocate failed during agent layer: %s", exc)
                await self._audit("agent.devils_advocate.failed", "devils_advocate", {
                    "watch_id": watch.id, "composite_id": composite.id,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        # Supervisor + Brief assembly
        supervisor = SupervisorAgent(llm=self.llm, graph=self.graph)
        brief = await run_supervisor_and_assemble(
            agent=supervisor,
            composite_event_id=composite.id,
            watch_id=watch.id,
            prior_outputs=prior_outputs,
            sources_count=len(composite.source_node_ids),
        )
        await self._audit("agent.supervisor.run", "supervisor_agent", {
            "watch_id":      watch.id,
            "composite_id":  composite.id,
            "brief_id":      brief.id,
            "section_count": len(brief.all_sections()),
            "model":         self.llm.get_model_name(),
        })
        return brief

    # ─── Helpers ─────────────────────────────────────────────────────────────
    @staticmethod
    def _count_for(name: str, result) -> int:
        if result is None:
            return 0
        if name == "ais":
            return len(result)
        return len(getattr(result, "events", []) or [])

    @staticmethod
    def _evt(stage: str, status: str, detail: str, pct: int) -> dict:
        return {"stage": stage, "status": status, "detail": detail, "progress_pct": pct}

    async def get_brief(self, watch_id: str):
        # Brief assembly belongs to Week 2 (agent layer + supervisor).
        _ = watch_id
        return None
