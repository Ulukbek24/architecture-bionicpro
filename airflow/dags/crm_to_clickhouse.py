from datetime import datetime, timedelta

import clickhouse_connect
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

CRM_CONN_ID = "crm_postgres"
CLICKHOUSE_HOST = "clickhouse"
CLICKHOUSE_PORT = 8123
CLICKHOUSE_USER = "default"
CLICKHOUSE_PASSWORD = ""

default_args = {
    "owner": "bionicpro-data",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "start_date": datetime(2025, 1, 1),
}


def _ch_client():
    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        database="bionic",
    )


def extract_events(**context):
    """Pull yesterday's events from CRM, hand off via XCom."""
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=CRM_CONN_ID)
    rows = hook.get_records(
        """
        SELECT event_time,
               prosthetic_id,
               user_id,
               event_type,
               actuator_id,
               mio_signal,
               battery_level,
               latency_ms
        FROM prosthetic_events
        WHERE event_time >= %s::date
          AND event_time <  (%s::date + INTERVAL '1 day')
        """,
        parameters=(ds, ds),
    )
    return [list(row) for row in rows]


def load_events(**context):
    rows = context["ti"].xcom_pull(task_ids="extract_events") or []
    if not rows:
        return 0
    client = _ch_client()
    client.insert(
        "prosthetic_events",
        rows,
        column_names=[
            "event_time",
            "prosthetic_id",
            "user_id",
            "event_type",
            "actuator_id",
            "mio_signal",
            "battery_level",
            "latency_ms",
        ],
    )
    return len(rows)


def build_daily_aggregate(**context):
    ds = context["ds"]
    client = _ch_client()
    client.command(
        """
        INSERT INTO bionic.usage_daily
        SELECT toDate(event_time)              AS report_date,
               prosthetic_id,
               user_id,
               count()                         AS events_total,
               avg(latency_ms)                 AS avg_latency_ms,
               avg(battery_level)              AS avg_battery,
               countIf(event_type = 'error')   AS error_events
        FROM bionic.prosthetic_events
        WHERE toDate(event_time) = toDate(%(ds)s)
        GROUP BY report_date, prosthetic_id, user_id
        """,
        parameters={"ds": ds},
    )


with DAG(
    dag_id="crm_to_clickhouse_daily",
    default_args=default_args,
    description="Daily ETL: CRM prosthetic_events -> ClickHouse facts + aggregates",
    schedule_interval="0 1 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["bionicpro", "etl"],
) as dag:
    extract = PythonOperator(task_id="extract_events", python_callable=extract_events)
    load = PythonOperator(task_id="load_events", python_callable=load_events)
    aggregate = PythonOperator(task_id="build_daily_aggregate", python_callable=build_daily_aggregate)

    extract >> load >> aggregate
