# presentation/http/routers/health.py
# Health endpoints for AquaVision service.
# Liveness: Process is running
# Readiness: Database and migrations are ready
# Pipeline Health: Last pipeline runs and scheduler status (admin only)
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session

router = APIRouter(tags=["Health"])


@router.get("/health/live")
def liveness():
    """Liveness probe - checks only that the process is running."""
    return {"status": "alive"}


@router.get("/health/ready")
def readiness(session: Session = Depends(get_session)):
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
            from alembic.config import Config
            from alembic.runtime.migration import MigrationContext
            from alembic.script import ScriptDirectory

            context = MigrationContext.configure(
                session.connection(),
                opts={
                    "version_table": "alembic_version",
                    "version_table_schema": "aquavision",
                },
            )
            current = set(context.get_current_heads())
            script = ScriptDirectory.from_config(Config("alembic.ini"))
            migrations_ok = current == set(script.get_heads())
        except Exception:
            migrations_ok = False

    status = "ready" if (db_ok and migrations_ok) else "not_ready"

    return {
        "status": status,
        "database": "ok" if db_ok else "error",
        "migrations": "ok" if migrations_ok else "outdated",
    }


@router.get("/api/v1/admin/pipeline-health")
def pipeline_health(session: Session = Depends(get_session)):
    """Pipeline health endpoint - shows last runs and scheduler status."""
    empty = {
        "api_status": "ready",
        "scheduler_status": "unknown",
        "last_irsa_run": None,
        "last_ffd_run": None,
        "data_freshness": {"irsa_hours": None, "ffd_hours": None},
        "recent_runs": [],
        "summary": {},
        "heartbeat": None,
    }
    try:
        from infrastructure.db.models import PipelineRun, SchedulerHeartbeat
    except Exception:
        return empty

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

    def last_run_of(pipeline_type: str):
        try:
            return session.execute(
                select(PipelineRun)
                .where(PipelineRun.pipeline_type == pipeline_type)
                .order_by(PipelineRun.started_at.desc())
                .limit(1)
            ).scalars().first()
        except Exception:
            return None

    last_irsa = last_run_of("IRSA")
    last_ffd = last_run_of("FFD")

    scheduler_status = "unknown"
    heartbeat_info = None
    try:
        heartbeat = session.execute(
            select(SchedulerHeartbeat)
            .where(SchedulerHeartbeat.service_name == "scheduler")
            .order_by(SchedulerHeartbeat.last_heartbeat_at.desc())
            .limit(1)
        ).scalars().first()

        if heartbeat:
            age_minutes = (datetime.now(timezone.utc) - heartbeat.last_heartbeat_at).total_seconds() / 60
            if age_minutes < 5:
                scheduler_status = "running"
            elif age_minutes < 15:
                scheduler_status = "delayed"
            else:
                scheduler_status = "unhealthy"
            heartbeat_info = {
                "instance_id": heartbeat.instance_id,
                "last_heartbeat_at": heartbeat.last_heartbeat_at.isoformat(),
                "age_minutes": round(age_minutes, 1),
                "status": heartbeat.status,
            }
    except Exception:
        pass

    recent_runs = []
    try:
        rows = session.execute(
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(20)
        ).scalars().all()
        recent_runs = [
            {
                "id": run.id,
                "run_id": run.run_id,
                "pipeline_type": run.pipeline_type,
                "status": run.status,
                "trigger_type": run.trigger_type,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "duration_seconds": run.duration_seconds,
                "error_message": run.error_message,
                "retry_count": run.retry_count,
            }
            for run in rows
        ]
    except Exception:
        pass

    summary = {}
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        count_rows = session.execute(
            select(PipelineRun.status, func.count())
            .where(PipelineRun.started_at >= cutoff)
            .group_by(PipelineRun.status)
        ).all()
        summary = {status: count for status, count in count_rows}
        summary["window_days"] = 7
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
        "recent_runs": recent_runs,
        "summary": summary,
        "heartbeat": heartbeat_info,
    }
