# presentation/http/routers/thresholds.py
# GET /water/thresholds - list configurable severity/alert thresholds.
# PUT /water/thresholds/{threshold_name} - update a threshold value.
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from application.dtos import WaterThresholdResponse
from application.use_cases.get_water_thresholds import GetWaterThresholdsUseCase
from application.use_cases.update_water_threshold import UpdateWaterThresholdUseCase
from infrastructure.db.engine import get_session
from infrastructure.db.repositories.water_threshold_repo import WaterThresholdRepository

router = APIRouter()


def get_list_use_case(session: Session = Depends(get_session)) -> GetWaterThresholdsUseCase:
    return GetWaterThresholdsUseCase(WaterThresholdRepository(session))


def get_update_use_case(session: Session = Depends(get_session)) -> UpdateWaterThresholdUseCase:
    return UpdateWaterThresholdUseCase(WaterThresholdRepository(session))


@router.get("/thresholds", response_model=List[WaterThresholdResponse])
async def list_thresholds(
    use_case: GetWaterThresholdsUseCase = Depends(get_list_use_case),
):
    """Configurable WAI / rainfall / ET thresholds."""
    return use_case.execute()


@router.put("/thresholds/{threshold_name}", response_model=WaterThresholdResponse)
async def update_threshold(
    threshold_name: str,
    value: float = Query(..., description="New threshold value"),
    use_case: UpdateWaterThresholdUseCase = Depends(get_update_use_case),
):
    """Update a threshold (e.g. wai_critical_min)."""
    try:
        return use_case.execute(threshold_name, value)
    except KeyError:
        raise HTTPException(status_code=404, detail="Threshold not found")
