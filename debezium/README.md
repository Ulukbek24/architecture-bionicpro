# Debezium CDC: CRM → Kafka → ClickHouse

The diagram shows Oracle Database 12 as CRM storage. For the dev environment we
use Postgres with `wal_level=logical`, so Debezium can stream changes via the
`pgoutput` plugin. The same connector pattern works for Oracle — only the
`connector.class` and Logminer-specific options change.

## Register the connector

After `docker-compose up -d` finishes booting:

```bash
curl -X POST -H "Content-Type: application/json" \
  --data @debezium/crm-postgres-connector.json \
  http://localhost:8083/connectors
```

Topics that will appear in Kafka:

- `crm.public.orders`
- `crm.public.prosthetic_events`
- `crm.public.prosthetics`

ClickHouse consumes these topics via the `KafkaEngine` tables defined in
`clickhouse/kafka-engine.sql`, and a `MaterializedView` re-shapes the stream
into the analytic fact tables used by `reports-api`.
