# packages/backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Environment: "development" or "production".
    ENVIRONMENT: str = "development"

    # Database (Docker PostGIS container: postgis/postgis:16-3.4 on port 5433).
    # Must be supplied via env (DATABASE_URL) in production; the dev fallback
    # below only applies in development.
    DATABASE_URL: str = "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # MQTT
    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 1883

    # JWT - SECRET_KEY must be set from env in production.
    SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Public registration is disabled by default; enable only for local dev.
    ALLOW_PUBLIC_REGISTRATION: bool = False

    # CORS allowlist (comma-separated origins).
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # GEE
    GEE_PROJECT: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")

    def validate_security(self) -> None:
        """Fail fast in production if insecure defaults are still in use."""
        if self.is_production:
            insecure = (
                "dev-only-insecure-secret-change-me" in self.SECRET_KEY
                or "change-in-production" in self.SECRET_KEY
            )
            if insecure:
                raise RuntimeError(
                    "SECRET_KEY must be set from environment in production."
                )
            if "postgres:1234@" in self.DATABASE_URL:
                raise RuntimeError(
                    "DATABASE_URL uses the default dev password; set it from "
                    "environment in production."
                )


settings = Settings()