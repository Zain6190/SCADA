# config/settings.py
# AquaVision service configuration - env-driven, no hard-coded secrets.
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Service
    APP_NAME: str = "aquavision-service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = ""
    DB_ECHO: bool = False

    # Schemas
    AQUAVISION_SCHEMA: str = "aquavision"
    SHARED_SCHEMA: str = "shared"
    SYSTEM_SCHEMA: str = "system"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000",
                               "https://ibcp-scada.vercel.app"]

    # JWT Auth
    JWT_SECRET: str = "change-me-in-production-use-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480  # 8 hours

    # Rate Limiting (requests per minute per IP)
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10

    # Notifications - Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True
    ALERT_RECIPIENTS: str = ""  # Comma-separated email addresses

    # Notifications - Slack
    SLACK_WEBHOOK_URL: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" or "text"


settings = Settings()
