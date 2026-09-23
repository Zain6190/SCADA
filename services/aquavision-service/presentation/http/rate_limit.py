# presentation/http/rate_limit.py
# Single shared slowapi Limiter instance (app.state.limiter + route decorators).
from slowapi import Limiter
from slowapi.util import get_remote_address

from config.settings import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    storage_uri="memory://",
)
