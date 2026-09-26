"""Resolve database URLs from environment variables or the repo-root .env file."""
import os
from pathlib import Path

DEFAULT_LOCAL_URL = "postgresql://postgres:1234@localhost:5433/ibcp_scada"


def _repo_env() -> dict:
    for root in Path(__file__).resolve().parents:
        env_file = root / ".env"
        if env_file.is_file():
            values = {}
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values.setdefault(key.strip(), value.strip())
            return values
    return {}


def neon_url() -> str:
    url = os.environ.get("NEON_DATABASE_URL") or _repo_env().get("NEON_DATABASE_URL")
    if not url:
        url = os.environ.get("DATABASE_URL") or _repo_env().get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set - copy .env.example to .env at the repo root "
            "and paste your Neon connection string"
        )
    return url


def local_url(default: str = DEFAULT_LOCAL_URL) -> str:
    return (
        os.environ.get("LOCAL_DATABASE_URL")
        or _repo_env().get("LOCAL_DATABASE_URL")
        or default
    )
