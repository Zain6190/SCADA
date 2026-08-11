# application/use_cases/generate_water_report.py
from datetime import date, timedelta
from typing import Optional

from application.dtos import ReportGenerateInput, WaterReportResponse
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository
from infrastructure.db.repositories.water_report_repo import WaterReportRepository


class GenerateWaterReportUseCase:
    """
    Stub: records a WaterReport row with a placeholder path.
    TODO(AquaVision): replace with real PDF generation (report-service)
    that aggregates indicators/predictions/alerts for the requested scope.
    """

    def __init__(
        self,
        report_repo: WaterReportRepository,
        indicator_repo: WaterIndicatorRepository,
    ):
        self._reports = report_repo
        self._indicators = indicator_repo

    def execute(self, payload: ReportGenerateInput) -> WaterReportResponse:
        week_start = payload.week_start_date or self._indicators.get_latest_week()
        if week_start is None:
            week_start = date.today() - timedelta(days=7)

        title = payload.title or f"Weekly Water Availability Report ({payload.scope})"
        file_path = f"/reports/water/{week_start.isoformat()}-{payload.scope.lower()}.pdf"

        row = self._reports.create(
            week_start_date=week_start,
            title=title,
            scope=payload.scope,
            region_id=payload.region_id,
            file_path=file_path,
            generated_by_user_id=None,  # TODO: set from JWT subject once auth wired
            status="Success",
        )
        return WaterReportResponse.model_validate(row)
