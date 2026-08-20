# main.py
# AquaVision Service - FastAPI entrypoint.
# Exposes /water/* endpoints (gateway routes /water/* -> this service).
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config.settings import settings

# ─── Structured JSON Logging ───────────────────────────────────────────────
if settings.LOG_FORMAT == "json":
    try:
        from pythonjsonlogger.json import JsonFormatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        ))
        logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO), handlers=[handler])
    except ImportError:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
else:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

logger = logging.getLogger("aquavision")

# ─── Rate Limiter ──────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    storage_uri="memory://",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify DB connectivity + fill demo data if tables are empty.
    from infrastructure.db.engine import engine
    from infrastructure.db.seed import seed_if_empty

    with engine.connect():
        logger.info("DB connection OK")
    try:
        seed_if_empty()
    except Exception as exc:  # pragma: no cover - non-fatal for startup
        logger.warning("Seeding skipped: %s", exc)

    # Wire notification dispatcher
    from infrastructure.notifications.dispatcher import NotificationDispatcher
    from infrastructure.notifications.email_notifier import EmailNotifier
    from infrastructure.notifications.slack_notifier import SlackNotifier
    from infrastructure.db.engine import SessionLocal

    notifiers = []
    if settings.SMTP_HOST and settings.SMTP_USERNAME:
        notifiers.append(EmailNotifier(
            smtp_host=settings.SMTP_HOST,
            smtp_port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            from_addr=settings.SMTP_FROM or settings.SMTP_USERNAME,
            use_tls=settings.SMTP_USE_TLS,
        ))
        logger.info(f"Email notifier configured: {settings.SMTP_HOST}:{settings.SMTP_PORT}")

    if settings.SLACK_WEBHOOK_URL:
        notifiers.append(SlackNotifier(webhook_url=settings.SLACK_WEBHOOK_URL))
        logger.info("Slack notifier configured")

    if not notifiers:
        logger.warning("No notification channels configured (set SMTP_* or SLACK_WEBHOOK_URL env vars)")

    # Store dispatcher on app state for use by threshold engine
    db_session = SessionLocal()
    app.state.notification_dispatcher = NotificationDispatcher(db_session, notifiers)
    app.state.notification_notifiers = notifiers

    yield

    db_session.close()


app = FastAPI(
    title=settings.APP_NAME,
    description="AquaVision AI - Water Monitoring & Early Warning (IBCP-SCADA)",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ─── Middleware ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info(
        "%s %s %s %sms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ─── Routers ───────────────────────────────────────────────────────────────
from presentation.http.routers import (  # noqa: E402
    alerts,
    auth,
    health,
    impact,
    indicators,
    map_data,
    operational,
    overview,
    predictions,
    regions,
    reports,
    sensors,
    thresholds,
    validation,
)
from ml.prediction_api import router as ml_router

WATER_PREFIX = "/water"
TAG = ["AquaVision"]

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(validation.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(overview.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(map_data.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(indicators.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(predictions.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(alerts.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(reports.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(thresholds.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(operational.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(regions.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(ml_router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(impact.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(sensors.router, prefix=WATER_PREFIX, tags=TAG)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "docs": "/docs",
    }
