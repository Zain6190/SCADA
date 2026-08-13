"""
app/api/v1/endpoints/admin.py
Pipeline observability & control endpoints (admin-only).

Routes:
    GET  /admin/pipeline-health
    GET  /admin/pipeline-runs
    GET  /admin/pipeline-runs/latest
    GET  /admin/pipeline-runs/{run_id}
    GET  /admin/pipeline-runs/{run_id}/logs/{stage_name}
    POST /admin/pipeline-runs/trigger
    POST /admin/pipeline-runs/{run_id}/cancel
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import require_admin
from app.models import db as orm

router = APIRouter()

ADMIN = require_admin

# Resolve ML pipeline root relative to this file
# backend:  packages/backend/app/api/v1/endpoints/admin.py
# pipeline: packages/ml-pipeline/
_ML_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent / "ml-pipeline"
_PYTHON = sys.executable


# ── Pydantic response schemas ──────────────────────────────────────────

class StageOut(BaseModel):
    id: int
    run_id: str
    stage_name: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    records_read: Optional[int] = None
    records_written: Optional[int] = None
    records_skipped: Optional[int] = None
    warning_count: Optional[int] = None
    error_count: Optional[int] = None
    log_path: Optional[str] = None

    class Config:
        from_attributes = True


class PipelineRunOut(BaseModel):
    id: int
    pipeline_name: str
    status: Optional[str] = None
    run_id: Optional[str] = None
    trigger_type: Optional[str] = None
    data_period: Optional[str] = None
    source_version: Optional[str] = None
    code_version: Optional[str] = None
    model_version: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    records_read: Optional[int] = None
    records_written: Optional[int] = None
    records_skipped: Optional[int] = None
    warning_count: Optional[int] = None
    error_count: Optional[int] = None
    log_path: Optional[str] = None
    error_summary: Optional[str] = None
    stages: List[StageOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class PipelineRunBrief(BaseModel):
    id: int
    run_id: Optional[str] = None
    status: Optional[str] = None
    trigger_type: Optional[str] = None
    data_period: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    records_written: Optional[int] = None
    warning_count: Optional[int] = None
    error_count: Optional[int] = None

    class Config:
        from_attributes = True


class PipelineHealth(BaseModel):
    last_run_id: Optional[str] = None
    last_status: Optional[str] = None
    last_started_at: Optional[datetime] = None
    last_ended_at: Optional[datetime] = None
    data_period: Optional[str] = None
    records_written: Optional[int] = None
    warning_count: Optional[int] = None
    error_count: Optional[int] = None
    csv_age_days: Optional[float] = None
    csv_mtime: Optional[datetime] = None
    running_stages: List[str] = Field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────

def _stages_for(db: Session, run_id: str) -> List[orm.PipelineRunStage]:
    return list(db.execute(
        text("SELECT * FROM system.pipeline_run_stages WHERE run_id = :run_id ORDER BY id")
        .bindparams(run_id=run_id)
    ).mappings().all())


def _run_by_id(db: Session, run_id: str) -> Optional[dict]:
    return db.execute(
        text("SELECT * FROM system.pipeline_runs WHERE run_id = :run_id")
        .bindparams(run_id=run_id)
    ).mappings().first()


def _run_by_pk(db: Session, pk: int) -> Optional[dict]:
    return db.execute(
        text("SELECT * FROM system.pipeline_runs WHERE id = :id")
        .bindparams(id=pk)
    ).mappings().first()


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("/pipeline-health", response_model=PipelineHealth)
async def pipeline_health(
    auth: dict = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    """Aggregated health summary for the admin dashboard."""
    last = db.execute(
        text("SELECT * FROM system.pipeline_runs ORDER BY id DESC LIMIT 1")
    ).mappings().first()

    csv_path = _ML_ROOT / "Data" / "raw" / "region_features.csv"
    csv_age = csv_mtime = None
    try:
        mtime_epoch = csv_path.stat().st_mtime
        csv_mtime = datetime.fromtimestamp(mtime_epoch, tz=timezone.utc)
        csv_age = round((datetime.now(timezone.utc).timestamp() - mtime_epoch) / 86400.0, 2)
    except FileNotFoundError:
        pass

    # Any currently-running stages
    running = [
        r[0] for r in db.execute(
            text(
                "SELECT DISTINCT stage_name FROM system.pipeline_run_stages "
                "WHERE status NOT IN ('SUCCESS','PARTIAL_SUCCESS','FAILED','SKIPPED','CANCELLED')"
            )
        ).fetchall()
    ]

    return PipelineHealth(
        last_run_id=last.get("run_id") if last else None,
        last_status=last.get("status") if last else None,
        last_started_at=last.get("started_at") if last else None,
        last_ended_at=last.get("ended_at") if last else None,
        data_period=last.get("data_period") if last else None,
        records_written=last.get("records_written") if last else None,
        warning_count=last.get("warning_count") if last else None,
        error_count=last.get("error_count") if last else None,
        csv_age_days=csv_age,
        csv_mtime=csv_mtime,
        running_stages=running,
    )


@router.get("/pipeline-runs", response_model=List[PipelineRunBrief])
async def list_runs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth: dict = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    """List pipeline runs (newest first) with optional status filter."""
    sql = "SELECT * FROM system.pipeline_runs"
    params: dict = {}
    if status:
        sql += " WHERE status = :status"
        params["status"] = status
    sql += " ORDER BY id DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    rows = db.execute(text(sql).bindparams(**params)).mappings().all()
    return [PipelineRunBrief(**r) for r in rows]


@router.get("/pipeline-runs/latest", response_model=PipelineRunOut)
async def latest_run(
    auth: dict = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    """Latest pipeline run with its stage breakdown."""
    last = db.execute(
        text("SELECT * FROM system.pipeline_runs ORDER BY id DESC LIMIT 1")
    ).mappings().first()
    if not last:
        raise HTTPException(404, "No pipeline runs found")
    stages = _stages_for(db, last["run_id"])
    return PipelineRunOut(**last, stages=[StageOut(**s) for s in stages])


@router.get("/pipeline-runs/{run_id}", response_model=PipelineRunOut)
async def get_run(
    run_id: str,
    auth: dict = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    """Single pipeline run with its stage breakdown."""
    run = _run_by_id(db, run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    stages = _stages_for(db, run_id)
    return PipelineRunOut(**run, stages=[StageOut(**s) for s in stages])


@router.get("/pipeline-runs/{run_id}/logs/{stage_name}")
async def get_stage_log(
    run_id: str,
    stage_name: str,
    auth: dict = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    """Raw log content for a specific stage."""
    row = db.execute(
        text(
            "SELECT log_path FROM system.pipeline_run_stages "
            "WHERE run_id = :run_id AND stage_name = :stage_name"
        ).bindparams(run_id=run_id, stage_name=stage_name)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"No log found for run {run_id} / stage {stage_name}")
    log_path = Path(row[0])
    if not log_path.exists():
        raise HTTPException(404, f"Log file missing on disk: {log_path}")
    return PlainTextResponse(log_path.read_text(encoding="utf-8", errors="replace"))


@router.post("/pipeline-runs/trigger", status_code=202)
async def trigger_pipeline(
    with_fetch: bool = Query(False, description="Include GEE data fetch"),
    auth: dict = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    """Start a new pipeline run (non-blocking). Returns 409 if one is already active."""
    running = db.execute(
        text(
            "SELECT run_id FROM system.pipeline_runs "
            "WHERE status IN ('QUEUED','RUNNING') LIMIT 1"
        )
    ).fetchone()
    if running:
        raise HTTPException(409, f"Pipeline already running: {running[0]}")

    cmd = [_PYTHON, "-m", "scripts.run_pipeline"]
    if with_fetch:
        cmd.append("--with-fetch")
    subprocess.Popen(
        cmd,
        cwd=str(_ML_ROOT),
        creationflags=0x00000008 if sys.platform == "win32" else 0,
    )
    return {"status": "triggered", "with_fetch": with_fetch}


@router.post("/pipeline-runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    auth: dict = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    """Cancel a QUEUED pipeline run before it starts."""
    run = _run_by_id(db, run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    if run["status"] != "QUEUED":
        raise HTTPException(
            409, f"Cannot cancel run in '{run['status']}' status (only QUEUED runs can be cancelled)"
        )
    db.execute(
        text(
            "UPDATE system.pipeline_runs SET status = 'CANCELLED', ended_at = now() "
            "WHERE run_id = :run_id AND status = 'QUEUED'"
        ).bindparams(run_id=run_id)
    )
    db.commit()
    return {"status": "cancelled", "run_id": run_id}
