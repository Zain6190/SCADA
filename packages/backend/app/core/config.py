# packages/backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Environment: "development" or "production".
    ENVIRONMENT: str = "development"

    # Database — set DATABASE_URL in .env. The dev fallback only works when
    # the PostGIS container is running on port 5433.
    DATABASE_URL: str = "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"

    # Redis / MQTT
    REDIS_URL: str = "redis://localhost:6379"
    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 1883

    # JWT — generate for production: python -c "import secrets; print(secrets.token_urlsafe(64))"
    SECRET_KEY: str = ""
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
        """Fail fast if required secrets are missing or insecure defaults are
        still in use."""
        if not self.SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY is not set. Add it to your .env file.\n"
                "  Generate one: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        if self.is_production:
            if "postgres:1234@" in self.DATABASE_URL:
                raise RuntimeError(
                    "DATABASE_URL uses the default dev password; set it from "
                    "environment in production."
                )


settings = Settings()