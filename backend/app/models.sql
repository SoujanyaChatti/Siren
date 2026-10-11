-- SIREN schema for TimescaleDB / Tiger Data.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS readings (
  time        TIMESTAMPTZ NOT NULL,
  source      TEXT NOT NULL,         -- usgs, nws_asos, nws, photo
  station_id  TEXT NOT NULL,
  metric      TEXT NOT NULL,         -- stage_ft, rain_in, depth_in, depth_high_in
  value       DOUBLE PRECISION NOT NULL,
  quality     TEXT,                  -- provisional, estimated, verified, unverified
  source_url  TEXT
);
SELECT create_hypertable('readings', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS readings_station_metric_time ON readings (station_id, metric, time DESC);

-- 15-minute rollups the rules engine reads (continuous aggregate, real-time enabled)
CREATE MATERIALIZED VIEW IF NOT EXISTS readings_15m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('15 minutes', time) AS bucket, station_id, metric,
       max(value) AS max_v, last(value, time) AS last_v, sum(value) AS sum_v, count(*) AS n
FROM readings GROUP BY bucket, station_id, metric
WITH NO DATA;

SELECT add_continuous_aggregate_policy('readings_15m', start_offset => INTERVAL '30 days',
  end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);

-- Compression on raw readings (historical storms compress well; see README for measured savings)
ALTER TABLE readings SET (timescaledb.compress, timescaledb.compress_segmentby = 'station_id, metric');
SELECT add_compression_policy('readings', INTERVAL '7 days', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS rule_evaluations (
  id BIGSERIAL, time TIMESTAMPTZ NOT NULL, zone_id TEXT, rule_id TEXT,
  rule_version TEXT, fired BOOLEAN, severity TEXT,
  inputs JSONB, inputs_hash TEXT, missing_data JSONB
);
SELECT create_hypertable('rule_evaluations', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, zone_id TEXT, opened_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ, peak_severity TEXT, status TEXT);

CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, incident_id TEXT, severity TEXT,
  rule_ids TEXT[], text_en TEXT, explanation JSONB, ai_path TEXT, created_at TIMESTAMPTZ);

CREATE TABLE IF NOT EXISTS alert_deliveries (id TEXT PRIMARY KEY, alert_id TEXT, user_id TEXT,
  language TEXT, text TEXT, audio_path TEXT, state TEXT, updated_at TIMESTAMPTZ);

CREATE TABLE IF NOT EXISTS alert_events (time TIMESTAMPTZ NOT NULL, alert_id TEXT, delivery_id TEXT,
  from_state TEXT, to_state TEXT, actor TEXT, note TEXT);

CREATE TABLE IF NOT EXISTS photo_reports (id TEXT PRIMARY KEY, time TIMESTAMPTZ, lat DOUBLE PRECISION,
  lon DOUBLE PRECISION, image_path TEXT, analysis JSONB, status TEXT);

CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT, language TEXT, zone_id TEXT,
  vehicle TEXT, needs JSONB);

CREATE TABLE IF NOT EXISTS audience_sessions (id TEXT PRIMARY KEY, demo_run_id TEXT, language TEXT,
  zone_id TEXT, joined_at TIMESTAMPTZ, last_seen_at TIMESTAMPTZ);

CREATE TABLE IF NOT EXISTS official_warnings (id TEXT PRIMARY KEY, issued_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
  event TEXT, polygon JSONB, source_url TEXT);

CREATE TABLE IF NOT EXISTS lead_time_results (zone_id TEXT, siren_first_alert_at TIMESTAMPTZ, siren_severity TEXT,
  official_warning_id TEXT, official_issued_at TIMESTAMPTZ, lead_minutes DOUBLE PRECISION,
  computed_at TIMESTAMPTZ, notes TEXT);
