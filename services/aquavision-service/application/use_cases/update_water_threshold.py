# application/use_cases/update_water_threshold.py
from application.dtos import WaterThresholdResponse
from infrastructure.db.repositories.water_threshold_repo import WaterThresholdRepository


class UpdateWaterThresholdUseCase:
    def __init__(self, threshold_repo: WaterThresholdRepository):
        self._thresholds = threshold_repo

    def execute(self, threshold_name: str, value: float) -> WaterThresholdResponse:
        row = self._thresholds.update(threshold_name, value)
        if row is None:
            raise KeyError(threshold_name)
        return WaterThresholdResponse.model_validate(row)
