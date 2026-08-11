# application/use_cases/list_water_reports.py
from typing import List, Optional

from application.dtos import WaterReportResponse
from infrastructure.db.repositories.water_report_repo import WaterReportRepository


class ListWaterReportsUseCase:
    def __init__(self, report_repo: WaterReportRepository):
        self._reports = report_repo

    def execute(self, scope: Optional[str] = None) -> List[WaterReportResponse]:
        rows = self._reports.list(scope=scope)
        return [WaterReportResponse.model_validate(r) for r in rows]
