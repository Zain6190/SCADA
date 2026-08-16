# ml/prediction_api.py
# API endpoints for ML predictions.
# GET  /water/ml/predictions/{asset_id}  - Get flood predictions
# POST /water/ml/train                    - Trigger model training

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import WaterAsset

router = APIRouter()


class PredictionResponse(BaseModel):
    asset_id: int
    asset_name: str
    prediction_date: str
    horizon_days: int
    predicted_level_ft: Optional[float]
    confidence: float
    lower_bound_80: Optional[float]
    upper_bound_80: Optional[float]
    risk_score: float
    risk_level: str
    exceeds_warning: bool
    exceeds_danger: bool
    model_version: str
    feature_importance: dict


class TrainRequest(BaseModel):
    asset_id: Optional[int] = None  # None = train all
    horizons: List[int] = [7, 14, 30]


class TrainResponse(BaseModel):
    models_trained: int
    results: list


@router.get("/ml/predictions/{asset_id}", response_model=List[PredictionResponse])
async def get_predictions(
    asset_id: int,
    horizons: str = Query("7,14,30", description="Comma-separated horizons"),
    session: Session = Depends(get_session),
):
    """Get flood predictions for an asset."""
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    from ml.models.flood_predictor import FloodPredictor
    from ml.features.feature_engineering import FloodFeatureBuilder
    
    predictor = FloodPredictor()
    builder = FloodFeatureBuilder(session)
    
    X, feature_names = builder.build_prediction_features(
        asset_id=asset_id,
        as_of_date=datetime.utcnow(),
    )
    
    if X is None:
        return []
    
    horizon_list = [int(h.strip()) for h in horizons.split(",")]
    predictions = []
    
    for horizon in horizon_list:
        pred = predictor.predict(
            asset_id=asset_id,
            asset_name=asset.canonical_name,
            X=X,
            feature_names=feature_names,
            horizon=horizon,
            warning_level=float(asset.warning_level_ft) if asset.warning_level_ft else None,
            danger_level=float(asset.critical_level_ft) if asset.critical_level_ft else None,
        )
        if pred:
            predictions.append(PredictionResponse(
                asset_id=pred.asset_id,
                asset_name=pred.asset_name,
                prediction_date=pred.prediction_date,
                horizon_days=pred.horizon_days,
                predicted_level_ft=pred.predicted_level_ft,
                confidence=pred.confidence,
                lower_bound_80=pred.lower_bound_80,
                upper_bound_80=pred.upper_bound_80,
                risk_score=pred.risk_score,
                risk_level=pred.risk_level,
                exceeds_warning=pred.exceeds_warning,
                exceeds_danger=pred.exceeds_danger,
                model_version=pred.model_version,
                feature_importance=pred.feature_importance,
            ))
    
    return predictions


@router.post("/ml/train", response_model=TrainResponse)
async def trigger_training(
    payload: TrainRequest = TrainRequest(),
):
    """Trigger model training."""
    from ml.train_flood_model import train_all_assets
    
    results = train_all_assets(horizons=payload.horizons)
    
    return TrainResponse(
        models_trained=len(results),
        results=results,
    )
