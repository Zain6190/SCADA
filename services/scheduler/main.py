# services/scheduler/main.py
# Lightweight scheduler with pipeline locking, heartbeat, and run tracking.
# Auto-downloads IRSA PDFs + FFD bulletins daily, retrains ML models.
import sys
import os
import time
import logging
import socket
import uuid
from datetime import date, datetime, timedelta, timezone

# Ensure aquavision-service is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "aquavision-service"))

import schedule
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")

# Scheduler identity
INSTANCE_ID = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
SERVICE_NAME = "scheduler"


def get_db_session():
    """Get a database session."""
    from infrastructure.db.engine import SessionLocal
    return SessionLocal()


def acquire_pipeline_lock(conn, pipeline_type: str) -> bool:
    """Try to acquire an advisory lock for this pipeline type."""
    lock_key = hash(pipeline_type) % (2**31)
    result = conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key})
    return result.scalar()


def release_pipeline_lock(conn, pipeline_type: str):
    """Release the advisory lock."""
    lock_key = hash(pipeline_type) % (2**31)
    conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})


def update_heartbeat():
    """Update scheduler heartbeat in database."""
    from infrastructure.db.models import SchedulerHeartbeat
    from sqlalchemy.dialects.postgresql import insert
    
    with get_db_session() as session:
        stmt = insert(SchedulerHeartbeat).values(
            service_name=SERVICE_NAME,
            instance_id=INSTANCE_ID,
            host_name=socket.gethostname(),
            process_id=os.getpid(),
            started_at=datetime.now(timezone.utc),
            last_heartbeat_at=datetime.now(timezone.utc),
            status="RUNNING",
        ).on_conflict_do_update(
            index_elements=["service_name", "instance_id"],
            set_={
                "last_heartbeat_at": datetime.now(timezone.utc),
                "status": "RUNNING",
            }
        )
        session.execute(stmt)
        session.commit()


def create_pipeline_run(conn, pipeline_type: str, trigger_type: str = "SCHEDULED") -> str:
    """Create a new pipeline run record."""
    run_id = f"{pipeline_type}-{date.today().strftime('%Y-%m-%d')}-{datetime.now().strftime('%H%M%S')}"
    conn.execute(
        text("""
            INSERT INTO aquavision.pipeline_runs (run_id, pipeline_type, status, trigger_type, started_at)
            VALUES (:run_id, :pipeline_type, 'RUNNING', :trigger_type, :started_at)
        """),
        {
            "run_id": run_id,
            "pipeline_type": pipeline_type,
            "trigger_type": trigger_type,
            "started_at": datetime.now(timezone.utc),
        }
    )
    conn.commit()
    return run_id


def complete_pipeline_run(conn, run_id: str, status: str, error_message: str = None):
    """Mark a pipeline run as complete."""
    conn.execute(
        text("""
            UPDATE aquavision.pipeline_runs
            SET status = :status,
                completed_at = :completed_at,
                error_message = :error_message,
                duration_seconds = EXTRACT(EPOCH FROM (:completed_at - started_at))
            WHERE run_id = :run_id
        """),
        {
            "run_id": run_id,
            "status": status,
            "completed_at": datetime.now(timezone.utc),
            "error_message": error_message,
        }
    )
    conn.commit()


def job_ingest_irsa():
    """Download yesterday's IRSA PDF with pipeline locking."""
    from infrastructure.ingestion.irsa_downloader import auto_ingest_irsa

    pipeline_type = "IRSA"
    target = date.today() - timedelta(days=1)
    
    with get_db_session() as conn:
        # Try to acquire lock
        if not acquire_pipeline_lock(conn, pipeline_type):
            logger.warning(f"Skipping {pipeline_type} ingestion - another run in progress")
            return
        
        run_id = create_pipeline_run(conn, pipeline_type)
        
        try:
            logger.info(f"Starting IRSA ingestion for {target}...")
            result = auto_ingest_irsa(target)
            
            if "error" in result:
                complete_pipeline_run(conn, run_id, "FAILED", result["error"])
                logger.error(f"Ingestion failed: {result['error']}")
            else:
                complete_pipeline_run(conn, run_id, "SUCCESS")
                logger.info(f"Ingestion OK: stored={result.get('stored', 0)}")
        except Exception as e:
            complete_pipeline_run(conn, run_id, "FAILED", str(e))
            logger.exception(f"Ingestion error: {e}")
        finally:
            release_pipeline_lock(conn, pipeline_type)


def job_ingest_ffd():
    """Scrape FFD bulletin with pipeline locking."""
    from infrastructure.ingestion.ffd_ingest import ingest_ffd_bulletin

    pipeline_type = "FFD"
    
    with get_db_session() as conn:
        if not acquire_pipeline_lock(conn, pipeline_type):
            logger.warning(f"Skipping {pipeline_type} ingestion - another run in progress")
            return
        
        run_id = create_pipeline_run(conn, pipeline_type)
        
        try:
            logger.info("Starting FFD bulletin ingestion...")
            result = ingest_ffd_bulletin()
            
            if result.get("fetch_status") == "FAILED":
                complete_pipeline_run(conn, run_id, "FAILED", result.get("error"))
                logger.error(f"FFD ingestion failed: {result.get('error')}")
            else:
                complete_pipeline_run(conn, run_id, "SUCCESS")
                logger.info(f"FFD OK: stored={result.get('stored', 0)}")
        except Exception as e:
            complete_pipeline_run(conn, run_id, "FAILED", str(e))
            logger.exception(f"FFD ingestion error: {e}")
        finally:
            release_pipeline_lock(conn, pipeline_type)


def job_train_models():
    """Retrain XGBoost flood prediction models."""
    from ml.train_flood_model import train_all_assets

    pipeline_type = "ML"
    
    with get_db_session() as conn:
        if not acquire_pipeline_lock(conn, pipeline_type):
            logger.warning(f"Skipping {pipeline_type} training - another run in progress")
            return
        
        run_id = create_pipeline_run(conn, pipeline_type)
        
        try:
            logger.info("Starting ML model retraining...")
            results = train_all_assets(horizons=[7])
            trained = len([r for r in results if "error" not in r])
            complete_pipeline_run(conn, run_id, "SUCCESS")
            logger.info(f"Training complete: {trained} models trained")
        except Exception as e:
            complete_pipeline_run(conn, run_id, "FAILED", str(e))
            logger.exception(f"Training error: {e}")
        finally:
            release_pipeline_lock(conn, pipeline_type)


def job_run_wai_pipeline():
    """Run the weekly WAI prediction + alert pipeline."""
    import subprocess

    pipeline_type = "WAI_PIPELINE"
    ml_root = os.path.join(os.path.dirname(__file__), "..", "..", "packages", "ml-pipeline")

    with get_db_session() as conn:
        if not acquire_pipeline_lock(conn, pipeline_type):
            logger.warning(f"Skipping {pipeline_type} - another run in progress")
            return

        run_id = create_pipeline_run(conn, pipeline_type)

        try:
            logger.info("Starting WAI pipeline (sync_indicators, predict_weekly, run_risk_alerts)...")
            result = subprocess.run(
                [sys.executable, "-m", "scripts.run_pipeline", "--trigger", "SCHEDULED"],
                cwd=ml_root,
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if result.returncode == 0:
                complete_pipeline_run(conn, run_id, "SUCCESS")
                logger.info("WAI pipeline complete")
            else:
                complete_pipeline_run(conn, run_id, "FAILED", result.stdout[-500:] if result.stdout else result.stderr[-500:])
                logger.error(f"WAI pipeline failed: rc={result.returncode}")
        except subprocess.TimeoutExpired:
            complete_pipeline_run(conn, run_id, "FAILED", "Timeout after 3600s")
            logger.error("WAI pipeline timed out")
        except Exception as e:
            complete_pipeline_run(conn, run_id, "FAILED", str(e))
            logger.exception(f"WAI pipeline error: {e}")
        finally:
            release_pipeline_lock(conn, pipeline_type)


def job_refresh_weather():
    """Refresh weather forecasts for all active assets (every 6 hours)."""
    pipeline_type = "WEATHER_REFRESH"

    with get_db_session() as session:
        if not acquire_pipeline_lock(session, pipeline_type):
            logger.warning(f"Skipping {pipeline_type} - another run in progress")
            return

        run_id = create_pipeline_run(session, pipeline_type)

        try:
            from ml.features.weather_service import WeatherService
            ws = WeatherService(session)
            count = ws.refresh_all_assets()
            complete_pipeline_run(session, run_id, "SUCCESS")
            logger.info(f"Weather refresh complete: {count} forecast rows")
        except Exception as e:
            complete_pipeline_run(session, run_id, "FAILED", str(e))
            logger.exception(f"Weather refresh error: {e}")
        finally:
            release_pipeline_lock(session, pipeline_type)


if __name__ == "__main__":
    # Schedule: daily at 06:30 PKT (01:30 UTC)
    schedule.every().day.at("01:30").do(job_ingest_irsa)

    # FFD: daily at 06:00 PKT (01:00 UTC) — before IRSA
    schedule.every().day.at("01:00").do(job_ingest_ffd)

    # ML retrain: weekly on Sunday at 03:00 UTC (08:00 PKT)
    schedule.every().sunday.at("03:00").do(job_train_models)

    # WAI pipeline: weekly on Sunday at 04:00 UTC (09:00 PKT) — after ML retrain
    schedule.every().sunday.at("04:00").do(job_run_wai_pipeline)

    # Weather forecasts: every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
    schedule.every(6).hours.do(job_refresh_weather)

    # Heartbeat: every 5 minutes
    schedule.every(5).minutes.do(update_heartbeat)

    logger.info(f"Scheduler started (instance: {INSTANCE_ID})")
    logger.info(f"Next run: {schedule.next_run()}")

    # Initial heartbeat
    update_heartbeat()

    # Run once on startup
    logger.info("Running initial ingestion...")
    job_ingest_irsa()

    while True:
        schedule.run_pending()
        time.sleep(60)
