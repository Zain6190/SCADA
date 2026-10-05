# application/use_cases/get_water_predictions.py
from typing import List, Optional

from application.dtos import WaterPredictionResponse
from infrastructure.db.repositories.water_prediction_repo import WaterPredictionRepository


class GetWaterPredictionsUseCase:
    def __init__(self, prediction_repo: WaterPredictionRepository):
        self._predictions = prediction_repo

    def execute(
        self,
        region_id: Optional[int] = None,
        include_actual: bool = False,
    ) -> List[WaterPredictionResponse]:
        if not include_actual:
            rows = self._predictions.list(region_id=region_id)
            return [WaterPredictionResponse.model_validate(r) for r in rows]

        responses: List[WaterPredictionResponse] = []
        for pred, region_name, actual_wai, actual_severity in (
            self._predictions.list_with_actual(region_id=region_id)
        ):
            resp = WaterPredictionResponse.model_validate(pred)
            resp.region_name = region_name
            if actual_wai is not None:
                resp.actual_wai_score = float(actual_wai)
                resp.actual_severity = actual_severity
                if resp.predicted_wai_score is not None:
                    resp.absolute_error = round(
                        abs(float(actual_wai) - float(resp.predicted_wai_score)), 2
                    )
            responses.append(resp)
        return responses
