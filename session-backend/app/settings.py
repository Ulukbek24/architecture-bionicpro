from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    keycloak_internal_url: str = "http://keycloak:8080"
    keycloak_public_url: str = "http://localhost:8080"
    keycloak_realm: str = "reports-realm"
    keycloak_client_id: str = "reports-frontend"
    keycloak_client_secret: str = "frontend-bff-secret-do-not-use-in-prod"

    bff_public_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    session_secret: str = "change-me-session-secret"
    session_cookie_name: str = "bionicpro_session"

    reports_api_url: str = "http://reports-api:8001"

    class Config:
        env_prefix = ""


settings = Settings()
