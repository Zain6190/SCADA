"""
AquaVision ML API Router - Model management, training, and validation endpoints.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("aquavision.ml_api")

router = APIRouter(prefix="/ml", tags=["ml"])

_BASE_DIR = Path(os.environ.get("AQUAVISION_BASE_DIR", "/app"))
MODEL_METADATA_PATH = _BASE_DIR / "data" / "models" / "model_metadata.json"


# ── Response models ──────────────────────────────────────────────────────────

class ModelMetadataResponse(BaseModel):
    generated_at: str
    model_version: str
    features_enriched: bool
    weather_features: bool
    log_transform: bool
    smote_classifier: bool
    assets: dict


class TrainAllResponse(BaseModel):
    status: str
    message: str
    started_at: str


class ValidateAllResponse(BaseModel):
    status: str
    message: str
    started_at: str


class ValidationReport(BaseModel):
    asset_id: int
    model_type: str
    model_version: str
    horizon: int
    metrics: dict
    data_info: dict
    recommendation: str
    reasons: list
    fold_details: list
    validated_at: str


# ── Background tasks ─────────────────────────────────────────────────────────

def _run_retrain():
    """Run batch retrain in a subprocess."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0,'/app'); from scripts.retrain_all_models import main; main()"],
            capture_output=True, text=True, timeout=3600, cwd="/app"
        )
        logger.info(f"Retrain completed: {result.stdout[-500:] if result.stdout else 'no output'}")
        if result.returncode != 0:
            logger.error(f"Retrain failed: {result.stderr[-500:] if result.stderr else 'no error output'}")
    except Exception as e:
        logger.error(f"Retrain exception: {e}")


def _run_validation():
    """Run batch validation in a subprocess."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0,'/app'); from scripts.validate_all_models import main; main()"],
            capture_output=True, text=True, timeout=3600, cwd="/app"
        )
        logger.info(f"Validation completed: {result.stdout[-500:] if result.stdout else 'no output'}")
        if result.returncode != 0:
            logger.error(f"Validation failed: {result.stderr[-500:] if result.stderr else 'no error output'}")
    except Exception as e:
        logger.error(f"Validation exception: {e}")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/model-metadata", response_model=ModelMetadataResponse)
async def get_model_metadata():
    """Get consolidated model metadata for all trained models."""
    if MODEL_METADATA_PATH.exists():
        with open(MODEL_METADATA_PATH) as f:
            data = json.load(f)
        return ModelMetadataResponse(**data)

    # Fallback: generate from model files
    model_dir = _BASE_DIR / "models" / "flood_xgb"
    assets = {}
    for f in model_dir.glob("[0-9]*_[0-9]*.joblib"):
        parts = f.stem.split("_")
        if len(parts) < 2:
            continue
        aid = int(parts[0])
        horizon = int(parts[1])
        is_highflow = len(parts) > 2 and parts[2] == "hf"

        if aid not in assets:
            assets[aid] = {"asset_id": aid, "models": {}}

        key = f"{'high_flow' if is_highflow else 'flood_predictor'}_{horizon}"
        assets[aid]["models"][key] = {
            "status": "TRAINED",
            "horizon": horizon,
            "model_type": "high_flow" if is_highflow else "flood_predictor",
            "file": f.name,
        }

    return ModelMetadataResponse(
        generated_at=datetime.utcnow().isoformat(),
        model_version="xgb-flood-v1.2",
        features_enriched=True,
        weather_features=True,
        log_transform=True,
        smote_classifier=True,
        assets=assets,
    )


@router.post("/train-all", response_model=TrainAllResponse)
async def train_all(background_tasks: BackgroundTasks):
    """Trigger batch retrain for all assets (runs in background)."""
    background_tasks.add_task(_run_retrain)
    return TrainAllResponse(
        status="started",
        message="Batch retrain started in background. Check /ml/model-metadata for results.",
        started_at=datetime.utcnow().isoformat(),
    )


@router.post("/validate-all", response_model=ValidateAllResponse)
async def validate_all(background_tasks: BackgroundTasks):
    """Trigger batch validation for all models (runs in background)."""
    background_tasks.add_task(_run_validation)
    return ValidateAllResponse(
        status="started",
        message="Batch validation started in background.",
        started_at=datetime.utcnow().isoformat(),
    )


@router.get("/validation-reports")
async def get_validation_reports(
    asset_id: Optional[int] = Query(None, description="Filter by asset ID"),
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get recent validation reports."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    query = """
        SELECT asset_id, model_type, model_version, horizon, metrics,
               data_info, recommendation, reasons, fold_details,
               validated_at::text as validated_at
        FROM aquavision.validation_reports
        WHERE 1=1
    """
    params = {}

    if asset_id is not None:
        query += " AND asset_id = :asset_id"
        params["asset_id"] = asset_id
    if model_type:
        query += " AND model_type = :model_type"
        params["model_type"] = model_type

    query += " ORDER BY validated_at DESC LIMIT :limit"
    params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    results = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("metrics"), str):
            r["metrics"] = json.loads(r["metrics"])
        if isinstance(r.get("data_info"), str):
            r["data_info"] = json.loads(r["data_info"])
        if isinstance(r.get("reasons"), str):
            r["reasons"] = json.loads(r["reasons"])
        if isinstance(r.get("fold_details"), str):
            r["fold_details"] = json.loads(r["fold_details"])
        results.append(r)

    return {"count": len(results), "reports": results}


@router.get("/model-status")
async def get_model_status():
    """Get quick summary of all model files on disk."""
    model_dir = _BASE_DIR / "models" / "flood_xgb"
    classifier_dir = _BASE_DIR / "data" / "models"

    flood_models = {}
    hf_models = {}
    classifiers = {}

    for f in sorted(model_dir.glob("[0-9]*_[0-9]*.joblib")):
        parts = f.stem.split("_")
        if len(parts) < 2:
            continue
        aid = int(parts[0])
        horizon = int(parts[1])
        is_hf = len(parts) > 2 and parts[2] == "hf"

        entry = {"file": f.name, "size_kb": round(f.stat().st_size / 1024, 1)}

        if is_hf:
            hf_models.setdefault(aid, []).append({f"horizon_{horizon}": entry})
        else:
            flood_models.setdefault(aid, []).append({f"horizon_{horizon}": entry})

    for f in sorted(classifier_dir.glob("flood_classifier_asset_[0-9]*.pkl")):
        parts = f.stem.split("_")
        aid = int(parts[-1])
        classifiers[aid] = {"file": f.name, "size_kb": round(f.stat().st_size / 1024, 1)}

    return {
        "flood_predictors": flood_models,
        "high_flow_predictors": hf_models,
        "classifiers": classifiers,
        "total_files": len(list(model_dir.glob("*.joblib"))) + len(list(classifier_dir.glob("*.pkl"))),
    }


# ── Model Registry ──────────────────────────────────────────────────────────

class PromoteRequest(BaseModel):
    asset_id: int
    model_type: str = "flood_predictor"
    horizon: int = 7
    status: str  # SHADOW, EXPERIMENTAL, REJECTED
    performed_by: str = "operator"


@router.get("/registry")
async def get_model_registry(
    asset_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
):
    """Get model registry with validation scores and status."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    query = """
        SELECT vr.asset_id, vr.model_type, vr.model_version, vr.horizon,
               vr.metrics, vr.data_info, vr.recommendation, vr.reasons,
               vr.validated_at::text as validated_at,
               a.canonical_name as asset_name, a.asset_type
        FROM aquavision.validation_reports vr
        LEFT JOIN aquavision.water_assets a ON a.id = vr.asset_id
        WHERE 1=1
    """
    params = {}

    if asset_id is not None:
        query += " AND vr.asset_id = :asset_id"
        params["asset_id"] = asset_id
    if status:
        query += " AND vr.recommendation = :status"
        params["status"] = status

    query += " ORDER BY vr.asset_id, vr.horizon"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    results = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("metrics"), str):
            r["metrics"] = json.loads(r["metrics"])
        if isinstance(r.get("data_info"), str):
            r["data_info"] = json.loads(r["data_info"])
        if isinstance(r.get("reasons"), str):
            r["reasons"] = json.loads(r["reasons"])
        results.append(r)

    return {"count": len(results), "models": results}


@router.post("/registry/promote")
async def promote_model(req: PromoteRequest):
    """Promote/demote a model's status in the validation registry."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    valid_statuses = {"SHADOW", "EXPERIMENTAL", "REJECTED"}
    if req.status not in valid_statuses:
        raise HTTPException(400, f"Invalid status: {req.status}. Must be one of {valid_statuses}")

    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE aquavision.validation_reports
            SET recommendation = :status,
                reasons = reasons || jsonb_build_array(
                    jsonb_build_object('action', 'manual_override', 'by', :by, 'at', now()::text)
                )
            WHERE asset_id = :asset_id AND model_type = :model_type AND horizon = :horizon
        """), {
            "status": req.status,
            "by": req.performed_by,
            "asset_id": req.asset_id,
            "model_type": req.model_type,
            "horizon": req.horizon,
        })

        if result.rowcount == 0:
            raise HTTPException(404, f"No validation report found for asset={req.asset_id} type={req.model_type} horizon={req.horizon}d")

    return {"status": "ok", "message": f"Model promoted to {req.status}"}


@router.get("/registry/summary")
async def get_registry_summary():
    """Get aggregated registry stats."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT recommendation, COUNT(*) as cnt,
                   AVG((metrics->>'r2_log')::float) as avg_r2_log,
                   AVG((metrics->>'mae_log')::float) as avg_mae_log,
                   AVG((metrics->>'score')::float) as avg_score
            FROM aquavision.validation_reports
            GROUP BY recommendation
        """)).mappings().all()

    summary = {}
    for row in rows:
        summary[row["recommendation"]] = {
            "count": row["cnt"],
            "avg_r2_log": round(row["avg_r2_log"], 4) if row["avg_r2_log"] else None,
            "avg_mae_log": round(row["avg_mae_log"], 4) if row["avg_mae_log"] else None,
            "avg_score": round(row["avg_score"], 1) if row["avg_score"] else None,
        }

    # Total models on disk
    model_dir = _BASE_DIR / "models" / "flood_xgb"
    total_on_disk = len(list(model_dir.glob("*.joblib"))) if model_dir.exists() else 0

    return {
        "summary": summary,
        "total_on_disk": total_on_disk,
        "total_validated": sum(v["count"] for v in summary.values()),
    }


# ── Drift Detection ─────────────────────────────────────────────────────────

@router.get("/drift-alerts")
async def get_drift_alerts(
    asset_id: Optional[int] = Query(None),
    drift_level: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get recent drift detection alerts."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    query = """
        SELECT id, asset_id, horizon, drift_level, mae, rmse, mape,
               bias_ratio, mean_error, n_samples, reasons,
               detected_at::text as detected_at,
               acknowledged, acknowledged_by, acknowledged_at::text as acknowledged_at
        FROM aquavision.drift_alerts
        WHERE 1=1
    """
    params = {}

    if asset_id is not None:
        query += " AND asset_id = :asset_id"
        params["asset_id"] = asset_id
    if drift_level:
        query += " AND drift_level = :drift_level"
        params["drift_level"] = drift_level

    query += " ORDER BY detected_at DESC LIMIT :limit"
    params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    results = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("reasons"), str):
            r["reasons"] = json.loads(r["reasons"])
        results.append(r)

    return {"count": len(results), "alerts": results}


@router.post("/drift-detect")
async def trigger_drift_detection(background_tasks: BackgroundTasks):
    """Trigger drift detection job."""
    def _run():
        try:
            subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0,'/app'); from scripts.detect_drift import main; main()"],
                capture_output=True, text=True, timeout=300, cwd="/app"
            )
        except Exception as e:
            logger.error(f"Drift detection failed: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Drift detection started in background"}


@router.post("/drift-alerts/{alert_id}/ack")
async def acknowledge_drift_alert(alert_id: int, performed_by: str = "operator"):
    """Acknowledge a drift alert."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE aquavision.drift_alerts
            SET acknowledged = true, acknowledged_by = :by, acknowledged_at = now()
            WHERE id = :id
        """), {"by": performed_by, "id": alert_id})

        if result.rowcount == 0:
            raise HTTPException(404, "Drift alert not found")

    return {"status": "ok", "message": f"Alert {alert_id} acknowledged"}


# ── Persisted Predictions ───────────────────────────────────────────────────

@router.get("/predictions")
async def get_predictions(
    asset_id: Optional[int] = Query(None),
    horizon: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Get persisted flood predictions from DB."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    query = """
        SELECT wp.id, wp.asset_id, wp.horizon, wp.predicted_value,
               wp.predicted_lower, wp.predicted_upper,
               wp.risk_score, wp.risk_category,
               wp.exceeds_warning, wp.exceeds_danger,
               wp.model_version, wp.confidence,
               wp.valid_from::text as valid_from,
               wp.valid_to::text as valid_to,
               wp.generated_at::text as generated_at,
               wa.canonical_name as asset_name
        FROM aquavision.water_predictions wp
        LEFT JOIN aquavision.water_assets wa ON wa.id = wp.asset_id
        WHERE 1=1
    """
    params = {}

    if asset_id is not None:
        query += " AND wp.asset_id = :asset_id"
        params["asset_id"] = asset_id
    if horizon is not None:
        query += " AND wp.horizon = :horizon"
        params["horizon"] = horizon

    query += " ORDER BY wp.generated_at DESC, wp.asset_id, wp.horizon LIMIT :limit"
    params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    return {"count": len(rows), "predictions": [dict(r) for r in rows]}


@router.get("/prediction-summary")
async def get_predictions_summary():
    """Get latest prediction per asset/horizon."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT ON (wp.asset_id, wp.horizon)
                wp.asset_id, wp.horizon, wp.predicted_value,
                wp.risk_score, wp.risk_category,
                wp.confidence, wp.model_version,
                wp.valid_from::text as valid_from,
                wp.generated_at::text as generated_at,
                wa.canonical_name as asset_name
            FROM aquavision.water_predictions wp
            LEFT JOIN aquavision.water_assets wa ON wa.id = wp.asset_id
            ORDER BY wp.asset_id, wp.horizon, wp.generated_at DESC
        """)).mappings().all()

    return {"count": len(rows), "predictions": [dict(r) for r in rows]}


@router.post("/run-predictions")
async def trigger_predictions(background_tasks: BackgroundTasks):
    """Trigger prediction persistence job."""
    def _run():
        try:
            subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0,'/app'); from scripts.persist_predictions import main; main()"],
                capture_output=True, text=True, timeout=300, cwd="/app"
            )
        except Exception as e:
            logger.error(f"Prediction persistence failed: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Prediction persistence started in background"}


@router.get("/prediction-logs")
async def get_prediction_logs(limit: int = Query(20, ge=1, le=100)):
    """Get prediction run history."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, run_type, assets_predicted, assets_failed,
                   predictions_written, duration_seconds, status,
                   started_at::text as started_at, completed_at::text as completed_at
            FROM aquavision.prediction_logs
            ORDER BY started_at DESC
            LIMIT :limit
        """), {"limit": limit}).mappings().all()

    return {"count": len(rows), "logs": [dict(r) for r in rows]}


# ── PSI Feature Drift ──────────────────────────────────────────────────────

@router.get("/feature-drift")
async def get_feature_drift(
    asset_id: Optional[int] = Query(None),
    drift_status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Get PSI feature drift results."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    query = """
        SELECT fd.id, fd.asset_id, fd.feature_name, fd.psi, fd.ks_statistic,
               fd.mean_current, fd.mean_baseline, fd.std_current, fd.std_baseline,
               fd.drift_status, fd.evaluation_window,
               fd.computed_at::text as computed_at,
               wa.canonical_name as asset_name
        FROM aquavision.feature_drift fd
        LEFT JOIN aquavision.water_assets wa ON wa.id = fd.asset_id
        WHERE 1=1
    """
    params = {}

    if asset_id is not None:
        query += " AND fd.asset_id = :asset_id"
        params["asset_id"] = asset_id
    if drift_status:
        query += " AND fd.drift_status = :drift_status"
        params["drift_status"] = drift_status

    query += " ORDER BY fd.computed_at DESC, fd.psi DESC LIMIT :limit"
    params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    return {"count": len(rows), "features": [dict(r) for r in rows]}


@router.get("/feature-drift/summary")
async def get_feature_drift_summary():
    """Get PSI drift summary: how many features are STABLE/MODERATE/SIGNIFICANT per asset."""
    from infrastructure.db.engine import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT fd.asset_id, wa.canonical_name,
                   COUNT(*) as total_features,
                   COUNT(*) FILTER (WHERE fd.drift_status = 'STABLE') as stable,
                   COUNT(*) FILTER (WHERE fd.drift_status = 'MODERATE') as moderate,
                   COUNT(*) FILTER (WHERE fd.drift_status = 'SIGNIFICANT') as significant,
                   AVG(fd.psi) as avg_psi,
                   MAX(fd.computed_at)::text as last_computed
            FROM aquavision.feature_drift fd
            LEFT JOIN aquavision.water_assets wa ON wa.id = fd.asset_id
            GROUP BY fd.asset_id, wa.canonical_name
            ORDER BY significant DESC, moderate DESC
        """)).mappings().all()

    return {"assets": [dict(r) for r in rows]}


@router.post("/feature-drift/detect")
async def trigger_psi_drift_detection(background_tasks: BackgroundTasks):
    """Trigger PSI drift detection for all assets."""
    def _run():
        try:
            subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0,'/app'); from scripts.detect_drift_psi import main; main()"],
                capture_output=True, text=True, timeout=600, cwd="/app"
            )
        except Exception as e:
            logger.error(f"PSI drift detection failed: {e}")

    background_tasks.add_task(_run)
    return {"status": "started", "message": "PSI drift detection started in background"}
