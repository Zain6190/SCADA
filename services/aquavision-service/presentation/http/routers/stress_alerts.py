# presentation/http/routers/stress_alerts.py
# WAI region-level stress alerts (water_alerts table).
# GET  /water/stress-alerts                  - list stress alerts
# POST /water/stress-alerts/{id}/ack         - acknowledge
# POST /water/stress-alerts/{id}/resolve     - resolve
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, and_, func
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import WaterAlert, Region

router = APIRouter()


class StressAlertResponse(BaseModel):
    id: int
    region_id: int
    region_name: Optional[str] = None
    week_start_date: str
    alert_type: str
    severity: str
    wai_score: Optional[float] = None
    rainfall_anomaly: Optional[float] = None
    et_anomaly: Optional[float] = None
    surface_water_change_pct: Optional[float] = None
    status: str
    confidence: Optional[float] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None

    class Config:
        from_attributes = True


class AckRequest(BaseModel):
    performed_by: str = "Operator"
    notes: Optional[str] = None


@router.get("/stress-alerts", response_model=List[StressAlertResponse])
def list_stress_alerts(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    region_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    q = (
        select(WaterAlert, Region.name.label("region_name"))
        .join(Region, WaterAlert.region_id == Region.id, isouter=True)
        .where(WaterAlert.alert_domain == "WATER_STRESS")
    )
    if status:
        q = q.where(WaterAlert.status == status)
    if severity:
        q = q.where(WaterAlert.severity == severity)
    if region_id:
        q = q.where(WaterAlert.region_id == region_id)
    q = q.order_by(desc(WaterAlert.created_at)).limit(limit)

    rows = session.execute(q).all()
    results = []
    for alert, region_name in rows:
        results.append(
            StressAlertResponse(
                id=alert.id,
                region_id=alert.region_id,
                region_name=region_name,
                week_start_date=str(alert.week_start_date),
                alert_type=alert.alert_type,
                severity=alert.severity,
                wai_score=float(alert.wai_score) if alert.wai_score else None,
                rainfall_anomaly=float(alert.rainfall_anomaly) if alert.rainfall_anomaly else None,
                et_anomaly=float(alert.et_anomaly) if alert.et_anomaly else None,
                surface_water_change_pct=float(alert.surface_water_change_pct) if alert.surface_water_change_pct else None,
                status=alert.status,
                confidence=float(alert.confidence) if hasattr(alert, "confidence") and alert.confidence else None,
                source=alert.alert_source if hasattr(alert, "alert_source") else None,
                notes=alert.notes,
                created_at=alert.created_at.isoformat() if alert.created_at else "",
                acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
            )
        )
    return results


@router.post("/stress-alerts/{alert_id}/ack", response_model=StressAlertResponse)
def ack_stress_alert(
    alert_id: int,
    body: AckRequest,
    session: Session = Depends(get_session),
):
    alert = session.get(WaterAlert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.status = "Acknowledged"
    alert.acknowledged_at = datetime.utcnow()
    if body.notes:
        alert.notes = (alert.notes or "") + f"\n[{body.performed_by}] {body.notes}"
    session.commit()
    session.refresh(alert)
    return _to_response(alert, session)


@router.post("/stress-alerts/{alert_id}/resolve", response_model=StressAlertResponse)
def resolve_stress_alert(
    alert_id: int,
    body: AckRequest,
    session: Session = Depends(get_session),
):
    alert = session.get(WaterAlert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.status = "Resolved"
    alert.resolved_at = datetime.utcnow()
    if body.notes:
        alert.notes = (alert.notes or "") + f"\n[{body.performed_by}] {body.notes}"
    session.commit()
    session.refresh(alert)
    return _to_response(alert, session)


def _to_response(alert: WaterAlert, session: Session) -> StressAlertResponse:
    region_name = None
    if alert.region_id:
        region = session.get(Region, alert.region_id)
        region_name = region.name if region else None
    return StressAlertResponse(
        id=alert.id,
        region_id=alert.region_id,
        region_name=region_name,
        week_start_date=str(alert.week_start_date),
        alert_type=alert.alert_type,
        severity=alert.severity,
        wai_score=float(alert.wai_score) if alert.wai_score else None,
        rainfall_anomaly=float(alert.rainfall_anomaly) if alert.rainfall_anomaly else None,
        et_anomaly=float(alert.et_anomaly) if alert.et_anomaly else None,
        surface_water_change_pct=float(alert.surface_water_change_pct) if alert.surface_water_change_pct else None,
        status=alert.status,
        confidence=float(alert.confidence) if hasattr(alert, "confidence") and alert.confidence else None,
        source=alert.alert_source if hasattr(alert, "alert_source") else None,
        notes=alert.notes,
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
    )
