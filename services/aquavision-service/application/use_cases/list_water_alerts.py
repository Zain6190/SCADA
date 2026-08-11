# application/use_cases/list_water_alerts.py
from typing import List, Optional

from application.dtos import WaterAlertResponse
from infrastructure.db.repositories.water_alert_repo import WaterAlertRepository


class ListWaterAlertsUseCase:
    def __init__(self, alert_repo: WaterAlertRepository):
        self._alerts = alert_repo

    def execute(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        region_id: Optional[int] = None,
    ) -> List[WaterAlertResponse]:
        rows = self._alerts.list(status=status, severity=severity, region_id=region_id)
        return [WaterAlertResponse.model_validate(r) for r in rows]
