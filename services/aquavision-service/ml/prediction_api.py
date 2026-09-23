# ml/prediction_api.py
# Operational ML endpoints (predictions, train, anomalies, classification, performance).
# v2 predictions (4-metric, CI) live at GET /water/v2/predict/{asset_id}.

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import WaterAsset

logger = logging.getLogger(__name__)

router = APIRouter()


def _regenerate_model_metadata():
    """Try to regenerate model_metadata.json after training."""
    try:
        import subprocess
        from pathlib import Path
        script = Path(__file__).parent.parent / "scripts" / "generate_model_metadata.py"
        if script.exists():
            result = subprocess.run(
                ["python", str(script)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                logger.info("Model metadata JSON regenerated")
            else:
                logger.warning(f"Metadata generation failed: {result.stderr[:200]}")
    except Exception as e:
        logger.warning(f"Could not regenerate model metadata: {e}")


class PredictionResponse(BaseModel):
    asset_id: int
    asset_name: str
    prediction_date: str
    horizon_days: int
    predicted_level_ft: Optional[float]
    predicted_inflow: Optional[float] = None
    predicted_discharge: Optional[float] = None
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    risk_score: float
    risk_level: str
    exceeds_warning: bool
    exceeds_danger: bool
    model_version: str
    model_status: str
    feature_importance: dict
    target_field: str = "level"  # "level", "inflow", or "discharge"


class TrainRequest(BaseModel):
    asset_id: Optional[int] = None  # None = train all
    horizons: List[int] = [7, 14, 30]


class TrainResponse(BaseModel):
    models_trained: int
    results: list


class AnomalyResponse(BaseModel):
    asset_id: int
    asset_name: str
    observed_at: str
    anomaly_score: float
    is_anomaly: bool
    anomaly_features: list
    severity: str
    model_version: str
    model_status: str
    details: dict


class AnomalyTrainResponse(BaseModel):
    models_trained: int
    results: list


@router.get("/ml/predictions/{asset_id}", response_model=List[PredictionResponse])
async def get_predictions(
    asset_id: int,
    horizons: str = Query("7,14,30", description="Comma-separated horizons"),
    session: Session = Depends(get_session),
):
    """Get flood predictions for an asset.

    WARNING: This model is EXPERIMENTAL. Predictions are advisory only.
    """
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    try:
        from ml.models.flood_predictor import FloodPredictor
        from ml.features.feature_engineering import FloodFeatureBuilder
    except ImportError as e:
        logger.warning(f"ML packages not available in container: {e}")
        return []

    try:
        predictor = FloodPredictor()
        builder = FloodFeatureBuilder(session)

        X, feature_names = builder.build_prediction_features(
            asset_id=asset_id,
            as_of_date=datetime.utcnow(),
        )

        if X is None:
            return []

        # Detect target field for this asset
        from sqlalchemy import text
        has_inflow = session.execute(
            text("SELECT COUNT(*) FROM aquavision.water_observations WHERE asset_id = :aid AND inflow_cusecs IS NOT NULL"),
            {"aid": asset_id},
        ).scalar()
        total = session.execute(
            text("SELECT COUNT(*) FROM aquavision.water_observations WHERE asset_id = :aid"),
            {"aid": asset_id},
        ).scalar()
        has_discharge = session.execute(
            text("SELECT COUNT(*) FROM aquavision.water_observations WHERE asset_id = :aid AND discharge_cusecs IS NOT NULL"),
            {"aid": asset_id},
        ).scalar()

        if has_inflow > total * 0.3:
            target_field = "inflow"
        elif has_discharge > total * 0.3:
            target_field = "discharge"
        else:
            target_field = "level"

        # For risk scoring: only use level thresholds if model predicts level
        warn_level = None
        danger_lvl = None
        if target_field == "level":
            warn_level = float(asset.warning_level_ft) if asset.warning_level_ft else None
            danger_lvl = float(asset.critical_level_ft) if asset.critical_level_ft else None

        horizon_list = [int(h.strip()) for h in horizons.split(",")]
        predictions = []

        for horizon in horizon_list:
            pred = predictor.predict(
                asset_id=asset_id,
                asset_name=asset.canonical_name,
                X=X,
                feature_names=feature_names,
                horizon=horizon,
                warning_level=warn_level,
                danger_level=danger_lvl,
            )
            if pred:
                predicted_value = pred.predicted_level_ft
                predictions.append(PredictionResponse(
                    asset_id=pred.asset_id,
                    asset_name=pred.asset_name,
                    prediction_date=pred.prediction_date,
                    horizon_days=pred.horizon_days,
                    predicted_level_ft=predicted_value if target_field == "level" else None,
                    predicted_inflow=predicted_value if target_field == "inflow" else None,
                    predicted_discharge=predicted_value if target_field == "discharge" else None,
                    lower_bound=pred.lower_bound,
                    upper_bound=pred.upper_bound,
                    risk_score=pred.risk_score,
                    risk_level=pred.risk_level,
                    exceeds_warning=pred.exceeds_warning,
                    exceeds_danger=pred.exceeds_danger,
                    model_version=pred.model_version,
                    model_status=pred.model_status,
                    feature_importance=pred.feature_importance,
                    target_field=target_field,
                ))

        return predictions
    except Exception as e:
        logger.warning(f"Prediction failed for asset {asset_id}: {e}")
        return []


@router.post("/ml/train", response_model=TrainResponse)
async def trigger_training(
    payload: TrainRequest = TrainRequest(),
):
    """Trigger model training."""
    from ml.train_flood_model import train_all_assets

    results = train_all_assets(horizons=payload.horizons)
    _regenerate_model_metadata()

    return TrainResponse(
        models_trained=len(results),
        results=results,
    )


# ─── Anomaly Detection ──────────────────────────────────────────────────────

@router.get("/ml/anomalies/{asset_id}", response_model=List[AnomalyResponse])
async def get_anomalies(
    asset_id: int,
    top_n: int = Query(5, ge=1, le=20),
    session: Session = Depends(get_session),
):
    """Get anomalous observations for an asset."""
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    from ml.models.anomaly_detector import AnomalyDetector

    detector = AnomalyDetector()
    results = detector.predict(
        asset_id=asset_id,
        asset_name=asset.canonical_name,
        session=session,
        top_n=top_n,
    )

    return [
        AnomalyResponse(
            asset_id=r.asset_id,
            asset_name=r.asset_name,
            observed_at=r.observed_at,
            anomaly_score=r.anomaly_score,
            is_anomaly=r.is_anomaly,
            anomaly_features=r.anomaly_features,
            severity=r.severity,
            model_version=r.model_version,
            model_status=r.model_status,
            details=r.details,
        )
        for r in results
    ]


@router.post("/ml/anomalies/train", response_model=AnomalyTrainResponse)
async def train_anomaly_detectors(session: Session = Depends(get_session)):
    """Train Isolation Forest anomaly detectors for all assets."""
    from ml.models.anomaly_detector import AnomalyDetector

    detector = AnomalyDetector()
    results = detector.train_all(session)

    return AnomalyTrainResponse(
        models_trained=len(results),
        results=results,
    )


# ─── Flood Classification ────────────────────────────────────────────────────

class FloodClassificationResponse(BaseModel):
    asset_id: int
    asset_name: str
    flood_probability: float
    flood_predicted: bool
    flood_severity: str
    confidence: str
    recommendation: str
    model_available: bool


@router.get("/ml/flood-classification/{asset_id}", response_model=FloodClassificationResponse)
async def get_flood_classification(
    asset_id: int,
    session: Session = Depends(get_session),
):
    """Get flood probability classification for an asset."""
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    from ml.models.flood_classifier import FloodClassifier
    from pathlib import Path

    model_path = Path(__file__).parent.parent / "data" / "models" / f"flood_classifier_asset_{asset_id}.pkl"

    if not model_path.exists():
        return FloodClassificationResponse(
            asset_id=asset_id,
            asset_name=asset.canonical_name,
            flood_probability=0.0,
            flood_predicted=False,
            flood_severity="NONE",
            confidence="LOW",
            recommendation="No model trained for this asset",
            model_available=False,
        )

    try:
        clf = FloodClassifier.load(asset_id, model_path)

        from sqlalchemy import text
        from infrastructure.db.engine import engine as sa_engine

        with sa_engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT observed_at, inflow_cusecs, outflow_cusecs,
                           water_level_ft, discharge_cusecs
                    FROM aquavision.water_observations
                    WHERE asset_id = :asset_id
                    AND inflow_cusecs IS NOT NULL
                    ORDER BY observed_at DESC
                    LIMIT 60
                """),
                {"asset_id": asset_id},
            ).mappings().all()

        if not rows:
            raise HTTPException(400, "No observation data available")

        import pandas as pd
        from decimal import Decimal

        df = pd.DataFrame(list(reversed(rows)))
        for col in df.columns:
            if df[col].dtype == object:
                try:
                    df[col] = df[col].apply(lambda x: float(x) if isinstance(x, (Decimal, int)) else x)
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                except Exception:
                    pass

        result = clf.predict(df)

        if "error" in result:
            raise HTTPException(400, result["error"])

        return FloodClassificationResponse(
            asset_id=asset_id,
            asset_name=asset.canonical_name,
            flood_probability=result["flood_probability"],
            flood_predicted=result["flood_predicted"],
            flood_severity=result["flood_severity"],
            confidence=result["confidence"],
            recommendation=result["recommendation"],
            model_available=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Classification failed: {str(e)}")


@router.post("/ml/flood-classification/train")
async def train_flood_classifiers():
    """Train flood classifiers for all assets with sufficient data."""
    from ml.models.flood_classifier import train_all_classifiers

    results = train_all_classifiers(horizon=7)
    trained = len([r for r in results if "error" not in r])
    _regenerate_model_metadata()

    return {
        "models_trained": trained,
        "results": results,
    }


# ─── Model Performance Endpoint ────────────────────────────────────────────


class ModelPerformance(BaseModel):
    asset_id: int
    asset_name: str
    model_type: str
    model_status: str
    trained_at: Optional[str] = None
    saved_at: Optional[str] = None
    samples: Optional[int] = None
    train_samples: Optional[int] = None
    test_samples: Optional[int] = None
    r2: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    accuracy: Optional[float] = None
    auc: Optional[float] = None
    f1: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    feature_importance: dict = {}
    horizon_days: Optional[int] = None
    model_version: Optional[str] = None
    model_file: str = ""


@router.get("/ml/model-performance", response_model=List[ModelPerformance])
async def get_model_performance():
    """Read model performance metadata from pre-generated JSON."""
    import json
    from pathlib import Path

    metadata_path = Path(__file__).parent.parent / "data" / "model_metadata.json"
    if not metadata_path.exists():
        return []

    with open(metadata_path) as f:
        raw = json.load(f)

    return [ModelPerformance(**item) for item in raw]
