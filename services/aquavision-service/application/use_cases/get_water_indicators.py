# application/use_cases/get_water_indicators.py
from datetime import date
from typing import List, Optional

from application.dtos import WaterIndicatorResponse
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository


class GetWaterIndicatorsUseCase:
    def __init__(self, indicator_repo: WaterIndicatorRepository):
        self._indicators = indicator_repo

    def execute(
        self,
        region_id: Optional[int] = None,
        severity: Optional[str] = None,
        week_start_date: Optional[date] = None,
        limit: int = 100,
    ) -> List[WaterIndicatorResponse]:
        rows = self._indicators.list(
            region_id=region_id,
            severity=severity,
            week_start_date=week_start_date,
            limit=limit,
        )
        return [WaterIndicatorResponse.model_validate(r) for r in rows]
