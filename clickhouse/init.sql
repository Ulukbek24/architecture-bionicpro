CREATE DATABASE IF NOT EXISTS bionic;

CREATE TABLE IF NOT EXISTS bionic.prosthetic_events
(
    event_time     DateTime,
    prosthetic_id  String,
    user_id        String,
    event_type     LowCardinality(String),
    actuator_id    String,
    mio_signal     Float64,
    battery_level  Float32,
    latency_ms     UInt16
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (prosthetic_id, event_time)
TTL event_time + INTERVAL 2 YEAR;

CREATE TABLE IF NOT EXISTS bionic.usage_daily
(
    report_date    Date,
    prosthetic_id  String,
    user_id        String,
    events_total   UInt64,
    avg_latency_ms Float32,
    avg_battery    Float32,
    error_events   UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(report_date)
ORDER BY (prosthetic_id, report_date);
