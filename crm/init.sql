-- CRM OLTP schema (Битрикс24-like) for the BionicPRO sandbox.
-- Real prod runs Oracle 12; here we use Postgres so Debezium can replicate via pgoutput.

CREATE TABLE IF NOT EXISTS prosthetics (
    prosthetic_id   TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    model           TEXT NOT NULL,
    serial_number   TEXT NOT NULL UNIQUE,
    activated_at    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    prosthetic_id   TEXT REFERENCES prosthetics(prosthetic_id),
    status          TEXT NOT NULL,
    amount_rub      NUMERIC(12, 2) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prosthetic_events (
    event_id        BIGSERIAL PRIMARY KEY,
    event_time      TIMESTAMP NOT NULL DEFAULT now(),
    prosthetic_id   TEXT NOT NULL REFERENCES prosthetics(prosthetic_id),
    user_id         TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    actuator_id     TEXT NOT NULL,
    mio_signal      DOUBLE PRECISION NOT NULL,
    battery_level   REAL NOT NULL,
    latency_ms      INT NOT NULL
);

CREATE INDEX IF NOT EXISTS prosthetic_events_time_idx ON prosthetic_events (event_time);
CREATE INDEX IF NOT EXISTS prosthetic_events_pid_idx  ON prosthetic_events (prosthetic_id);

-- Debezium needs REPLICA IDENTITY FULL on tables without a stable PK column
-- it can use for tombstones. Our PKs are fine, but explicit is safer.
ALTER TABLE prosthetics        REPLICA IDENTITY FULL;
ALTER TABLE orders             REPLICA IDENTITY FULL;
ALTER TABLE prosthetic_events  REPLICA IDENTITY FULL;

-- Seed data. prosthetic_ids align with the Keycloak user attributes so RBAC
-- in reports-api returns non-empty results for the demo users.
INSERT INTO prosthetics (prosthetic_id, user_id, model, serial_number) VALUES
    ('P-1001', 'prothetic1', 'BionicArm-X1', 'SN-1001'),
    ('P-1002', 'prothetic1', 'BionicArm-X1', 'SN-1002'),
    ('P-2001', 'prothetic2', 'BionicLeg-Y2', 'SN-2001'),
    ('P-3001', 'prothetic3', 'BionicArm-X2', 'SN-3001'),
    ('P-3002', 'prothetic3', 'BionicArm-X2', 'SN-3002'),
    ('P-3003', 'prothetic3', 'BionicLeg-Y3', 'SN-3003')
ON CONFLICT DO NOTHING;

INSERT INTO orders (user_id, prosthetic_id, status, amount_rub) VALUES
    ('prothetic1', 'P-1001', 'paid',    450000.00),
    ('prothetic1', 'P-1002', 'paid',    450000.00),
    ('prothetic2', 'P-2001', 'paid',    620000.00),
    ('prothetic3', 'P-3001', 'paid',    480000.00),
    ('prothetic3', 'P-3002', 'paid',    480000.00),
    ('prothetic3', 'P-3003', 'shipped', 660000.00);

INSERT INTO prosthetic_events
    (event_time, prosthetic_id, user_id, event_type, actuator_id, mio_signal, battery_level, latency_ms)
SELECT
    now() - (interval '1 minute' * (random() * 60 * 24)::int),
    p.prosthetic_id,
    p.user_id,
    (ARRAY['grip', 'release', 'rotate', 'error'])[1 + (random() * 3)::int],
    'A-' || (1 + (random() * 5)::int),
    random() * 1.0,
    50 + random() * 50,
    20 + (random() * 80)::int
FROM prosthetics p, generate_series(1, 200);
