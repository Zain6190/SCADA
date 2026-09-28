"""Process-local TTL cache for the flood-map territory payload."""
import time
from typing import Optional

TERRITORY_CACHE_SECONDS = 30.0

_payload: Optional[dict] = None
_expires_at: float = 0.0


def get_flood_territory() -> Optional[dict]:
    if _payload is not None and time.monotonic() < _expires_at:
        return _payload
    return None


def set_flood_territory(payload: dict) -> dict:
    global _payload, _expires_at
    _payload = payload
    _expires_at = time.monotonic() + TERRITORY_CACHE_SECONDS
    return payload


def invalidate_flood_territory() -> None:
    global _payload, _expires_at
    _payload = None
    _expires_at = 0.0
