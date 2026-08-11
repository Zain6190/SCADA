# presentation/http/routers/map_data.py
# GET /water/map-data - GeoJSON of region water state joined with geometry.
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from application.dtos import WaterMapResponse
from application.use_cases.get_water_map_data import GetWaterMapDataUseCase
from infrastructure.db.engine import get_session
from infrastructure.db.repositories.region_repo import RegionRepository
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository

router = APIRouter()


def get_use_case(session: Session = Depends(get_session)) -> GetWaterMapDataUseCase:
    return GetWaterMapDataUseCase(
        WaterIndicatorRepository(session), RegionRepository(session)
    )


@router.get("/map-data", response_model=WaterMapResponse)
async def get_map_data(
    week: Optional[str] = Query(
        None,
        description="ISO week '2026-W30' or date '2026-07-27'. Defaults to latest week.",
    ),
    region_type: Optional[str] = Query(
        None, pattern="^(province|district|tehsil)$", description="Filter regions by type."
    ),
    use_case: GetWaterMapDataUseCase = Depends(get_use_case),
):
    """Water indicators joined with shared.regions geometry as GeoJSON."""
    return use_case.execute(week=week, region_type=region_type)
