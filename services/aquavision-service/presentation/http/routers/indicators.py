# presentation/http/routers/indicators.py
# GET/POST /water/indicators - read + ingest weekly water indicators.
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from application.dtos import WaterIndicatorCreate, WaterIndicatorResponse
from application.use_cases.get_water_indicators import GetWaterIndicatorsUseCase
from application.use_cases.upsert_water_indicator import UpsertWaterIndicatorUseCase
from infrastructure.db.engine import get_session
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository

router = APIRouter()


def get_read_use_case(session: Session = Depends(get_session)) -> GetWaterIndicatorsUseCase:
    return GetWaterIndicatorsUseCase(WaterIndicatorRepository(session))


def get_ingest_use_case(session: Session = Depends(get_session)) -> UpsertWaterIndicatorUseCase:
    return UpsertWaterIndicatorUseCase(WaterIndicatorRepository(session))


@router.get("/indicators", response_model=List[WaterIndicatorResponse])
async def list_indicators(
    region_id: Optional[int] = None,
    severity: Optional[str] = Query(None, pattern="^(Normal|Moderate|Stressed|Critical|Severe)$"),
    week_start_date: Optional[date] = None,
    limit: int = Query(100, ge=1, le=1000),
    use_case: GetWaterIndicatorsUseCase = Depends(get_read_use_case),
):
    """Weekly water indicators (WAI, rainfall, ET, surface water)."""
    return use_case.execute(
        region_id=region_id, severity=severity, week_start_date=week_start_date, limit=limit
    )


@router.post(
    "/indicators",
    response_model=WaterIndicatorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_indicator(
    payload: WaterIndicatorCreate,
    use_case: UpsertWaterIndicatorUseCase = Depends(get_ingest_use_case),
):
    """ETL ingest: upsert one indicator per region/week (idempotent)."""
    return use_case.execute(payload)
