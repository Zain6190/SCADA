# presentation/http/routers/prediction_pipeline.py
# ML Prediction Pipeline API.
# POST /water/prediction-pipeline/run - Run full prediction pipeline
# GET  /water/prediction-pipeline/forecasts - List stored forecasts

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import WaterAssetForecast

logger = logging.getLogger("aquavision.api.prediction_pipeline")

router = APIRouter(prefix="/prediction-pipeline", tags=["ML Prediction Pipeline"])


class PredictionRunResponse(BaseModel):
    predictions_stored: int
    alerts_generated: int


class ForecastResponse(BaseModel):
    id: int
    asset_id: int
    generated_at: str
    target_time: str
    predicted_level_ft: Optional[float] = None
    predicted_inflow: Optional[float] = None
    predicted_outflow: Optional[float] = None
    predicted_discharge: Optional[float] = None
    confidence: Optional[float] = None
    model_version: Optional[str] = None
    notes: Optional[str] = None


@router.post("/run", response_model=PredictionRunResponse)
def run_prediction_pipeline():
    """Run full prediction pipeline: predict -> store -> alert."""
    from infrastructure.thresholds.engine import run_prediction_pipeline as run_pipeline
    
    result = run_pipeline()
    return PredictionRunResponse(**result)


@router.get("/forecasts", response_model=List[ForecastResponse])
def list_forecasts(
    asset_id: Optional[int] = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    """List stored ML forecasts."""
    query = select(WaterAssetForecast)
    if asset_id:
        query = query.where(WaterAssetForecast.asset_id == asset_id)
    
    forecasts = session.execute(
        query.order_by(WaterAssetForecast.generated_at.desc()).limit(limit)
    ).scalars().all()
    
    return [
        ForecastResponse(
            id=f.id,
            asset_id=f.asset_id,
            generated_at=f.generated_at.isoformat() if f.generated_at else "",
            target_time=f.target_time.isoformat() if f.target_time else "",
            predicted_level_ft=float(f.predicted_level_ft) if f.predicted_level_ft else None,
            predicted_inflow=float(f.predicted_inflow) if f.predicted_inflow else None,
            predicted_outflow=float(f.predicted_outflow) if f.predicted_outflow else None,
            predicted_discharge=float(f.predicted_discharge) if f.predicted_discharge else None,
            confidence=float(f.confidence) if f.confidence else None,
            model_version=f.model_version,
            notes=f.notes,
        )
        for f in forecasts
    ]
