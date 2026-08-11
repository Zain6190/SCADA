# presentation/http/routers/overview.py
# GET /water/overview - national KPI summary.
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from application.dtos import WaterOverviewResponse
from application.use_cases.get_water_overview import GetWaterOverviewUseCase
from infrastructure.db.engine import get_session
from infrastructure.db.repositories.water_alert_repo import WaterAlertRepository
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository

router = APIRouter()


def get_use_case(session: Session = Depends(get_session)) -> GetWaterOverviewUseCase:
    return GetWaterOverviewUseCase(
        WaterIndicatorRepository(session), WaterAlertRepository(session)
    )


@router.get("/overview", response_model=WaterOverviewResponse)
async def get_overview(use_case: GetWaterOverviewUseCase = Depends(get_use_case)):
    """Aggregate the latest week's indicators into national KPIs."""
    return use_case.execute()
