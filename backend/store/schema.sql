-- Damocles Phase 2 fact store. Loaded by DuckDBStore.connect() at boot.
-- IDempotent: every statement uses CREATE ... IF NOT EXISTS so the boot path
-- is safe to re-run. Schema migrations live alongside as schema_v{n}.sql.

INSTALL spatial;
LOAD spatial;

-- Sensor cache rows. Keys are deterministic (sensor + bbox + time bucket)
-- so the cache lookup is a primary-key probe, not a range scan.
CREATE TABLE IF NOT EXISTS sensor_cache (
    cache_key      VARCHAR PRIMARY KEY,
    sensor_name    VARCHAR NOT NULL,
    bbox_min_lon   DOUBLE  NOT NULL,
    bbox_min_lat   DOUBLE  NOT NULL,
    bbox_max_lon   DOUBLE  NOT NULL,
    bbox_max_lat   DOUBLE  NOT NULL,
    time_from      TIMESTAMP NOT NULL,
    time_to        TIMESTAMP NOT NULL,
    cached_at      TIMESTAMP NOT NULL,
    row_count      INTEGER NOT NULL,
    metadata_json  VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_sensor_cache_sensor_time
    ON sensor_cache (sensor_name, time_from, time_to);

-- AIS detections. We deliberately keep `source_payload_json` so we can
-- replay the exact upstream row for audit reproduction.
CREATE TABLE IF NOT EXISTS raw_ais (
    cache_key   VARCHAR NOT NULL,
    event_id    VARCHAR NOT NULL,
    mmsi        VARCHAR,
    ts          TIMESTAMP NOT NULL,
    lat         DOUBLE NOT NULL,
    lon         DOUBLE NOT NULL,
    speed_kn    DOUBLE,
    course_deg  DOUBLE,
    heading_deg DOUBLE,
    vessel_name VARCHAR,
    flag        VARCHAR,
    length_m    DOUBLE,
    ais_status  VARCHAR,
    payload_json VARCHAR,
    PRIMARY KEY (cache_key, event_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_ais_mmsi_ts ON raw_ais (mmsi, ts);
CREATE INDEX IF NOT EXISTS idx_raw_ais_ts ON raw_ais (ts);

-- GDELT geocoded news events.
CREATE TABLE IF NOT EXISTS raw_news (
    cache_key       VARCHAR NOT NULL,
    event_id        VARCHAR NOT NULL,
    ts              TIMESTAMP NOT NULL,
    lat             DOUBLE NOT NULL,
    lon             DOUBLE NOT NULL,
    headline        VARCHAR,
    source_url      VARCHAR,
    source_name     VARCHAR,
    cameo_code      VARCHAR,
    goldstein_scale DOUBLE,
    language        VARCHAR,
    mentions        INTEGER,
    payload_json    VARCHAR,
    PRIMARY KEY (cache_key, event_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_news_ts ON raw_news (ts);

-- Telegram social signals.
CREATE TABLE IF NOT EXISTS raw_social (
    cache_key   VARCHAR NOT NULL,
    event_id    VARCHAR NOT NULL,
    channel     VARCHAR,
    message_id  VARCHAR,
    ts          TIMESTAMP NOT NULL,
    lat         DOUBLE,
    lon         DOUBLE,
    text        VARCHAR,
    language    VARCHAR,
    views       INTEGER,
    forwards    INTEGER,
    has_media   BOOLEAN,
    payload_json VARCHAR,
    PRIMARY KEY (cache_key, event_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_social_ts ON raw_social (ts);

-- Sentinel-1 SAR vessel detections (CFAR output).
CREATE TABLE IF NOT EXISTS raw_sar (
    cache_key       VARCHAR NOT NULL,
    event_id        VARCHAR NOT NULL,
    ts              TIMESTAMP NOT NULL,
    lat             DOUBLE NOT NULL,
    lon             DOUBLE NOT NULL,
    sar_tile_id     VARCHAR,
    length_m        DOUBLE,
    confidence      DOUBLE,
    dark_score      DOUBLE,
    bbox_geojson    VARCHAR,
    payload_json    VARCHAR,
    PRIMARY KEY (cache_key, event_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_sar_ts ON raw_sar (ts);

-- OpenSky flight observations.
CREATE TABLE IF NOT EXISTS raw_flight (
    cache_key   VARCHAR NOT NULL,
    event_id    VARCHAR NOT NULL,
    icao24      VARCHAR,
    callsign    VARCHAR,
    ts          TIMESTAMP NOT NULL,
    lat         DOUBLE NOT NULL,
    lon         DOUBLE NOT NULL,
    altitude_m  DOUBLE,
    velocity_ms DOUBLE,
    heading     DOUBLE,
    origin_country VARCHAR,
    payload_json VARCHAR,
    PRIMARY KEY (cache_key, event_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_flight_ts ON raw_flight (ts);

-- Composite events emitted by the fusion engine.
CREATE TABLE IF NOT EXISTS composite_events (
    id              VARCHAR PRIMARY KEY,
    scan_id         VARCHAR,
    threat_grade    VARCHAR NOT NULL,
    confidence      DOUBLE,
    summary         VARCHAR,
    centroid_lat    DOUBLE,
    centroid_lon    DOUBLE,
    time_window_start TIMESTAMP,
    time_window_end   TIMESTAMP,
    source_node_ids_json VARCHAR,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_composite_scan ON composite_events (scan_id);

-- Areas of Interest — both AI-inferred and analyst-drawn.
CREATE TABLE IF NOT EXISTS aoi (
    id              VARCHAR PRIMARY KEY,
    source          VARCHAR NOT NULL,        -- 'ai' | 'user'
    name_el         VARCHAR NOT NULL,
    name_en         VARCHAR,
    description     VARCHAR,
    polygon_wkt     VARCHAR NOT NULL,        -- WKT — DuckDB spatial reads this
    centroid_lat    DOUBLE,
    centroid_lon    DOUBLE,
    threat_grade    VARCHAR,
    threat_summary  VARCHAR,
    citation_event_ids_json VARCHAR,
    scan_id         VARCHAR,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aoi_source ON aoi (source);
CREATE INDEX IF NOT EXISTS idx_aoi_scan ON aoi (scan_id);

-- Standing scan history. One row per Greece-wide scan run.
CREATE TABLE IF NOT EXISTS scan_runs (
    scan_id         VARCHAR PRIMARY KEY,
    kind            VARCHAR NOT NULL,        -- 'standing' | 'manual' | 'watch'
    bbox_min_lon    DOUBLE NOT NULL,
    bbox_min_lat    DOUBLE NOT NULL,
    bbox_max_lon    DOUBLE NOT NULL,
    bbox_max_lat    DOUBLE NOT NULL,
    time_from       TIMESTAMP NOT NULL,
    time_to         TIMESTAMP NOT NULL,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP,
    status          VARCHAR NOT NULL,        -- 'running' | 'ok' | 'partial' | 'failed'
    sensor_counts_json VARCHAR,
    error           VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_scan_runs_started ON scan_runs (started_at DESC);
