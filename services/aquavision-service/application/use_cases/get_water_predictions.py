# application/use_cases/get_water_predictions.py
from typing import List, Optional

from application.dtos import WaterPredictionResponse
from infrastructure.db.repositories.water_prediction_repo import WaterPredictionRepository


class GetWaterPredictionsUseCase:
    def __init__(self, prediction_repo: WaterPredictionRepository):
        self._predictions = prediction_repo

    def execute(self, region_id: Optional[int] = None) -> List[WaterPredictionResponse]:
        rows = self._predictions.list(region_id=region_id)
        return [WaterPredictionResponse.model_validate(r) for r in rows]
