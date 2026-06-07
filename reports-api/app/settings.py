from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    keycloak_internal_url: str = "http://keycloak:8080"
    keycloak_realm: str = "reports-realm"
    keycloak_audience: str = "reports-api"

    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "bionic"

    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "bionic-reports"
    s3_public_base_url: str = "http://localhost/cdn"
    presigned_expires_seconds: int = 300

    class Config:
        env_prefix = ""


settings = Settings()
