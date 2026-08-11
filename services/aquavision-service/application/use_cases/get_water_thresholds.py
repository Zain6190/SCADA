# application/use_cases/get_water_thresholds.py
from typing import List

from application.dtos import WaterThresholdResponse
from infrastructure.db.repositories.water_threshold_repo import WaterThresholdRepository


class GetWaterThresholdsUseCase:
    def __init__(self, threshold_repo: WaterThresholdRepository):
        self._thresholds = threshold_repo

    def execute(self) -> List[WaterThresholdResponse]:
        rows = self._thresholds.list()
        return [WaterThresholdResponse.model_validate(r) for r in rows]
