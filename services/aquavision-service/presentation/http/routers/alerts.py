# presentation/http/routers/alerts.py
# GET /water/alerts - list alerts.
# POST /water/alerts/{id}/ack - New -> Acknowledged.
# POST /water/alerts/{id}/resolve - (New|Acknowledged) -> Resolved.
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from application.dtos import AlertStatusInput, WaterAlertResponse
from application.use_cases.list_water_alerts import ListWaterAlertsUseCase
from application.use_cases.update_alert_status import UpdateAlertStatusUseCase
from domain.entities import DomainValidationError
from infrastructure.db.engine import get_session
from infrastructure.db.repositories.water_alert_repo import WaterAlertRepository

router = APIRouter()


def get_list_use_case(session: Session = Depends(get_session)) -> ListWaterAlertsUseCase:
    return ListWaterAlertsUseCase(WaterAlertRepository(session))


def get_update_use_case(session: Session = Depends(get_session)) -> UpdateAlertStatusUseCase:
    return UpdateAlertStatusUseCase(WaterAlertRepository(session))


@router.get("/alerts", response_model=List[WaterAlertResponse])
async def list_alerts(
    status: Optional[str] = Query(None, pattern="^(New|Acknowledged|Resolved)$"),
    severity: Optional[str] = Query(None, pattern="^(Critical|Severe|Warning)$"),
    region_id: Optional[int] = None,
    use_case: ListWaterAlertsUseCase = Depends(get_list_use_case),
):
    """Water alerts with optional filters."""
    return use_case.execute(status=status, severity=severity, region_id=region_id)


@router.post("/alerts/{alert_id}/ack", response_model=WaterAlertResponse)
async def acknowledge_alert(
    alert_id: int,
    payload: AlertStatusInput | None = None,
    use_case: UpdateAlertStatusUseCase = Depends(get_update_use_case),
):
    """Acknowledge an alert (New -> Acknowledged)."""
    try:
        return use_case.acknowledge(alert_id, notes=payload.notes if payload else None)
    except DomainValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/alerts/{alert_id}/resolve", response_model=WaterAlertResponse)
async def resolve_alert(
    alert_id: int,
    payload: AlertStatusInput | None = None,
    use_case: UpdateAlertStatusUseCase = Depends(get_update_use_case),
):
    """Resolve an alert ((New|Acknowledged) -> Resolved)."""
    try:
        return use_case.resolve(alert_id, notes=payload.notes if payload else None)
    except DomainValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
