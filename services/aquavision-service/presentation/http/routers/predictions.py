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
async def list_predictions(
    region_id: Optional[int] = None,
    use_case: GetWaterPredictionsUseCase = Depends(get_use_case),
):
    """Predicted WAI/severity for upcoming weeks (model_version tracked per row)."""
    return use_case.execute(region_id=region_id)
