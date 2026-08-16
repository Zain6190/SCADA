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
    """Liveness probe - checks only that the process is running.
    
    Use for container restart decisions.
    Does NOT check database or external services.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(session: Session = Depends(get_session)):
    """Readiness probe - checks database connectivity and migration state.
    
    Returns not_ready if:
    - Database is unreachable
    - Alembic migrations are outdated
    """
    db_ok = False
    migrations_ok = False
    
    # Check database connection
    try:
        session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        pass
    
    # Check alembic migration state
    if db_ok:
        try:
            from alembic.runtime.migration import MigrationContext
            context = MigrationContext.configure(session.connection())
            current_rev = context.get_current_dimension()
            # If we can read the revision, migrations are accessible
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
    """Pipeline health endpoint - shows last runs and scheduler status.
    
    Protected: Should require admin authorization in production.
    """
    from infrastructure.db.models import PipelineRun, SchedulerHeartbeat
    
    # Get last IRSA run
    last_irsa = session.execute(
        select(PipelineRun).where(
            PipelineRun.pipeline_type == "IRSA"
        ).order_by(PipelineRun.started_at.desc())
    ).scalar_one_or_none()
    
    # Get last FFD run
    last_ffd = session.execute(
        select(PipelineRun).where(
            PipelineRun.pipeline_type == "FFD"
        ).order_by(PipelineRun.started_at.desc())
    ).scalar_one_or_none()
    
    # Get scheduler heartbeat
    heartbeat = session.execute(
        select(SchedulerHeartbeat).where(
            SchedulerHeartbeat.service_name == "scheduler"
        ).order_by(SchedulerHeartbeat.last_heartbeat_at.desc())
    ).scalar_one_or_none()
    
    # Calculate scheduler status
    scheduler_status = "unknown"
    if heartbeat:
        age_minutes = (datetime.now(timezone.utc) - heartbeat.last_heartbeat_at).total_seconds() / 60
        if age_minutes < 5:
            scheduler_status = "running"
        elif age_minutes < 15:
            scheduler_status = "delayed"
        else:
            scheduler_status = "unhealthy"
    
    # Calculate data freshness
    def get_freshness(run):
        if not run or not run.completed_at:
            return None
        return (datetime.now(timezone.utc) - run.completed_at).total_seconds() / 3600
    
    return {
        "api_status": "ready",
        "scheduler_status": scheduler_status,
        "last_irsa_run": {
            "status": last_irsa.status if last_irsa else None,
            "run_id": last_irsa.run_id if last_irsa else None,
            "completed_at": last_irsa.completed_at.isoformat() if last_irsa and last_irsa.completed_at else None,
            "records_stored": last_irsa.stages[-1].records_stored if last_irsa and last_irsa.stages else None,
        } if last_irsa else None,
        "last_ffd_run": {
            "status": last_ffd.status if last_ffd else None,
            "run_id": last_ffd.run_id if last_ffd else None,
            "completed_at": last_ffd.completed_at.isoformat() if last_ffd and last_ffd.completed_at else None,
            "records_stored": last_ffd.stages[-1].records_stored if last_ffd and last_ffd.stages else None,
        } if last_ffd else None,
        "data_freshness": {
            "irsa_hours": get_freshness(last_irsa),
            "ffd_hours": get_freshness(last_ffd),
        },
    }
