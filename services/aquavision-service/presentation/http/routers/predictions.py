# presentation/http/routers/predictions.py
# GET /water/predictions - 2-week-ahead water stress predictions.
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from application.dtos import WaterPredictionResponse
from application.use_cases.get_water_predictions import GetWaterPredictionsUseCase
from infrastructure.db.engine import get_session
from infrastructure.db.repositories.water_prediction_repo import WaterPredictionRepository

router = APIRouter()


def get_use_case(session: Session = Depends(get_session)) -> GetWaterPredictionsUseCase:
    return GetWaterPredictionsUseCase(WaterPredictionRepository(session))


@router.get("/predictions", response_model=List[WaterPredictionResponse])
def list_predictions(
    region_id: Optional[int] = None,
    include_actual: bool = False,
    use_case: GetWaterPredictionsUseCase = Depends(get_use_case),
):
    """Predicted WAI/severity for upcoming weeks (model_version tracked per row).

    include_actual=True joins the observed indicator for each target week so
    the dashboard can chart predicted vs actual and show per-row error.
    """
    return use_case.execute(region_id=region_id, include_actual=include_actual)
