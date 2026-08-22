# presentation/http/routers/operational.py
# Operational endpoints for IRSA-based water monitoring.
# GET  /water/operational/assets           - list all assets with current readings
# GET  /water/operational/assets/{id}      - asset detail + history
# GET  /water/operational/assets/{id}/observations - observation history
# GET  /water/operational/alerts           - list operational alerts
# POST /water/operational/alerts/{id}/ack  - acknowledge alert
# POST /water/operational/alerts/{id}/resolve - resolve alert
# GET  /water/operational/thresholds       - list asset thresholds
# PUT  /water/operational/thresholds/{id}  - update asset threshold
# POST /water/operational/evaluate         - trigger threshold evaluation
from datetime import datetime, timedelta, date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, and_, func
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import (
    WaterAsset, WaterAssetThreshold, WaterObservation,
    WaterOperationalAlert, WaterAlertAuditLog,
    WaterRiverNetwork, WaterTravelTimeModel,
    WaterFFDObservation,
)

router = APIRouter()


# ─── Pydantic Schemas ──────────────────────────────────────────────────────

class AssetResponse(BaseModel):
    id: int
    canonical_name: str
    asset_type: str
    river: Optional[str]
    province: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    capacity_maf: Optional[float]
    normal_level_ft: Optional[float]
    warning_level_ft: Optional[float]
    critical_level_ft: Optional[float]
    is_active: bool

    # Current readings
    current_level_ft: Optional[float] = None
    current_inflow: Optional[float] = None
    current_outflow: Optional[float] = None
    current_discharge: Optional[float] = None
    last_observed_at: Optional[datetime] = None
    data_age_hours: Optional[float] = None

    # Current alert status
    active_alert_count: int = 0
    highest_severity: Optional[str] = None

    # ML flood classification (latest from alerts)
    flood_probability: Optional[float] = None
    flood_severity: Optional[str] = None
    flood_recommendation: Optional[str] = None

    class Config:
        from_attributes = True


class ObservationResponse(BaseModel):
    id: int
    asset_id: int
    observed_at: datetime
    water_level_ft: Optional[float]
    inflow_cusecs: Optional[float]
    outflow_cusecs: Optional[float]
    discharge_cusecs: Optional[float]
    upstream_discharge_cusecs: Optional[float]
    downstream_discharge_cusecs: Optional[float]
    data_status: str
    quality_flag: Optional[str]

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    id: int
    asset_id: int
    asset_name: Optional[str] = None
    alert_type: str
    severity: str
    status: str
    message: str
    triggered_value: Optional[float]
    threshold_value: Optional[float]
    reading_level_ft: Optional[float]
    reading_inflow_cusecs: Optional[float]
    reading_outflow_cusecs: Optional[float]
    reading_discharge_cusecs: Optional[float]
    rate_of_change_ft_6h: Optional[float]
    created_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    notes: Optional[str]
    episode_id: Optional[int] = None
    downstream_impact_summary: Optional[str] = None
    downstream_population_exposed: Optional[int] = None
    downstream_bridges_at_risk: Optional[int] = None
    downstream_hospitals_at_risk: Optional[int] = None
    downstream_furthest_asset: Optional[str] = None
    downstream_furthest_arrival_hours: Optional[float] = None
    flood_probability: Optional[float] = None
    flood_severity: Optional[str] = None
    flood_confidence: Optional[str] = None
    flood_recommendation: Optional[str] = None
    alert_source: Optional[str] = None

    class Config:
        from_attributes = True


class ThresholdResponse(BaseModel):
    id: int
    asset_id: int
    asset_name: Optional[str] = None
    warning_level_ft: Optional[float]
    danger_level_ft: Optional[float]
    critical_level_ft: Optional[float]
    warning_inflow: Optional[float]
    danger_inflow: Optional[float]
    warning_discharge: Optional[float]
    danger_discharge: Optional[float]
    level_rise_watch_6h: Optional[float]
    level_rise_warning_6h: Optional[float]
    level_rise_critical_6h: Optional[float]
    stale_hours_warning: int
    stale_hours_critical: int
    is_active: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


class ThresholdUpdateInput(BaseModel):
    warning_level_ft: Optional[float] = None
    danger_level_ft: Optional[float] = None
    critical_level_ft: Optional[float] = None
    warning_inflow: Optional[float] = None
    danger_inflow: Optional[float] = None
    warning_discharge: Optional[float] = None
    danger_discharge: Optional[float] = None
    level_rise_watch_6h: Optional[float] = None
    level_rise_warning_6h: Optional[float] = None
    level_rise_critical_6h: Optional[float] = None
    stale_hours_warning: Optional[int] = None
    stale_hours_critical: Optional[int] = None
    notes: Optional[str] = None


class AlertActionInput(BaseModel):
    performed_by: str = "Operator"
    notes: Optional[str] = None


class EvaluateResponse(BaseModel):
    assets_checked: int
    new_alerts: int
    alerts: dict


def _build_alert_response(alert: WaterOperationalAlert, asset: WaterAsset = None) -> AlertResponse:
    """Build AlertResponse from alert + optional asset."""
    if not asset:
        from infrastructure.db.engine import SessionLocal
        with SessionLocal() as session:
            asset = session.get(WaterAsset, alert.asset_id)
    return AlertResponse(
        id=alert.id,
        asset_id=alert.asset_id,
        asset_name=asset.canonical_name if asset else None,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        message=alert.message,
        triggered_value=float(alert.triggered_value) if alert.triggered_value else None,
        threshold_value=float(alert.threshold_value) if alert.threshold_value else None,
        reading_level_ft=float(alert.reading_level_ft) if alert.reading_level_ft else None,
        reading_inflow_cusecs=float(alert.reading_inflow_cusecs) if alert.reading_inflow_cusecs else None,
        reading_outflow_cusecs=float(alert.reading_outflow_cusecs) if alert.reading_outflow_cusecs else None,
        reading_discharge_cusecs=float(alert.reading_discharge_cusecs) if alert.reading_discharge_cusecs else None,
        rate_of_change_ft_6h=float(alert.rate_of_change_ft_6h) if alert.rate_of_change_ft_6h else None,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        notes=alert.notes,
        episode_id=alert.episode_id,
        downstream_impact_summary=alert.downstream_impact_summary,
        downstream_population_exposed=alert.downstream_population_exposed,
        downstream_bridges_at_risk=alert.downstream_bridges_at_risk,
        downstream_hospitals_at_risk=alert.downstream_hospitals_at_risk,
        downstream_furthest_asset=alert.downstream_furthest_asset,
        downstream_furthest_arrival_hours=float(alert.downstream_furthest_arrival_hours) if alert.downstream_furthest_arrival_hours else None,
        flood_probability=float(alert.flood_probability) if alert.flood_probability else None,
        flood_severity=alert.flood_severity,
        flood_confidence=str(alert.flood_confidence) if alert.flood_confidence else None,
        flood_recommendation=alert.flood_recommendation,
        alert_source=alert.alert_source,
    )


# ─── ASSETS ─────────────────────────────────────────────────────────────────

@router.get("/operational/assets", response_model=List[AssetResponse])
async def list_assets(
    asset_type: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """List all water assets with current readings and alert status."""
    query = select(WaterAsset).where(WaterAsset.is_active == True)
    if asset_type:
        query = query.where(WaterAsset.asset_type == asset_type)
    assets = session.execute(query.order_by(WaterAsset.canonical_name)).scalars().all()

    result = []
    for asset in assets:
        # Get latest observation
        latest_obs = session.execute(
            select(WaterObservation)
            .where(WaterObservation.asset_id == asset.id)
            .order_by(desc(WaterObservation.observed_at))
            .limit(1)
        ).scalar_one_or_none()

        # Count active alerts
        alert_count = session.execute(
            select(func.count(WaterOperationalAlert.id)).where(
                WaterOperationalAlert.asset_id == asset.id,
                WaterOperationalAlert.status.in_(["NEW", "ACKNOWLEDGED", "INVESTIGATING"]),
            )
        ).scalar() or 0

        # Get highest severity
        highest = session.execute(
            select(WaterOperationalAlert.severity).where(
                WaterOperationalAlert.asset_id == asset.id,
                WaterOperationalAlert.status.in_(["NEW", "ACKNOWLEDGED", "INVESTIGATING"]),
            ).order_by(
                # CRITICAL > WARNING > ADVISORY > WATCH > NORMAL
                WaterOperationalAlert.severity.desc()
            ).limit(1)
        ).scalar_one_or_none()

        # Get latest flood classification from most recent alert with probability
        flood_prob = session.execute(
            select(WaterOperationalAlert.flood_probability, WaterOperationalAlert.flood_severity, WaterOperationalAlert.flood_recommendation)
            .where(
                WaterOperationalAlert.asset_id == asset.id,
                WaterOperationalAlert.flood_probability.isnot(None),
            ).order_by(desc(WaterOperationalAlert.created_at)).limit(1)
        ).first()

        # Fallback: threshold-based probability if no ML classification exists
        fp_value, fp_severity, fp_rec = None, None, None
        if flood_prob:
            fp_value = float(flood_prob[0]) if flood_prob[0] else None
            fp_severity = flood_prob[1]
            fp_rec = flood_prob[2]
        elif latest_obs:
            discharge = float(latest_obs.discharge_cusecs) if latest_obs.discharge_cusecs else None
            inflow = float(latest_obs.inflow_cusecs) if latest_obs.inflow_cusecs else None
            level = float(latest_obs.water_level_ft) if latest_obs.water_level_ft else None
            value = discharge or inflow or level
            if value and asset.warning_level_ft and asset.critical_level_ft:
                warn = float(asset.warning_level_ft)
                crit = float(asset.critical_level_ft)
                if crit > warn and value >= warn:
                    ratio = min((value - warn) / (crit - warn), 1.0)
                    fp_value = round(0.05 + ratio * 0.85, 4)
                    fp_severity = "CRITICAL" if ratio > 0.8 else "HIGH" if ratio > 0.5 else "MODERATE" if ratio > 0.2 else "LOW"
                    fp_rec = f"Level at {ratio*100:.0f}% of critical threshold"
            elif value and discharge:
                fp_value = 0.05
                fp_severity = "LOW"
                fp_rec = "Normal operations - threshold-based estimate"

        data_age = None
        if latest_obs and latest_obs.observed_at:
            obs_time = latest_obs.observed_at
            if obs_time.tzinfo:
                data_age = (datetime.utcnow().replace(tzinfo=obs_time.tzinfo) - obs_time).total_seconds() / 3600
            else:
                data_age = (datetime.utcnow() - obs_time).total_seconds() / 3600

        result.append(AssetResponse(
            id=asset.id,
            canonical_name=asset.canonical_name,
            asset_type=asset.asset_type,
            river=asset.river,
            province=asset.province,
            latitude=float(asset.latitude) if asset.latitude else None,
            longitude=float(asset.longitude) if asset.longitude else None,
            capacity_maf=float(asset.capacity_maf) if asset.capacity_maf else None,
            normal_level_ft=float(asset.normal_level_ft) if asset.normal_level_ft else None,
            warning_level_ft=float(asset.warning_level_ft) if asset.warning_level_ft else None,
            critical_level_ft=float(asset.critical_level_ft) if asset.critical_level_ft else None,
            is_active=asset.is_active,
            current_level_ft=float(latest_obs.water_level_ft) if latest_obs and latest_obs.water_level_ft else None,
            current_inflow=float(latest_obs.inflow_cusecs) if latest_obs and latest_obs.inflow_cusecs else None,
            current_outflow=float(latest_obs.outflow_cusecs) if latest_obs and latest_obs.outflow_cusecs else None,
            current_discharge=float(latest_obs.discharge_cusecs) if latest_obs and latest_obs.discharge_cusecs else None,
            last_observed_at=latest_obs.observed_at if latest_obs else None,
            data_age_hours=round(data_age, 1) if data_age else None,
            active_alert_count=alert_count,
            highest_severity=highest,
            flood_probability=fp_value,
            flood_severity=fp_severity,
            flood_recommendation=fp_rec,
        ))

    return result


@router.get("/operational/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: int,
    session: Session = Depends(get_session),
):
    """Get single asset with current readings."""
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    latest_obs = session.execute(
        select(WaterObservation)
        .where(WaterObservation.asset_id == asset.id)
        .order_by(desc(WaterObservation.observed_at))
        .limit(1)
    ).scalar_one_or_none()

    alert_count = session.execute(
        select(func.count(WaterOperationalAlert.id)).where(
            WaterOperationalAlert.asset_id == asset.id,
            WaterOperationalAlert.status.in_(["NEW", "ACKNOWLEDGED", "INVESTIGATING"]),
        )
    ).scalar() or 0

    highest = session.execute(
        select(WaterOperationalAlert.severity).where(
            WaterOperationalAlert.asset_id == asset.id,
            WaterOperationalAlert.status.in_(["NEW", "ACKNOWLEDGED", "INVESTIGATING"]),
        ).order_by(WaterOperationalAlert.severity.desc()).limit(1)
    ).scalar_one_or_none()

    data_age = None
    if latest_obs and latest_obs.observed_at:
        obs_time = latest_obs.observed_at
        if obs_time.tzinfo:
            data_age = (datetime.utcnow().replace(tzinfo=obs_time.tzinfo) - obs_time).total_seconds() / 3600
        else:
            data_age = (datetime.utcnow() - obs_time).total_seconds() / 3600

    return AssetResponse(
        id=asset.id,
        canonical_name=asset.canonical_name,
        asset_type=asset.asset_type,
        river=asset.river,
        province=asset.province,
        latitude=float(asset.latitude) if asset.latitude else None,
        longitude=float(asset.longitude) if asset.longitude else None,
        capacity_maf=float(asset.capacity_maf) if asset.capacity_maf else None,
        normal_level_ft=float(asset.normal_level_ft) if asset.normal_level_ft else None,
        warning_level_ft=float(asset.warning_level_ft) if asset.warning_level_ft else None,
        critical_level_ft=float(asset.critical_level_ft) if asset.critical_level_ft else None,
        is_active=asset.is_active,
        current_level_ft=float(latest_obs.water_level_ft) if latest_obs and latest_obs.water_level_ft else None,
        current_inflow=float(latest_obs.inflow_cusecs) if latest_obs and latest_obs.inflow_cusecs else None,
        current_outflow=float(latest_obs.outflow_cusecs) if latest_obs and latest_obs.outflow_cusecs else None,
        current_discharge=float(latest_obs.discharge_cusecs) if latest_obs and latest_obs.discharge_cusecs else None,
        last_observed_at=latest_obs.observed_at if latest_obs else None,
        data_age_hours=round(data_age, 1) if data_age else None,
        active_alert_count=alert_count,
        highest_severity=highest,
    )


@router.get("/operational/assets/{asset_id}/observations", response_model=List[ObservationResponse])
async def get_observations(
    asset_id: int,
    days: int = Query(7, ge=1, le=90),
    session: Session = Depends(get_session),
):
    """Get observation history for an asset."""
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    since = datetime.utcnow() - timedelta(days=days)
    observations = session.execute(
        select(WaterObservation)
        .where(
            WaterObservation.asset_id == asset_id,
            WaterObservation.observed_at >= since,
        )
        .order_by(desc(WaterObservation.observed_at))
    ).scalars().all()

    return [
        ObservationResponse(
            id=obs.id,
            asset_id=obs.asset_id,
            observed_at=obs.observed_at,
            water_level_ft=float(obs.water_level_ft) if obs.water_level_ft else None,
            inflow_cusecs=float(obs.inflow_cusecs) if obs.inflow_cusecs else None,
            outflow_cusecs=float(obs.outflow_cusecs) if obs.outflow_cusecs else None,
            discharge_cusecs=float(obs.discharge_cusecs) if obs.discharge_cusecs else None,
            upstream_discharge_cusecs=float(obs.upstream_discharge_cusecs) if obs.upstream_discharge_cusecs else None,
            downstream_discharge_cusecs=float(obs.downstream_discharge_cusecs) if obs.downstream_discharge_cusecs else None,
            data_status=obs.data_status,
            quality_flag=obs.quality_flag,
        )
        for obs in observations
    ]


# ─── ALERTS ─────────────────────────────────────────────────────────────────

@router.get("/operational/alerts", response_model=List[AlertResponse])
async def list_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    asset_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """List operational alerts with filters."""
    query = select(WaterOperationalAlert)
    if status:
        query = query.where(WaterOperationalAlert.status == status)
    if severity:
        query = query.where(WaterOperationalAlert.severity == severity)
    if asset_id:
        query = query.where(WaterOperationalAlert.asset_id == asset_id)

    alerts = session.execute(
        query.order_by(desc(WaterOperationalAlert.created_at)).limit(limit)
    ).scalars().all()

    asset_ids = list({a.asset_id for a in alerts})
    assets_map = {}
    if asset_ids:
        assets = session.execute(
            select(WaterAsset).where(WaterAsset.id.in_(asset_ids))
        ).scalars().all()
        assets_map = {a.id: a for a in assets}

    result = []
    for alert in alerts:
        result.append(_build_alert_response(alert, assets_map.get(alert.asset_id)))

    return result


@router.post("/operational/alerts/{alert_id}/investigate", response_model=AlertResponse)
async def investigate_alert(
    alert_id: int,
    payload: AlertActionInput = AlertActionInput(),
    session: Session = Depends(get_session),
):
    """Start investigating an alert (ACKNOWLEDGED -> INVESTIGATING)."""
    alert = session.get(WaterOperationalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status not in ("ACKNOWLEDGED",):
        raise HTTPException(status_code=409, detail=f"Cannot investigate alert in status '{alert.status}'")

    old_status = alert.status
    alert.status = "INVESTIGATING"
    alert.acknowledged_by = payload.performed_by
    if not alert.acknowledged_at:
        alert.acknowledged_at = datetime.utcnow()
    if payload.notes:
        alert.notes = payload.notes

    audit = WaterAlertAuditLog(
        alert_id=alert.id,
        action="INVESTIGATING",
        performed_by=payload.performed_by,
        old_status=old_status,
        new_status="INVESTIGATING",
        notes=payload.notes,
    )
    session.add(audit)
    session.commit()

    asset = session.get(WaterAsset, alert.asset_id)
    return _build_alert_response(alert, asset)


@router.post("/operational/alerts/{alert_id}/escalate", response_model=AlertResponse)
async def escalate_alert(
    alert_id: int,
    payload: AlertActionInput = AlertActionInput(),
    session: Session = Depends(get_session),
):
    """Escalate an alert (INVESTIGATING -> ESCALATED)."""
    alert = session.get(WaterOperationalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status not in ("INVESTIGATING",):
        raise HTTPException(status_code=409, detail=f"Cannot escalate alert in status '{alert.status}'")

    old_status = alert.status
    alert.status = "ESCALATED"
    if payload.notes:
        alert.notes = payload.notes

    audit = WaterAlertAuditLog(
        alert_id=alert.id,
        action="ESCALATED",
        performed_by=payload.performed_by,
        old_status=old_status,
        new_status="ESCALATED",
        notes=payload.notes,
    )
    session.add(audit)
    session.commit()

    asset = session.get(WaterAsset, alert.asset_id)
    return _build_alert_response(alert, asset)


@router.post("/operational/alerts/{alert_id}/ack", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    payload: AlertActionInput = AlertActionInput(),
    session: Session = Depends(get_session),
):
    """Acknowledge an alert (NEW -> ACKNOWLEDGED)."""
    alert = session.get(WaterOperationalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status not in ("NEW",):
        raise HTTPException(status_code=409, detail=f"Cannot acknowledge alert in status '{alert.status}'")

    old_status = alert.status
    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_by = payload.performed_by
    alert.acknowledged_at = datetime.utcnow()
    if payload.notes:
        alert.notes = payload.notes

    audit = WaterAlertAuditLog(
        alert_id=alert.id,
        action="ACKNOWLEDGED",
        performed_by=payload.performed_by,
        old_status=old_status,
        new_status="ACKNOWLEDGED",
        notes=payload.notes,
    )
    session.add(audit)
    session.commit()

    asset = session.get(WaterAsset, alert.asset_id)
    return _build_alert_response(alert, asset)


@router.post("/operational/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: int,
    payload: AlertActionInput = AlertActionInput(),
    session: Session = Depends(get_session),
):
    """Resolve an alert (NEW|ACKNOWLEDGED|INVESTIGATING|ESCALATED -> RESOLVED)."""
    alert = session.get(WaterOperationalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status not in ("NEW", "ACKNOWLEDGED", "INVESTIGATING", "ESCALATED"):
        raise HTTPException(status_code=409, detail=f"Cannot resolve alert in status '{alert.status}'")

    old_status = alert.status
    alert.status = "RESOLVED"
    alert.resolved_by = payload.performed_by
    alert.resolved_at = datetime.utcnow()
    if payload.notes:
        alert.notes = payload.notes

    audit = WaterAlertAuditLog(
        alert_id=alert.id,
        action="RESOLVED",
        performed_by=payload.performed_by,
        old_status=old_status,
        new_status="RESOLVED",
        notes=payload.notes,
    )
    session.add(audit)
    session.commit()

    asset = session.get(WaterAsset, alert.asset_id)
    return _build_alert_response(alert, asset)


# ─── THRESHOLDS ─────────────────────────────────────────────────────────────

@router.get("/operational/thresholds", response_model=List[ThresholdResponse])
async def list_thresholds(
    session: Session = Depends(get_session),
):
    """List all asset threshold configurations."""
    thresholds = session.execute(
        select(WaterAssetThreshold).order_by(WaterAssetThreshold.asset_id)
    ).scalars().all()

    result = []
    for t in thresholds:
        asset = session.get(WaterAsset, t.asset_id)
        result.append(ThresholdResponse(
            id=t.id,
            asset_id=t.asset_id,
            asset_name=asset.canonical_name if asset else None,
            warning_level_ft=float(t.warning_level_ft) if t.warning_level_ft else None,
            danger_level_ft=float(t.danger_level_ft) if t.danger_level_ft else None,
            critical_level_ft=float(t.critical_level_ft) if t.critical_level_ft else None,
            warning_inflow=float(t.warning_inflow) if t.warning_inflow else None,
            danger_inflow=float(t.danger_inflow) if t.danger_inflow else None,
            warning_discharge=float(t.warning_discharge) if t.warning_discharge else None,
            danger_discharge=float(t.danger_discharge) if t.danger_discharge else None,
            level_rise_watch_6h=float(t.level_rise_watch_6h) if t.level_rise_watch_6h else None,
            level_rise_warning_6h=float(t.level_rise_warning_6h) if t.level_rise_warning_6h else None,
            level_rise_critical_6h=float(t.level_rise_critical_6h) if t.level_rise_critical_6h else None,
            stale_hours_warning=t.stale_hours_warning,
            stale_hours_critical=t.stale_hours_critical,
            is_active=t.is_active,
            notes=t.notes,
        ))

    return result


@router.put("/operational/thresholds/{threshold_id}", response_model=ThresholdResponse)
async def update_threshold(
    threshold_id: int,
    payload: ThresholdUpdateInput,
    session: Session = Depends(get_session),
):
    """Update an asset threshold configuration."""
    threshold = session.get(WaterAssetThreshold, threshold_id)
    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(threshold, field, value)
    threshold.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(threshold)

    asset = session.get(WaterAsset, threshold.asset_id)
    return ThresholdResponse(
        id=threshold.id,
        asset_id=threshold.asset_id,
        asset_name=asset.canonical_name if asset else None,
        warning_level_ft=float(threshold.warning_level_ft) if threshold.warning_level_ft else None,
        danger_level_ft=float(threshold.danger_level_ft) if threshold.danger_level_ft else None,
        critical_level_ft=float(threshold.critical_level_ft) if threshold.critical_level_ft else None,
        warning_inflow=float(threshold.warning_inflow) if threshold.warning_inflow else None,
        danger_inflow=float(threshold.danger_inflow) if threshold.danger_inflow else None,
        warning_discharge=float(threshold.warning_discharge) if threshold.warning_discharge else None,
        danger_discharge=float(threshold.danger_discharge) if threshold.danger_discharge else None,
        level_rise_watch_6h=float(threshold.level_rise_watch_6h) if threshold.level_rise_watch_6h else None,
        level_rise_warning_6h=float(threshold.level_rise_warning_6h) if threshold.level_rise_warning_6h else None,
        level_rise_critical_6h=float(threshold.level_rise_critical_6h) if threshold.level_rise_critical_6h else None,
        stale_hours_warning=threshold.stale_hours_warning,
        stale_hours_critical=threshold.stale_hours_critical,
        is_active=threshold.is_active,
        notes=threshold.notes,
    )


# ─── EVALUATE ───────────────────────────────────────────────────────────────

@router.post("/operational/evaluate", response_model=EvaluateResponse)
async def trigger_evaluation(
    session: Session = Depends(get_session),
):
    """Manually trigger threshold evaluation for all assets."""
    from infrastructure.thresholds.engine import evaluate_all_assets
    result = evaluate_all_assets(session)
    return EvaluateResponse(**result)


# ─── DOWNSTREAM IMPACT ──────────────────────────────────────────────────────

class TravelTimeResponse(BaseModel):
    flow_min_cusecs: float
    flow_max_cusecs: float
    travel_time_min_hours: float
    travel_time_max_hours: float
    travel_time_expected_hours: float
    confidence: str
    method: str


class DownstreamSegmentResponse(BaseModel):
    segment_id: int
    river_name: str
    upstream_asset_id: int
    upstream_asset_name: str
    downstream_asset_id: int
    downstream_asset_name: str
    distance_km: Optional[float]
    segment_order: int

    # Travel time for current flow
    travel_time_min_hours: Optional[float]
    travel_time_max_hours: Optional[float]
    travel_time_expected_hours: Optional[float]
    travel_time_confidence: Optional[str]
    arrival_window_min: Optional[datetime]
    arrival_window_expected: Optional[datetime]
    arrival_window_max: Optional[datetime]

    # Current readings at downstream asset
    downstream_level_ft: Optional[float]
    downstream_discharge: Optional[float]
    downstream_alert_severity: Optional[str]

    # Status
    segment_status: str
    data_source: str


class DownstreamImpactResponse(BaseModel):
    source_asset_id: int
    source_asset_name: str
    source_release_cusecs: Optional[float]
    source_level_ft: Optional[float]
    river_name: str
    chain: List[DownstreamSegmentResponse]
    total_distance_km: Optional[float]
    total_travel_time_hours: Optional[float]


@router.get("/operational/impact/{asset_id}", response_model=DownstreamImpactResponse)
async def get_downstream_impact(
    asset_id: int,
    session: Session = Depends(get_session),
):
    """Get downstream impact chain for an asset.
    
    Returns the full downstream chain with travel times, arrival windows,
    and current conditions at each downstream asset.
    """
    asset = session.get(WaterAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Get latest observation for release/flow
    latest_obs = session.execute(
        select(WaterObservation)
        .where(WaterObservation.asset_id == asset_id)
        .order_by(desc(WaterObservation.observed_at))
        .limit(1)
    ).scalar_one_or_none()

    release_cusecs = float(latest_obs.inflow_cusecs or latest_obs.discharge_cusecs or 0) if latest_obs else None
    source_level = float(latest_obs.water_level_ft) if latest_obs and latest_obs.water_level_ft else None

    # Get all downstream segments starting from this asset
    chain = []
    current_asset_id = asset_id
    total_distance = 0
    total_travel_time = 0

    while True:
        # Find next segment downstream
        segment = session.execute(
            select(WaterRiverNetwork).where(
                WaterRiverNetwork.upstream_asset_id == current_asset_id
            ).order_by(WaterRiverNetwork.segment_order)
        ).scalar_one_or_none()

        if not segment:
            break

        # Get travel time model for current flow
        tt_model = None
        if release_cusecs and release_cusecs > 0:
            tt_model = session.execute(
                select(WaterTravelTimeModel).where(
                    WaterTravelTimeModel.river_segment_id == segment.id,
                    WaterTravelTimeModel.flow_min_cusecs <= release_cusecs,
                    WaterTravelTimeModel.flow_max_cusecs > release_cusecs,
                )
            ).scalar_one_or_none()

        # Calculate arrival windows
        now = datetime.utcnow()
        arrival_min = None
        arrival_expected = None
        arrival_max = None
        tt_min = None
        tt_max = None
        tt_expected = None
        tt_confidence = None

        if tt_model:
            tt_min = float(tt_model.travel_time_min_hours)
            tt_max = float(tt_model.travel_time_max_hours)
            tt_expected = float(tt_model.travel_time_expected_hours)
            tt_confidence = tt_model.confidence
            arrival_min = now + timedelta(hours=tt_min)
            arrival_expected = now + timedelta(hours=tt_expected)
            arrival_max = now + timedelta(hours=tt_max)

        # Get downstream asset current readings
        downstream_obs = session.execute(
            select(WaterObservation)
            .where(WaterObservation.asset_id == segment.downstream_asset_id)
            .order_by(desc(WaterObservation.observed_at))
            .limit(1)
        ).scalar_one_or_none()

        downstream_level = float(downstream_obs.water_level_ft) if downstream_obs and downstream_obs.water_level_ft else None
        downstream_discharge = float(downstream_obs.discharge_cusecs or downstream_obs.downstream_discharge_cusecs or 0) if downstream_obs else None

        # Get downstream asset alert status
        downstream_alert = session.execute(
            select(WaterOperationalAlert.severity).where(
                WaterOperationalAlert.asset_id == segment.downstream_asset_id,
                WaterOperationalAlert.status.in_(["NEW", "ACKNOWLEDGED", "INVESTIGATING"]),
            ).order_by(WaterOperationalAlert.severity.desc()).limit(1)
        ).scalar_one_or_none()

        downstream_asset = session.get(WaterAsset, segment.downstream_asset_id)

        chain.append(DownstreamSegmentResponse(
            segment_id=segment.id,
            river_name=segment.river_name,
            upstream_asset_id=segment.upstream_asset_id,
            upstream_asset_name=asset.canonical_name,
            downstream_asset_id=segment.downstream_asset_id,
            downstream_asset_name=downstream_asset.canonical_name if downstream_asset else f"Asset {segment.downstream_asset_id}",
            distance_km=float(segment.distance_km) if segment.distance_km else None,
            segment_order=segment.segment_order,
            travel_time_min_hours=tt_min,
            travel_time_max_hours=tt_max,
            travel_time_expected_hours=tt_expected,
            travel_time_confidence=tt_confidence,
            arrival_window_min=arrival_min,
            arrival_window_expected=arrival_expected,
            arrival_window_max=arrival_max,
            downstream_level_ft=downstream_level,
            downstream_discharge=downstream_discharge,
            downstream_alert_severity=downstream_alert,
            segment_status=segment.status,
            data_source=segment.source_name,
        ))

        if segment.distance_km:
            total_distance += float(segment.distance_km)
        if tt_expected:
            total_travel_time += tt_expected

        current_asset_id = segment.downstream_asset_id

    # Determine river name from first segment
    river_name = chain[0].river_name if chain else "Unknown"

    return DownstreamImpactResponse(
        source_asset_id=asset_id,
        source_asset_name=asset.canonical_name,
        source_release_cusecs=release_cusecs,
        source_level_ft=source_level,
        river_name=river_name,
        chain=chain,
        total_distance_km=total_distance if total_distance > 0 else None,
        total_travel_time_hours=total_travel_time if total_travel_time > 0 else None,
    )


# ─── FFD/PMD FLOOD BULLETINS ───────────────────────────────────────────────

class FFDObservationResponse(BaseModel):
    id: int
    asset_id: Optional[int]
    station_name: str
    river_name: Optional[str]
    observed_at: date
    gauge_level_ft: Optional[float]
    discharge_cusecs: Optional[float]
    flood_status: str
    forecast_trend: str
    forecast_range: Optional[str] = None
    historical_max: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FFDIngestResponse(BaseModel):
    date: str
    parsed: int
    stored: int
    skipped: int
    error: Optional[str] = None


@router.get("/operational/ffd", response_model=List[FFDObservationResponse])
async def list_ffd_observations(
    asset_id: Optional[int] = None,
    target_date: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """List FFD/PMD flood bulletin observations."""
    query = select(WaterFFDObservation)
    
    if asset_id:
        query = query.where(WaterFFDObservation.asset_id == asset_id)
    
    if target_date:
        from datetime import date as date_type
        try:
            d = date_type.fromisoformat(target_date)
            query = query.where(WaterFFDObservation.observed_at == d)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    obs = session.execute(
        query.order_by(desc(WaterFFDObservation.observed_at), WaterFFDObservation.station_name)
    ).scalars().all()
    
    return [
        FFDObservationResponse(
            id=o.id,
            asset_id=o.asset_id,
            station_name=o.station_name,
            river_name=o.river_name,
            observed_at=o.observed_at,
            gauge_level_ft=float(o.gauge_level_ft) if o.gauge_level_ft else None,
            discharge_cusecs=float(o.discharge_cusecs) if o.discharge_cusecs else None,
            flood_status=o.flood_status,
            forecast_trend=o.forecast_trend,
            historical_max=float(o.historical_max) if hasattr(o, 'historical_max') and o.historical_max else None,
            created_at=o.created_at,
        )
        for o in obs
    ]


@router.post("/operational/ffd/ingest", response_model=FFDIngestResponse)
async def trigger_ffd_ingest(
    target_date: Optional[str] = None,
):
    """Trigger FFD/PMD bulletin ingestion."""
    from infrastructure.ingestion.ffd_ingest import ingest_ffd_bulletin
    from datetime import date as date_type
    
    d = None
    if target_date:
        try:
            d = date_type.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    result = ingest_ffd_bulletin(d)
    return FFDIngestResponse(**result)


class IRSAIngestResponse(BaseModel):
    success: bool
    message: str
    observations: int = 0
    url: Optional[str] = None


class FFDMarkerResponse(BaseModel):
    id: int
    station_name: str
    river_name: Optional[str]
    flood_status: str
    discharge_cusecs: Optional[float]
    gauge_level_ft: Optional[float]
    observed_at: str
    latitude: Optional[float]
    longitude: Optional[float]
    asset_id: Optional[int]


@router.get("/operational/ffd/markers", response_model=List[FFDMarkerResponse])
async def get_ffd_markers(session: Session = Depends(get_session)):
    """Get latest FFD observations as map markers for the flood map layer."""
    from infrastructure.db.models import WaterFFDObservation, WaterAsset

    subq = (
        select(
            WaterFFDObservation.station_name,
            func.max(WaterFFDObservation.id).label("max_id"),
        )
        .group_by(WaterFFDObservation.station_name)
        .subquery()
    )

    rows = session.execute(
        select(WaterFFDObservation, WaterAsset.latitude, WaterAsset.longitude)
        .join(subq, WaterFFDObservation.id == subq.c.max_id)
        .outerjoin(WaterAsset, WaterFFDObservation.asset_id == WaterAsset.id)
        .order_by(WaterFFDObservation.station_name)
    ).all()

    return [
        FFDMarkerResponse(
            id=ffd.id,
            station_name=ffd.station_name,
            river_name=ffd.river_name,
            flood_status=ffd.flood_status or "NORMAL",
            discharge_cusecs=float(ffd.discharge_cusecs) if ffd.discharge_cusecs else None,
            gauge_level_ft=float(ffd.gauge_level_ft) if ffd.gauge_level_ft else None,
            observed_at=str(ffd.observed_at),
            latitude=float(lat) if lat else None,
            longitude=float(lng) if lng else None,
            asset_id=ffd.asset_id,
        )
        for ffd, lat, lng in rows
    ]


@router.post("/operational/irsa/ingest", response_model=IRSAIngestResponse)
async def trigger_irsa_ingest(target_date: Optional[str] = None):
    """Trigger IRSA daily PDF ingestion. Downloads + parses + stores observations."""
    from infrastructure.ingestion.irsa_downloader import auto_ingest_irsa
    from datetime import date as date_type

    d = None
    if target_date:
        try:
            d = date_type.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        result = auto_ingest_irsa(d)
        return IRSAIngestResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IRSA ingestion failed: {str(e)}")
