# services/scheduler/main.py
# Lightweight scheduler: auto-downloads IRSA PDFs daily at 06:30 PKT.
import sys
import time
import logging
from datetime import date, timedelta

import schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")


def job_ingest_irsa():
    """Download yesterday's IRSA PDF → parse → store."""
    from infrastructure.ingestion.irsa_downloader import auto_ingest_irsa

    target = date.today() - timedelta(days=1)
    logger.info(f"Starting IRSA ingestion for {target}...")
    try:
        result = auto_ingest_irsa(target)
        if "error" in result:
            logger.error(f"Ingestion failed: {result['error']}")
        else:
            logger.info(f"Ingestion OK: {result}")
    except Exception as e:
        logger.exception(f"Ingestion error: {e}")


if __name__ == "__main__":
    # Schedule: daily at 06:30 PKT (01:30 UTC)
    schedule.every().day.at("01:30").do(job_ingest_irsa)

    logger.info("Scheduler started. Waiting for next run...")
    logger.info(f"Next run: {schedule.next_run()}")

    # Run once on startup (optional: comment out to skip)
    logger.info("Running initial ingestion...")
    job_ingest_irsa()

    while True:
        schedule.run_pending()
        time.sleep(60)
