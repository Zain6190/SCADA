# application/use_cases/update_alert_status.py
from datetime import datetime, timezone
from typing import Optional

from application.dtos import WaterAlertResponse
from domain.entities import DomainValidationError, WaterAlert
from infrastructure.db.repositories.water_alert_repo import WaterAlertRepository


class UpdateAlertStatusUseCase:
    """Transition an alert through its state machine using domain logic."""

    def __init__(self, alert_repo: WaterAlertRepository):
        self._alerts = alert_repo

    def _load_domain(self, alert_id: int) -> tuple[WaterAlert, object]:
        row = self._alerts.get(alert_id)
        if row is None:
            raise DomainValidationError("Alert not found")
        alert = WaterAlert(
            id=row.id,
            region_id=row.region_id,
            week_start_date=row.week_start_date,
            alert_type=row.alert_type,
            severity=row.severity,
            status=row.status,
            notes=row.notes,
        )
        return alert, row

    def acknowledge(self, alert_id: int, notes: Optional[str] = None) -> WaterAlertResponse:
        alert, row = self._load_domain(alert_id)
        alert.acknowledge()
        if notes is not None:
            alert.notes = notes
        row.notes = alert.notes
        row.acknowledged_at = alert.acknowledged_at or datetime.now(timezone.utc)
        self._alerts.persist_status(row, alert.status)
        return WaterAlertResponse.model_validate(row)

    def resolve(self, alert_id: int, notes: Optional[str] = None) -> WaterAlertResponse:
        alert, row = self._load_domain(alert_id)
        alert.resolve()
        if notes is not None:
            alert.notes = notes
        row.notes = alert.notes
        row.resolved_at = alert.resolved_at or datetime.now(timezone.utc)
        self._alerts.persist_status(row, alert.status)
        return WaterAlertResponse.model_validate(row)

