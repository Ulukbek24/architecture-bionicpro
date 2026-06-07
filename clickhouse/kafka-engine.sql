-- Stream consumers + materialized views for CDC pipeline from CRM via Debezium.

CREATE DATABASE IF NOT EXISTS bionic_cdc;

-- Raw Kafka stream for prosthetic_events table.
-- Debezium (adaptive_time_microseconds) emits TIMESTAMP as int64 microseconds
-- since epoch, so we read it as Int64 and convert in the MV.
DROP TABLE IF EXISTS bionic_cdc.prosthetic_events_kafka;
CREATE TABLE bionic_cdc.prosthetic_events_kafka
(
    event_id       Int64,
    event_time     Int64,
    prosthetic_id  String,
    user_id        String,
    event_type     String,
    actuator_id    String,
    mio_signal     Float64,
    battery_level  Float32,
    latency_ms     UInt16,
    __deleted      String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list  = 'crm.public.prosthetic_events',
    kafka_group_name  = 'clickhouse-prosthetic-events',
    kafka_format      = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_skip_broken_messages = 1000;

-- Materialized view pushes Kafka rows into the same analytic fact table that
-- the daily Airflow ETL writes to. Both paths converge so reports-api stays
-- source-agnostic.
DROP TABLE IF EXISTS bionic_cdc.prosthetic_events_mv;
CREATE MATERIALIZED VIEW bionic_cdc.prosthetic_events_mv
TO bionic.prosthetic_events AS
SELECT
    toDateTime(fromUnixTimestamp64Micro(event_time)) AS event_time,
    prosthetic_id,
    user_id,
    event_type,
    actuator_id,
    mio_signal,
    battery_level,
    latency_ms
FROM bionic_cdc.prosthetic_events_kafka
WHERE __deleted = 'false';

-- Real-time aggregate for the reports dashboard.
DROP TABLE IF EXISTS bionic.usage_realtime;
CREATE TABLE bionic.usage_realtime
(
    bucket_minute  DateTime,
    prosthetic_id  String,
    user_id        String,
    events_total   UInt64,
    avg_latency_ms Float32,
    error_events   UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(bucket_minute)
ORDER BY (prosthetic_id, bucket_minute);

DROP TABLE IF EXISTS bionic_cdc.usage_realtime_mv;
CREATE MATERIALIZED VIEW bionic_cdc.usage_realtime_mv
TO bionic.usage_realtime AS
SELECT
    toStartOfMinute(toDateTime(fromUnixTimestamp64Micro(event_time))) AS bucket_minute,
    prosthetic_id,
    user_id,
    count()                                    AS events_total,
    avg(latency_ms)                            AS avg_latency_ms,
    countIf(event_type = 'error')              AS error_events
FROM bionic_cdc.prosthetic_events_kafka
WHERE __deleted = 'false'
GROUP BY bucket_minute, prosthetic_id, user_id;
