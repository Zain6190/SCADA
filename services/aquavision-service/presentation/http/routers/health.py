# presentation/http/routers/health.py
# Health endpoints for AquaVision service.
# Liveness: Process is running
# Readiness: Database and migrations are ready
# Pipeline Health: Last pipeline runs and scheduler status (admin only)
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session

router = APIRouter(tags=["Health"])


@router.get("/health/live")
async def liveness():
    """Liveness probe - checks only that the process is running."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(session: Session = Depends(get_session)):
    """Readiness probe - checks database connectivity and migration state."""
    db_ok = False
    migrations_ok = False

    try:
        session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    if db_ok:
        try:
            from alembic.runtime.migration import MigrationContext
            context = MigrationContext.configure(session.connection())
            context.get_current_dimension()
            migrations_ok = True
        except Exception:
            migrations_ok = False

    status = "ready" if (db_ok and migrations_ok) else "not_ready"

    return {
        "status": status,
        "database": "ok" if db_ok else "error",
        "migrations": "ok" if migrations_ok else "outdated",
    }


@router.get("/api/v1/admin/pipeline-health")
async def pipeline_health(session: Session = Depends(get_session)):
    """Pipeline health endpoint - shows last runs and scheduler status."""
    try:
        from infrastructure.db.models import PipelineRun, SchedulerHeartbeat
    except Exception:
        return {
            "api_status": "ready",
            "scheduler_status": "unknown",
            "last_irsa_run": None,
            "last_ffd_run": None,
            "data_freshness": {"irsa_hours": None, "ffd_hours": None},
        }

    def safe_run_info(run):
        if not run:
            return None
        stages = run.stages if hasattr(run, 'stages') and run.stages else []
        return {
            "status": run.status,
            "run_id": run.run_id,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "records_stored": stages[-1].records_stored if stages else None,
        }

    def get_freshness(run):
        if not run or not run.completed_at:
            return None
        now = datetime.now(timezone.utc)
        completed = run.completed_at
        if completed.tzinfo is None:
            completed = completed.replace(tzinfo=timezone.utc)
        return (now - completed).total_seconds() / 3600

    try:
        last_irsa = session.execute(
            select(PipelineRun).where(
                PipelineRun.pipeline_type == "IRSA"
            ).order_by(PipelineRun.started_at.desc())
        ).scalar_one_or_none()
    except Exception:
        last_irsa = None

    try:
        last_ffd = session.execute(
            select(PipelineRun).where(
                PipelineRun.pipeline_type == "FFD"
            ).order_by(PipelineRun.started_at.desc())
        ).scalar_one_or_none()
    except Exception:
        last_ffd = None

    scheduler_status = "unknown"
    try:
        heartbeat = session.execute(
            select(SchedulerHeartbeat).where(
                SchedulerHeartbeat.service_name == "scheduler"
            ).order_by(SchedulerHeartbeat.last_heartbeat_at.desc())
        ).scalar_one_or_none()

        if heartbeat:
            age_minutes = (datetime.now(timezone.utc) - heartbeat.last_heartbeat_at).total_seconds() / 60
            if age_minutes < 5:
                scheduler_status = "running"
            elif age_minutes < 15:
                scheduler_status = "delayed"
            else:
                scheduler_status = "unhealthy"
    except Exception:
        pass

    return {
        "api_status": "ready",
        "scheduler_status": scheduler_status,
        "last_irsa_run": safe_run_info(last_irsa),
        "last_ffd_run": safe_run_info(last_ffd),
        "data_freshness": {
            "irsa_hours": get_freshness(last_irsa),
            "ffd_hours": get_freshness(last_ffd),
        },
    }
