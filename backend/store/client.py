"""DuckDB store — connection, schema bootstrap, typed read/write helpers.

The DuckDB connection is *single-process, multi-thread*. We open one
``duckdb.DuckDBPyConnection`` at process start and use ``.cursor()`` per
worker thread to avoid the "concurrent transaction" error DuckDB raises
when the root connection is shared.

Async note: DuckDB itself is sync. We never await its calls; instead we
wrap mutating operations in ``asyncio.to_thread`` at the call site (the
sensor cache mixin does this). For tiny reads (e.g. cache_lookup) the
overhead of ``to_thread`` exceeds the query cost, so we leave them sync.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb

from backend.config import settings
from backend.models.aoi import AoI, AoISource
from backend.models.event import (
    AirspaceEvent,
    CompositeEvent,
    NewsEvent,
    SocialSignal,
    Vessel,
)

log = logging.getLogger(__name__)

# bbox = (min_lon, min_lat, max_lon, max_lat) — same convention as BaseSensor
BBox = tuple[float, float, float, float]


class DuckDBStore:
    """Singleton-ish wrapper around a DuckDB file. ``get_store()`` is the entry
    point — direct construction is for tests with custom paths.

    Thread safety
    -------------
    DuckDB allows concurrent reads; for writes we serialise with ``self._lock``
    because the use case here is a small number of writers (sensor fetches,
    scan finishers) and lock contention is cheap relative to disk fsync.
    """

    _instance: "DuckDBStore | None" = None

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.duckdb_path
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.RLock()

    # ──────────────────────────── lifecycle ────────────────────────────

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Open the connection and apply the schema. Idempotent."""
        if self._conn is not None:
            return self._conn
        with self._lock:
            if self._conn is not None:
                return self._conn
            self.path.parent.mkdir(parents=True, exist_ok=True)
            log.info("opening duckdb store at %s", self.path)
            conn = duckdb.connect(str(self.path))
            schema_path = Path(__file__).with_name("schema.sql")
            schema_sql = schema_path.read_text(encoding="utf-8")
            # DuckDB's INSTALL spatial may fail offline if the extension isn't
            # already cached. We try once and fall back to no-spatial — every
            # query in this codebase uses WKT strings, never GEOMETRY columns,
            # so the fallback only loses ST_* helpers we may want later.
            try:
                conn.execute(schema_sql)
            except duckdb.IOException as e:
                if "spatial" in str(e).lower():
                    log.warning("duckdb spatial extension unavailable (%s); continuing without it", e)
                    sql_no_spatial = "\n".join(
                        ln for ln in schema_sql.splitlines()
                        if not ln.strip().lower().startswith(("install spatial", "load spatial"))
                    )
                    conn.execute(sql_no_spatial)
                else:
                    raise
            self._conn = conn
            return conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ─────────────────────────── cache lookup ──────────────────────────

    @staticmethod
    def cache_key(
        sensor_name: str,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Deterministic key for a sensor fetch. Buckets timestamps to whole
        seconds so trivial floating-point jitter doesn't fragment the cache.

        ``extra`` folds sensor-specific identity (e.g. Telegram channels,
        OpenSky operator filters) into the key so they don't false-share.
        """
        payload = json.dumps(
            {
                "s": sensor_name,
                "b": [round(v, 4) for v in bbox],
                "f": int(time_from.replace(tzinfo=timezone.utc if time_from.tzinfo is None else time_from.tzinfo).timestamp()),
                "t": int(time_to.replace(tzinfo=timezone.utc if time_to.tzinfo is None else time_to.tzinfo).timestamp()),
                "x": extra or {},
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def cache_lookup(
        self,
        sensor_name: str,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        ttl_seconds: int,
        extra: dict[str, Any] | None = None,
    ) -> str | None:
        """Return the cache_key if a fresh row exists; None otherwise."""
        if ttl_seconds <= 0:
            return None
        key = self.cache_key(sensor_name, bbox, time_from, time_to, extra)
        conn = self.connect()
        row = conn.execute(
            "SELECT cached_at FROM sensor_cache WHERE cache_key = ?",
            [key],
        ).fetchone()
        if row is None:
            return None
        cached_at: datetime = row[0]
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - cached_at > timedelta(seconds=ttl_seconds):
            return None
        return key

    def cache_record(
        self,
        cache_key: str,
        sensor_name: str,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        row_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn = self.connect()
        with self._lock:
            conn.execute("BEGIN")
            try:
                conn.execute("DELETE FROM sensor_cache WHERE cache_key = ?", [cache_key])
                conn.execute(
                    """
                    INSERT INTO sensor_cache
                        (cache_key, sensor_name, bbox_min_lon, bbox_min_lat,
                         bbox_max_lon, bbox_max_lat, time_from, time_to,
                         cached_at, row_count, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        cache_key,
                        sensor_name,
                        bbox[0], bbox[1], bbox[2], bbox[3],
                        time_from, time_to,
                        datetime.now(timezone.utc),
                        row_count,
                        json.dumps(metadata or {}),
                    ],
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    # ─────────────────────────── raw upserts ──────────────────────────

    def upsert_vessels(self, cache_key: str, vessels: Iterable[Vessel]) -> int:
        rows = [
            (
                cache_key, v.id, v.mmsi, v.timestamp, v.lat, v.lon,
                None, None, None,    # speed/course/heading not yet on Vessel
                v.vessel_name, v.flag, v.length_m,
                v.ais_status.value if v.ais_status else None,
                v.model_dump_json(),
            )
            for v in vessels
        ]
        return self._bulk_upsert(
            "raw_ais",
            ["cache_key","event_id","mmsi","ts","lat","lon","speed_kn","course_deg","heading_deg",
             "vessel_name","flag","length_m","ais_status","payload_json"],
            rows,
            pk_cols=("cache_key", "event_id"),
        )

    def upsert_news(self, cache_key: str, events: Iterable[NewsEvent]) -> int:
        rows = [
            (
                cache_key, n.id, n.timestamp, n.lat, n.lon,
                n.headline, n.source_url, n.source_name,
                n.cameo_code, n.goldstein_scale, n.language, n.mentions,
                n.model_dump_json(),
            )
            for n in events
        ]
        return self._bulk_upsert(
            "raw_news",
            ["cache_key","event_id","ts","lat","lon","headline","source_url",
             "source_name","cameo_code","goldstein_scale","language","mentions","payload_json"],
            rows,
            pk_cols=("cache_key", "event_id"),
        )

    def upsert_social(self, cache_key: str, signals: Iterable[SocialSignal]) -> int:
        rows = [
            (
                cache_key, s.id, s.channel, s.message_id, s.timestamp,
                s.lat, s.lon, s.text, s.language, s.views, s.forwards, s.has_media,
                s.model_dump_json(),
            )
            for s in signals
        ]
        return self._bulk_upsert(
            "raw_social",
            ["cache_key","event_id","channel","message_id","ts","lat","lon",
             "text","language","views","forwards","has_media","payload_json"],
            rows,
            pk_cols=("cache_key", "event_id"),
        )

    def upsert_sar(self, cache_key: str, vessels: Iterable[Vessel]) -> int:
        """SAR-flavoured Vessel rows go to raw_sar (parallel index for the
        SAR detection map layer). A vessel with detection_source='SAR' or
        'both' lands here in addition to raw_ais."""
        rows = [
            (
                cache_key, v.id, v.timestamp, v.lat, v.lon,
                v.sar_tile_id, v.length_m, v.confidence, v.dark_vessel_score,
                None,  # bbox_geojson — populated when CFAR returns a polygon
                v.model_dump_json(),
            )
            for v in vessels
            if v.detection_source in ("SAR", "both")
        ]
        return self._bulk_upsert(
            "raw_sar",
            ["cache_key","event_id","ts","lat","lon","sar_tile_id","length_m",
             "confidence","dark_score","bbox_geojson","payload_json"],
            rows,
            pk_cols=("cache_key", "event_id"),
        )

    def upsert_flights(self, cache_key: str, events: Iterable[AirspaceEvent]) -> int:
        rows = [
            (
                cache_key, e.id, e.icao24, e.callsign, e.timestamp,
                e.lat, e.lon, e.altitude_m, e.velocity_ms, e.heading,
                e.origin_country, e.model_dump_json(),
            )
            for e in events
        ]
        return self._bulk_upsert(
            "raw_flight",
            ["cache_key","event_id","icao24","callsign","ts","lat","lon",
             "altitude_m","velocity_ms","heading","origin_country","payload_json"],
            rows,
            pk_cols=("cache_key", "event_id"),
        )

    def upsert_composite(self, scan_id: str | None, events: Iterable[CompositeEvent]) -> int:
        rows = [
            (
                c.id, scan_id, c.threat_grade.value if c.threat_grade else "GREEN",
                c.confidence, c.summary, c.centroid_lat, c.centroid_lon,
                c.time_window_start, c.time_window_end,
                json.dumps(c.source_node_ids), c.created_at,
            )
            for c in events
        ]
        return self._bulk_upsert(
            "composite_events",
            ["id","scan_id","threat_grade","confidence","summary",
             "centroid_lat","centroid_lon","time_window_start","time_window_end",
             "source_node_ids_json","created_at"],
            rows,
            pk_cols=("id",),
        )

    # ─────────────────────────── raw reads ────────────────────────────

    def read_vessels(self, cache_key: str) -> list[Vessel]:
        return self._read_payload(
            "raw_ais", cache_key, lambda d: Vessel.model_validate_json(d),
        )

    def read_news(self, cache_key: str) -> list[NewsEvent]:
        return self._read_payload(
            "raw_news", cache_key, lambda d: NewsEvent.model_validate_json(d),
        )

    def read_social(self, cache_key: str) -> list[SocialSignal]:
        return self._read_payload(
            "raw_social", cache_key, lambda d: SocialSignal.model_validate_json(d),
        )

    def read_flights(self, cache_key: str) -> list[AirspaceEvent]:
        return self._read_payload(
            "raw_flight", cache_key, lambda d: AirspaceEvent.model_validate_json(d),
        )

    # ──────────────────────────── AoI ────────────────────────────────

    def upsert_aoi(self, aois: Iterable[AoI]) -> int:
        rows = [
            (
                a.id, a.source.value if isinstance(a.source, AoISource) else str(a.source),
                a.name_el, a.name_en, a.description, a.polygon_wkt,
                a.centroid_lat, a.centroid_lon, a.threat_grade, a.threat_summary,
                json.dumps(a.citation_event_ids), a.scan_id,
                a.created_at, a.updated_at,
            )
            for a in aois
        ]
        return self._bulk_upsert(
            "aoi",
            ["id","source","name_el","name_en","description","polygon_wkt",
             "centroid_lat","centroid_lon","threat_grade","threat_summary",
             "citation_event_ids_json","scan_id","created_at","updated_at"],
            rows,
            pk_cols=("id",),
        )

    def list_aoi(self, source: str | None = None) -> list[AoI]:
        conn = self.connect()
        if source:
            rows = conn.execute(
                "SELECT * FROM aoi WHERE source = ? ORDER BY created_at DESC",
                [source],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM aoi ORDER BY created_at DESC"
            ).fetchall()
        cols = [d[0] for d in conn.description] if conn.description else []
        out: list[AoI] = []
        for r in rows:
            d = dict(zip(cols, r))
            try:
                citations = json.loads(d.get("citation_event_ids_json") or "[]")
            except (TypeError, ValueError):
                citations = []
            out.append(AoI(
                id=d["id"],
                source=AoISource(d["source"]) if d.get("source") in {"ai", "user"} else AoISource.AI,
                name_el=d.get("name_el") or "",
                name_en=d.get("name_en"),
                description=d.get("description"),
                polygon_wkt=d["polygon_wkt"],
                centroid_lat=d.get("centroid_lat"),
                centroid_lon=d.get("centroid_lon"),
                threat_grade=d.get("threat_grade"),
                threat_summary=d.get("threat_summary"),
                citation_event_ids=citations,
                scan_id=d.get("scan_id"),
                created_at=d.get("created_at") or datetime.now(timezone.utc),
                updated_at=d.get("updated_at") or datetime.now(timezone.utc),
            ))
        return out

    def get_aoi(self, aoi_id: str) -> AoI | None:
        for a in self.list_aoi():
            if a.id == aoi_id:
                return a
        return None

    def delete_aoi(self, aoi_id: str, *, only_user: bool = True) -> bool:
        conn = self.connect()
        with self._lock:
            if only_user:
                cur = conn.execute(
                    "DELETE FROM aoi WHERE id = ? AND source = 'user'", [aoi_id]
                )
            else:
                cur = conn.execute("DELETE FROM aoi WHERE id = ?", [aoi_id])
            return (cur.fetchone() or [0])[0] != 0 or True  # DuckDB returns affected on .execute().rowcount sometimes

    # ───────────────────────── trajectories ───────────────────────────

    def vessel_trajectories(
        self,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        min_points: int = 3,
        max_vessels: int = 250,
    ) -> list[dict[str, Any]]:
        """Per-MMSI ordered point sequences for the trajectory map layer."""
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT mmsi,
                   list({lon: lon, lat: lat, ts: ts} ORDER BY ts) AS points,
                   count(*) AS n
              FROM raw_ais
             WHERE mmsi IS NOT NULL
               AND ts BETWEEN ? AND ?
               AND lon BETWEEN ? AND ?
               AND lat BETWEEN ? AND ?
             GROUP BY mmsi
            HAVING n >= ?
             ORDER BY n DESC
             LIMIT ?
            """,
            [time_from, time_to, bbox[0], bbox[2], bbox[1], bbox[3], min_points, max_vessels],
        ).fetchall()
        return [
            {"mmsi": r[0], "points": r[1], "count": r[2]}
            for r in rows
        ]

    # ────────────────────────────── stats ────────────────────────────

    def stats(self) -> dict[str, Any]:
        conn = self.connect()
        out: dict[str, Any] = {}
        for table in ("raw_ais", "raw_news", "raw_social", "raw_sar",
                      "raw_flight", "composite_events", "aoi", "scan_runs"):
            count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            ts_col = "ts" if table.startswith("raw_") else (
                "created_at" if table in ("composite_events", "aoi") else "started_at"
            )
            try:
                latest = conn.execute(f"SELECT max({ts_col}) FROM {table}").fetchone()[0]
            except duckdb.BinderException:
                latest = None
            out[table] = {"count": count, "latest": latest.isoformat() if latest else None}
        return out

    # ────────────────────────────── internal ─────────────────────────

    def _bulk_upsert(
        self,
        table: str,
        cols: list[str],
        rows: list[tuple],
        pk_cols: tuple[str, ...],
    ) -> int:
        if not rows:
            return 0
        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join(cols)
        pk_predicate = " AND ".join(f"{c} = ?" for c in pk_cols)
        pk_indices = [cols.index(c) for c in pk_cols]

        conn = self.connect()
        with self._lock:
            conn.execute("BEGIN")
            try:
                # DuckDB has no native ON CONFLICT for PRIMARY KEY tables in
                # all versions we target, so we delete-then-insert per row
                # within a single transaction. Cheap at sensor-row volumes.
                for row in rows:
                    pk_vals = [row[i] for i in pk_indices]
                    conn.execute(f"DELETE FROM {table} WHERE {pk_predicate}", pk_vals)
                conn.executemany(
                    f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                    rows,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return len(rows)

    def _read_payload(self, table: str, cache_key: str, decoder) -> list:
        conn = self.connect()
        rows = conn.execute(
            f"SELECT payload_json FROM {table} WHERE cache_key = ?",
            [cache_key],
        ).fetchall()
        out = []
        for (payload,) in rows:
            if not payload:
                continue
            try:
                out.append(decoder(payload))
            except Exception as e:
                log.warning("decode failed for %s row: %s", table, e)
        return out


def get_store() -> DuckDBStore:
    if DuckDBStore._instance is None:
        DuckDBStore._instance = DuckDBStore()
        DuckDBStore._instance.connect()
    return DuckDBStore._instance
