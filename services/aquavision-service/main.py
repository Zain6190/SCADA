# main.py
# AquaVision Service - FastAPI entrypoint.
# Exposes /water/* endpoints (gateway routes /water/* -> this service).
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aquavision")


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
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="AquaVision AI - Water Monitoring & Early Warning (IBCP-SCADA)",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from presentation.http.routers import (  # noqa: E402
    alerts,
    health,
    indicators,
    map_data,
    overview,
    predictions,
    regions,
    reports,
    thresholds,
)

WATER_PREFIX = "/water"
TAG = ["AquaVision"]

app.include_router(health.router)
app.include_router(overview.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(map_data.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(indicators.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(predictions.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(alerts.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(reports.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(thresholds.router, prefix=WATER_PREFIX, tags=TAG)
app.include_router(regions.router, prefix=WATER_PREFIX, tags=TAG)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "docs": "/docs",
    }
