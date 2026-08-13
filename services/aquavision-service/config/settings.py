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

    # Database — set DATABASE_URL in .env
    DATABASE_URL: str = ""
    DB_ECHO: bool = False

    # Logical schema names
    AQUAVISION_SCHEMA: str = "aquavision"
    SHARED_SCHEMA: str = "shared"
    SYSTEM_SCHEMA: str = "system"

    # Cross-context access policy:
    #   write: aquavision.* only
    #   read:  shared.regions + shared.assets (never write)
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


settings = Settings()
