# services/scheduler/main.py
# Lightweight scheduler: auto-downloads IRSA PDFs + FFD bulletins daily, retrains ML models.
import sys
import os
import time
import logging
from datetime import date, timedelta

# Ensure aquavision-service is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "aquavision-service"))

import schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")


def job_ingest_irsa():
    """Download yesterday's IRSA PDF → parse → store → threshold engine."""
    from infrastructure.ingestion.irsa_downloader import auto_ingest_irsa

    target = date.today() - timedelta(days=1)
    logger.info(f"Starting IRSA ingestion for {target}...")
    try:
        result = auto_ingest_irsa(target)
        if "error" in result:
            logger.error(f"Ingestion failed: {result['error']}")
        else:
            logger.info(f"Ingestion OK: stored={result.get('stored', 0)}")
    except Exception as e:
        logger.exception(f"Ingestion error: {e}")


def job_ingest_ffd():
    """Scrape FFD bulletin → store → threshold engine."""
    from infrastructure.ingestion.ffd_ingest import ingest_ffd_bulletin

    logger.info("Starting FFD bulletin ingestion...")
    try:
        result = ingest_ffd_bulletin()
        logger.info(f"FFD OK: stored={result.get('stored', 0)}")
    except Exception as e:
        logger.exception(f"FFD ingestion error: {e}")


def job_train_models():
    """Retrain XGBoost flood prediction models."""
    from ml.train_flood_model import train_all_assets

    logger.info("Starting ML model retraining...")
    try:
        results = train_all_assets(horizons=[7])
        trained = len([r for r in results if "error" not in r])
        logger.info(f"Training complete: {trained} models trained")
    except Exception as e:
        logger.exception(f"Training error: {e}")


if __name__ == "__main__":
    # Schedule: daily at 06:30 PKT (01:30 UTC)
    schedule.every().day.at("01:30").do(job_ingest_irsa)

    # FFD: daily at 06:00 PKT (01:00 UTC) — before IRSA
    schedule.every().day.at("01:00").do(job_ingest_ffd)

    # ML retrain: weekly on Sunday at 03:00 UTC (08:00 PKT)
    schedule.every().sunday.at("03:00").do(job_train_models)

    logger.info("Scheduler started. Waiting for next run...")
    logger.info(f"Next run: {schedule.next_run()}")

    # Run once on startup
    logger.info("Running initial ingestion...")
    job_ingest_irsa()

    while True:
        schedule.run_pending()
        time.sleep(60)
