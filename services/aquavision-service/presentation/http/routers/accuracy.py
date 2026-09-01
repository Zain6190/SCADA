"""
Prediction Accuracy API Router.
Tracks actual vs predicted values to monitor model performance over time.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("accuracy_api")

router = APIRouter(prefix="/accuracy", tags=["Prediction Accuracy"])


# ── Response models ──────────────────────────────────────────────────────

class AccuracySummary(BaseModel):
    asset_id: int
    horizon: int
    model_version: Optional[str] = None
    mae_30d: Optional[float] = None
    rmse_30d: Optional[float] = None
    mape_30d: Optional[float] = None
    bias_30d: Optional[float] = None
    coverage_30d: Optional[float] = None
    direction_30d: Optional[float] = None
    sample_count_30d: Optional[int] = None
    mae_90d: Optional[float] = None
    rmse_90d: Optional[float] = None
    mape_90d: Optional[float] = None
    bias_90d: Optional[float] = None
    coverage_90d: Optional[float] = None
    direction_90d: Optional[float] = None
    sample_count_90d: Optional[int] = None
    last_evaluated_at: Optional[str] = None


class AccuracyPoint(BaseModel):
    date: Optional[str] = None
    predicted_value: Optional[float] = None
    actual_value: Optional[float] = None
    error: Optional[float] = None
    abs_error: Optional[float] = None
    pct_error: Optional[float] = None
    within_interval: Optional[bool] = None
    direction_correct: Optional[bool] = None
    model_version: Optional[str] = None


class PendingPrediction(BaseModel):
    id: int
    asset_id: int
    horizon: int
    predicted_value: Optional[float] = None
    predicted_lower: Optional[float] = None
    predicted_upper: Optional[float] = None
    model_version: Optional[str] = None
    risk_category: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    days_until_evaluation: Optional[float] = None
    asset_name: Optional[str] = None


class ModelComparison(BaseModel):
    asset_id: int
    horizon: int
    models: list


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/summary", response_model=List[AccuracySummary])
async def accuracy_summary(
    asset_id: Optional[int] = Query(None, description="Filter by asset ID"),
    horizon: Optional[int] = Query(None, description="Filter by horizon (7, 14, 30)"),
):
    """Current accuracy snapshot per asset+horizon (30d and 90d rolling metrics)."""
    from scripts.compute_accuracy import get_accuracy_summary
    return get_accuracy_summary(asset_id=asset_id, horizon=horizon)


@router.get("/timeline/{asset_id}", response_model=List[AccuracyPoint])
async def accuracy_timeline(
    asset_id: int,
    horizon: int = Query(7, description="Prediction horizon in days"),
    days: int = Query(90, ge=7, le=365, description="Lookback window"),
):
    """Time-series of predicted vs actual values for charts."""
    from scripts.compute_accuracy import get_accuracy_timeline
    return get_accuracy_timeline(asset_id=asset_id, horizon=horizon, days=days)


@router.get("/pending", response_model=List[PendingPrediction])
async def pending_predictions():
    """Predictions awaiting evaluation (not yet matched to observations)."""
    from scripts.compute_accuracy import get_pending_predictions
    return get_pending_predictions()


@router.get("/model-compare", response_model=ModelComparison)
async def compare_models(
    asset_id: int = Query(..., description="Asset ID"),
    horizon: int = Query(7, description="Horizon in days"),
):
    """Compare accuracy across model versions for a given asset+horizon."""
    from scripts.compute_accuracy import get_accuracy_by_model
    return get_accuracy_by_model(asset_id=asset_id, horizon=horizon)


@router.post("/compute")
async def trigger_accuracy_computation():
    """Trigger accuracy computation (matching predictions to observations)."""
    from scripts.compute_accuracy import compute_accuracy
    try:
        result = compute_accuracy()
        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"Accuracy computation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
