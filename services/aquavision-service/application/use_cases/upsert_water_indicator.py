# application/use_cases/upsert_water_indicator.py
from datetime import date

from application.dtos import WaterIndicatorCreate, WaterIndicatorResponse
from domain.water_classifier import classify_severity
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository


class UpsertWaterIndicatorUseCase:
    """ETL ingest entry point - upserts one weekly indicator per region/week."""

    def __init__(self, indicator_repo: WaterIndicatorRepository):
        self._indicators = indicator_repo

    def execute(self, payload: WaterIndicatorCreate) -> WaterIndicatorResponse:
        fields = dict(payload.model_dump(exclude={"region_id", "week_start_date"}))
        fields.pop("wai_score", None)

        severity = None
        if payload.wai_score is not None:
            severity = classify_severity(payload.wai_score)

        row = self._indicators.upsert(
            payload.region_id,
            payload.week_start_date,
            wai_score=payload.wai_score,
            severity=severity,
            **fields,
        )
        return WaterIndicatorResponse.model_validate(row)
