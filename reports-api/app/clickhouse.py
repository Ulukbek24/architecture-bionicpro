import clickhouse_connect

from .settings import settings


def get_client():
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )


def fetch_user_report(prosthetic_ids: list[str]) -> dict:
    if not prosthetic_ids:
        return {"prosthetic_ids": [], "rows": []}
    client = get_client()
    rows = client.query(
        """
        SELECT report_date,
               prosthetic_id,
               events_total,
               avg_latency_ms,
               avg_battery,
               error_events
        FROM bionic.usage_daily
        WHERE prosthetic_id IN %(ids)s
        ORDER BY report_date DESC, prosthetic_id
        LIMIT 365
        """,
        parameters={"ids": prosthetic_ids},
    ).result_rows
    return {
        "prosthetic_ids": prosthetic_ids,
        "rows": [
            {
                "report_date": str(r[0]),
                "prosthetic_id": r[1],
                "events_total": r[2],
                "avg_latency_ms": float(r[3]) if r[3] is not None else None,
                "avg_battery": float(r[4]) if r[4] is not None else None,
                "error_events": r[5],
            }
            for r in rows
        ],
    }
