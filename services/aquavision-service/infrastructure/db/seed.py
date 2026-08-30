# infrastructure/db/seed.py
# Idempotent demo seeding for local development - only fills empty tables.
# Real data comes from the AquaVision ETL/ML pipeline (ml-pipeline).
#
# PIPELINE TABLES (water_predictions_weekly, water_alerts, water_indicators_weekly,
# water_reports) are NEVER seeded here. The ML pipeline writes real data to these.
# Only reference/config tables (assets, thresholds, regions) should be seeded.
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterAlert, WaterIndicator, WaterPrediction, WaterReport

# Tables that the ML pipeline populates — NEVER seed these
PIPELINE_TABLES = {
    "water_indicators_weekly",
    "water_predictions_weekly",
    "water_alerts",
    "water_reports",
}


def seed_if_empty() -> None:
    """Seeds demo data ONLY for reference tables. Pipeline tables are skipped."""
    # Pipeline tables are populated by run_pipeline.py / predict_weekly / run_risk_alerts
    # Never seed them — real data overwrites seed on first pipeline run.
    pass
