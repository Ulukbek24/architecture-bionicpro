# BionicPRO — Sprint 9 (Архитектура)

Решение четырёх заданий по проекту BionicPRO: SSO/PKCE, ETL-отчёты,
S3+CDN, и CDC через Debezium → Kafka → ClickHouse.

Запуск окружения:

```bash
docker-compose up -d --build
# регистрация Debezium-коннектора, после того как kafka-connect поднимется:
curl -X POST -H "Content-Type: application/json" \
     --data @debezium/crm-postgres-connector.json \
     http://localhost:8083/connectors
```

Точки входа:

| URL                              | Назначение                                |
|----------------------------------|-------------------------------------------|
| http://localhost                 | Nginx (frontend + /auth, /api, /cdn)      |
| http://localhost:3000            | Frontend (dev)                            |
| http://localhost:8000            | session-backend (BFF)                     |
| http://localhost:8001            | reports-api                               |
| http://localhost:8080            | Keycloak (admin / admin)                  |
| http://localhost:8088            | Airflow (admin / admin)                   |
| http://localhost:8123            | ClickHouse HTTP                           |
| http://localhost:9091            | MinIO console (minioadmin / minioadmin)   |
| http://localhost:8083            | Kafka Connect REST                        |

---

## Задание 1. PKCE + сервис сессий + Yandex ID

**Что было сделано:**

- Удалена прямая интеграция `keycloak-js` из фронтенда (`frontend/`),
  фронт больше не видит токенов.
- Поднят `session-backend` (FastAPI, `session-backend/app/`) —
  Backend-For-Frontend, который:
  - стартует Authorization Code Flow с PKCE (S256, `code_verifier`
    хранится в session-store);
  - меняет `code` на access/refresh токен от имени конфиденциального
    клиента `reports-frontend` (секрет в BFF, не на клиенте);
  - кладёт session-id в HttpOnly Secure cookie, токены — только в
    server-side store (`app/sessions.py`);
  - сам валидирует JWT по JWKS (`app/keycloak_client.py`,
    `decode_access_token`) и при необходимости рефрешит токен;
  - проксирует запросы фронта к `reports-api` с Bearer-токеном.
- В realm-export добавлены:
  - `pkce.code.challenge.method = S256` у клиента `reports-frontend`;
  - перевод клиента в `publicClient: false` + client secret;
  - IdP `yandex` (OIDC) c `pkceEnabled=true, pkceMethod=S256` —
    Federated Identity для входа через Яндекс ID;
  - атрибут `prosthetic_ids` у пользователей `prothetic1..3`, который
    маппится в claim access-токена.
- Экспорт реалма после всех манипуляций сохранён в
  `keycloak/keycloak-results-export.json`.
- Диаграмма: `diagrams/task1-pkce-bff.drawio`.

**Закрытая уязвимость из задания:** фронтенд больше не получает
access/refresh токены, секрет клиента и `code_verifier` хранятся
исключительно в BFF — клиента уже нельзя перехватить через DevTools или
расширение браузера.

---

## Задание 2. Сервис отчётов: Airflow + ClickHouse + reports-api

**Что было сделано:**

- ClickHouse-схема `bionic` (`clickhouse/init.sql`):
  - `prosthetic_events` — широкая таблица событий
    (`MergeTree`, partition by month, order by `(prosthetic_id, event_time)`,
    TTL 2 года);
  - `usage_daily` — суточный агрегат
    (`SummingMergeTree`, partition by month, order by `(prosthetic_id, report_date)`).
- Airflow DAG `crm_to_clickhouse_daily`
  (`airflow/dags/crm_to_clickhouse.py`), schedule `0 1 * * *`:
  1. `extract_events` — `PostgresHook` тянет события из CRM за `ds`;
  2. `load_events` — `clickhouse_connect` insert в `prosthetic_events`;
  3. `build_daily_aggregate` — `INSERT … SELECT … GROUP BY` в
     `usage_daily`.
- Airflow собран в собственном образе (`airflow/Dockerfile`) с
  `clickhouse-connect`, `psycopg2-binary`, providers-postgres. Connection
  `crm_postgres` прокинут через переменную окружения
  `AIRFLOW_CONN_CRM_POSTGRES`.
- `reports-api` (`reports-api/app/`):
  - валидирует Bearer JWT по JWKS Keycloak (`app/auth.py`);
  - читает агрегаты из `bionic.usage_daily` (`app/clickhouse.py`);
  - RBAC: admin видит всё, `prothetic_user` — только свои
    `prosthetic_ids` из claim'а; чужие — `403`;
  - после построения отчёта пишет артефакт в S3 и отдаёт CDN-ссылку
    (см. задание 3).
- Диаграмма: `diagrams/task2-reports-pipeline.drawio`.

---

## Задание 3. Снижение нагрузки на БД через S3 + CDN + Nginx

**Что было сделано:**

- MinIO (`minio/minio:RELEASE.2024-04-06`) поднят как S3-совместимый
  blob-store, бакет `bionic-reports` создаётся при первом запросе
  (`reports-api/app/s3.py`, `ensure_bucket`).
- `reports-api` после расчёта отчёта кладёт JSON/CSV-артефакт в S3 по
  ключу `reports/{user_id}/{report_id}.json` и возвращает только
  `key + presigned_url + cdn_url`. В OLTP/ClickHouse сами файлы не
  хранятся — только метаданные.
- Nginx (`nginx/nginx.conf`) выступает edge-CDN:
  - `proxy_cache_path /var/cache/nginx/cdn levels=1:2 keys_zone=cdn_cache:50m max_size=2g inactive=24h`;
  - `location /cdn/` проксирует в MinIO с `proxy_cache_valid 200 12h`;
  - также завернуты `/`, `/auth/`, `/api/`, `/reports-api/`.
- Диаграмма: `diagrams/task3-s3-cdn-nginx.drawio`.

**Эффект:** OLTP-БД не отдаёт байты артефактов, повторные обращения к
одному отчёту обслуживаются из cache-слоя Nginx без обращения к MinIO.

---

## Задание 4. CDC: CRM → Debezium → Kafka → ClickHouse

**Что было сделано:**

- CRM (Postgres) запущен с `wal_level=logical`, `max_wal_senders=10`,
  `max_replication_slots=10` — на Oracle 12 эквивалентно включению
  Logminer / GoldenGate-канала.
- Схема CRM (`crm/init.sql`): `prosthetics`, `orders`,
  `prosthetic_events` с `REPLICA IDENTITY FULL`. Seed-данные
  согласованы с `prosthetic_ids` пользователей в Keycloak, чтобы RBAC
  работал из коробки.
- Kafka + Zookeeper + Kafka Connect (`debezium/connect:2.5`).
- Debezium-коннектор `crm-postgres-connector`
  (`debezium/crm-postgres-connector.json`):
  - `plugin.name = pgoutput`, `slot.name = debezium_crm_slot`;
  - `table.include.list = public.orders,public.prosthetic_events,public.prosthetics`;
  - `transforms = unwrap` (`ExtractNewRecordState`) — мы получаем
    «плоский» row после изменения, не envelope, что упрощает
    Materialized View;
  - топики: `crm.public.orders`, `crm.public.prosthetic_events`,
    `crm.public.prosthetics`.
- ClickHouse-потребитель (`clickhouse/kafka-engine.sql`):
  - `bionic_cdc.prosthetic_events_kafka` — `Engine = Kafka`
    (`JSONEachRow`);
  - `bionic_cdc.prosthetic_events_mv` — `MATERIALIZED VIEW TO
    bionic.prosthetic_events` (та же фактовая таблица, что наполняет
    Airflow — batch и streaming сходятся);
  - `bionic.usage_realtime` (`SummingMergeTree`) + MV
    `usage_realtime_mv` — поминутные real-time агрегаты для дашборда.
- Диаграмма: `diagrams/task4-cdc.drawio`.

**Что это даёт:** `reports-api` остаётся source-agnostic — один и тот же
SQL читает и суточные (Airflow ETL), и поминутные (Kafka MV) агрегаты;
CRM-БД не нагружается аналитическими запросами.

---

## Финальное ревью

| #  | Критерий приёмки                                              | Статус |
|----|---------------------------------------------------------------|--------|
| 1  | Frontend → BFF → Keycloak с PKCE, токенов на клиенте нет      | ✅     |
| 1  | Yandex ID как IdP в Keycloak (OIDC + PKCE)                    | ✅     |
| 1  | `keycloak/keycloak-results-export.json`                       | ✅     |
| 1  | Диаграмма Задания 1                                           | ✅     |
| 2  | Airflow DAG `CRM → ClickHouse` (extract/load/aggregate)       | ✅     |
| 2  | ClickHouse-схема (`prosthetic_events`, `usage_daily`)         | ✅     |
| 2  | `reports-api` ходит в ClickHouse, RBAC по `prosthetic_ids`    | ✅     |
| 2  | Диаграмма Задания 2                                           | ✅     |
| 3  | Артефакты в S3 (MinIO), БД хранит только ключи                | ✅     |
| 3  | Nginx reverse proxy + кэш на `/cdn/`                          | ✅     |
| 3  | Диаграмма Задания 3                                           | ✅     |
| 4  | CRM с logical replication, Debezium PG connector              | ✅     |
| 4  | Kafka топики `crm.public.*`                                   | ✅     |
| 4  | ClickHouse `KafkaEngine` + `MaterializedView`                 | ✅     |
| 4  | Диаграмма Задания 4                                           | ✅     |

**Прогон в Docker (что фактически проверено):**

- Все 14 контейнеров стартуют через `docker compose up -d --build` и
  держатся в `Up` статусе.
- Задание 1: PKCE-флоу выполнен curl'ом (login → Keycloak form-post →
  callback → `/me`); access-токен пользователя `prothetic1` содержит
  claim `prosthetic_ids: ["P-1001","P-1002"]`. `/auth/login?idp=yandex`
  отдаёт redirect c `kc_idp_hint=yandex`.
- Задание 2: Airflow DAG `crm_to_clickhouse_daily` отработал триггером
  на `2026-06-06`, в `bionic.usage_daily` появились агрегаты. Запрос
  `/reports` через BFF вернул 4 строки, отфильтрованные по
  `prosthetic_ids` пользователя.
- Задание 3: артефакт записан в MinIO; CDN URL отдаёт 200 OK,
  второй запрос приходит с `X-Cache-Status: HIT` — Nginx обслуживает из
  кэша, MinIO повторно не дёргается.
- Задание 4: Debezium-коннектор `crm-postgres-connector` в RUNNING,
  топики `crm.public.*` созданы, снапшот ушёл в Kafka, MV в ClickHouse
  затянул его в `bionic.prosthetic_events` и `bionic.usage_realtime`.
  Live-инсерт в Postgres появился в ClickHouse через ~2 секунды.

**Известные оговорки (для прод-настройки):**

1. `KEYCLOAK_CLIENT_SECRET` и `oNwoLQdvJAvRcL89SydqCWCe5ry1jMgq`
   зашиты в `realm-export.json` / `docker-compose.yaml` для удобства
   демо. В прод — вынести в секрет-менеджер.
2. `session-backend/app/sessions.py` — in-memory store. Для прод
   заменить на Redis с TTL = `ssoSessionMaxLifespan`.
3. IdP Yandex поднят с `clientId/clientSecret = placeholder`.
   Перед боевым включением — зарегистрировать приложение в
   `oauth.yandex.ru` и подставить реальные значения.
4. Debezium-коннектор регистрируется отдельным `curl` после старта
   стека (см. выше). В CI/CD это делается через Kafka Connect
   declarative API или Strimzi `KafkaConnector` CR.
5. ClickHouse `Kafka`-таблица настроена с
   `kafka_skip_broken_messages = 1000` — на проде стоит поднять
   alerting на `system.kafka_consumers` и DLQ.
