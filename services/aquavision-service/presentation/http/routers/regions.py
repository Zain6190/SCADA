# presentation/http/routers/regions.py
# GET /water/regions - list administrative regions (read-only from shared.regions).
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from application.dtos import RegionResponse
from application.use_cases.get_regions import GetRegionsUseCase
from infrastructure.db.engine import get_session
from infrastructure.db.repositories.region_repo import RegionRepository

router = APIRouter()


def get_use_case(session: Session = Depends(get_session)) -> GetRegionsUseCase:
    return GetRegionsUseCase(RegionRepository(session))


@router.get("/regions", response_model=List[RegionResponse])
async def list_regions(
    region_type: Optional[str] = Query(None, pattern="^(province|district|tehsil)$"),
    use_case: GetRegionsUseCase = Depends(get_use_case),
):
    """Administrative regions from shared.regions (read-only)."""
    return use_case.execute(region_type=region_type)
