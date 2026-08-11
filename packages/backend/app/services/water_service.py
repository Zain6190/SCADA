# packages/backend/app/services/water_service.py
# AquaVision AI - PostgreSQL service layer (SQLAlchemy ORM -> PostGIS).
from datetime import date, timedelta, datetime, UTC
from typing import List, Optional
import random

from sqlalchemy import select, func, and_, desc

from app.core.database import SessionLocal
from app.models import db as orm
from app.models.water import (
    Region, WaterIndicator, WaterIndicatorCreate, WaterPrediction,
    WaterAlert, WaterReport, WaterThreshold, WaterOverview, MapStation,
    AssetReading, AssetSummary, AssetOperationalNote,
)

# ---------------------------------------------------------------------------
# Access levels for role-based response filtering (backend-enforced).
#
# LEVEL_VIEWER  - core operational status only (WAI, severity, reservoir,
#                 storage %, timestamp, source). No analysis internals.
# LEVEL_ANALYST - viewer + analysis fields (rainfall, anomaly, ET).
# LEVEL_OPERATOR- analyst fields + operational write/ack context.
# LEVEL_MANAGER - adds provenance/quality fields (source IDs, flags, parsers).
#
# Restricted fields are REMOVED in the serializer, never merely hidden in the
# frontend.
# ---------------------------------------------------------------------------
LEVEL_VIEWER = "VIEWER"
LEVEL_ANALYST = "ANALYST"
LEVEL_OPERATOR = "OPERATOR"
LEVEL_MANAGER = "MANAGER"


def access_level(permissions: Optional[list]) -> str:
    """Map a permission set to an access level. Highest wins."""
    perms = set(permissions or [])
    if "AQUAVISION_MANAGE_DATA" in perms:
        return LEVEL_MANAGER
    if "AQUAVISION_ACKNOWLEDGE_ALERT" in perms or "AQUAVISION_ADD_NOTE" in perms:
        return LEVEL_OPERATOR
    if "AQUAVISION_ANALYZE" in perms:
        return LEVEL_ANALYST
    return LEVEL_VIEWER


def filter_indicators(indicators: List, permissions: Optional[list]) -> List[dict]:
    """Backend role-based filtering of indicator payloads by access level."""
    level = access_level(permissions)
    return [_filtered_idict(i, level) for i in indicators]
    """Map a permission set to an access level. Highest wins."""
    perms = set(permissions or [])
    if "AQUAVISION_MANAGE_DATA" in perms:
        return LEVEL_MANAGER
    if "AQUAVISION_ACKNOWLEDGE_ALERT" in perms or "AQUAVISION_ADD_NOTE" in perms:
        return LEVEL_OPERATOR
    if "AQUAVISION_ANALYZE" in perms:
        return LEVEL_ANALYST
    return LEVEL_VIEWER


_VIEWER_FIELDS = {
    "id", "region_id", "week_start_date", "week_number", "year",
    "wai_score", "severity", "surface_water_area_km2",
    "surface_water_change_pct", "created_at", "data_source_version",
    # provenance / status / freshness are pure status info (safe for all
    # readers); analysis internals (rainfall/ET/anomaly) remain analyst+ only.
    "data_status", "data_quality", "data_provider", "wai_model_version",
    "source_observed_at", "last_validated_at",
}
_ANALYST_FIELDS = _VIEWER_FIELDS | {
    "rainfall_mm_30day", "rainfall_anomaly", "et_mm_8day", "et_anomaly",
}


def _filtered_idict(i: orm.WaterIndicator, level: str) -> dict:
    """Serialize a WaterIndicator, removing fields the access level may not see."""
    allowed = _ANALYST_FIELDS if level in (LEVEL_ANALYST, LEVEL_OPERATOR, LEVEL_MANAGER) else _VIEWER_FIELDS
    return {k: v for k, v in {
        "id": i.id,
        "region_id": i.region_id,
        "week_start_date": i.week_start_date,
        "week_number": i.week_number,
        "year": i.year,
        "surface_water_area_km2": float(i.surface_water_area_km2) if i.surface_water_area_km2 is not None else None,
        "surface_water_change_pct": float(i.surface_water_change_pct) if i.surface_water_change_pct is not None else None,
        "rainfall_mm_30day": float(i.rainfall_mm_30day) if i.rainfall_mm_30day is not None else None,
        "rainfall_anomaly": float(i.rainfall_anomaly) if i.rainfall_anomaly is not None else None,
        "et_mm_8day": float(i.et_mm_8day) if i.et_mm_8day is not None else None,
        "et_anomaly": float(i.et_anomaly) if i.et_anomaly is not None else None,
        "wai_score": float(i.wai_score),
        "severity": i.severity,
        "data_source_version": i.data_source_version,
        "data_status": i.data_status,
        "data_quality": i.data_quality,
        "data_provider": i.data_provider,
        "wai_model_version": i.wai_model_version,
        "source_observed_at": i.source_observed_at,
        "last_validated_at": i.last_validated_at,
        "created_at": i.created_at,
    }.items() if k in allowed}


def classify_severity(wai: float) -> str:
    if wai < 25:
        return "Critical"
    if wai < 40:
        return "Severe"
    if wai < 55:
        return "Stressed"
    if wai < 70:
        return "Moderate"
    return "Normal"


DISTRICT_IDS = list(range(5, 19))  # 5..18


def _hydrate_region(r: orm.Region) -> Region:
    return Region(id=r.id, name=r.name, code=r.code, type=r.type,
                  parent_region_id=r.parent_region_id)


def _hydrate_indicator(i: orm.WaterIndicator) -> WaterIndicator:
    return WaterIndicator(
        id=i.id, region_id=i.region_id, week_start_date=i.week_start_date,
        week_number=i.week_number, year=i.year,
        surface_water_area_km2=float(i.surface_water_area_km2) if i.surface_water_area_km2 is not None else None,
        surface_water_change_pct=float(i.surface_water_change_pct) if i.surface_water_change_pct is not None else None,
        rainfall_mm_30day=float(i.rainfall_mm_30day) if i.rainfall_mm_30day is not None else None,
        rainfall_anomaly=float(i.rainfall_anomaly) if i.rainfall_anomaly is not None else None,
        et_mm_8day=float(i.et_mm_8day) if i.et_mm_8day is not None else None,
        et_anomaly=float(i.et_anomaly) if i.et_anomaly is not None else None,
        wai_score=float(i.wai_score), severity=i.severity,
        data_source_version=i.data_source_version,
        data_status=i.data_status, data_quality=i.data_quality,
        data_provider=i.data_provider, wai_model_version=i.wai_model_version,
        source_observed_at=i.source_observed_at, last_validated_at=i.last_validated_at,
        created_at=i.created_at,
    )


def _hydrate_prediction(p: orm.WaterPrediction) -> WaterPrediction:
    return WaterPrediction(
        id=p.id, region_id=p.region_id, target_week_start_date=p.target_week_start_date,
        model_type=p.model_type, model_version=p.model_version,
        predicted_severity=p.predicted_severity,
        predicted_wai_score=float(p.predicted_wai_score) if p.predicted_wai_score is not None else None,
        confidence=float(p.confidence) if p.confidence is not None else None,
        trained_on_week_start=p.trained_on_week_start,
        dataset_version=p.dataset_version,
        feature_importance_hash=p.feature_importance_hash,
        created_at=p.created_at,
    )


def _hydrate_alert(a: orm.WaterAlert) -> WaterAlert:
    return WaterAlert(
        id=a.id, region_id=a.region_id, week_start_date=a.week_start_date,
        alert_type=a.alert_type, severity=a.severity,
        wai_score=float(a.wai_score) if a.wai_score is not None else None,
        rainfall_anomaly=float(a.rainfall_anomaly) if a.rainfall_anomaly is not None else None,
        et_anomaly=float(a.et_anomaly) if a.et_anomaly is not None else None,
        surface_water_change_pct=float(a.surface_water_change_pct) if a.surface_water_change_pct is not None else None,
        status=a.status, assigned_to_user_id=str(a.assigned_to_user_id) if a.assigned_to_user_id else None,
        created_at=a.created_at, acknowledged_at=a.acknowledged_at,
        resolved_at=a.resolved_at, notes=a.notes,
        acknowledged_by_user_id=str(a.acknowledged_by_user_id) if a.acknowledged_by_user_id else None,
        initial_assessment=a.initial_assessment,
        estimated_response_time=a.estimated_response_time,
        investigation_notes=a.investigation_notes,
        action_taken=a.action_taken,
        action_result=a.action_result,
        action_time=a.action_time,
        evidence_refs=list(a.evidence_refs or []),
        escalated_to=a.escalated_to,
        escalated_at=a.escalated_at,
        verified_by_user_id=str(a.verified_by_user_id) if a.verified_by_user_id else None,
        verified_at=a.verified_at,
        resolved_by_user_id=str(a.resolved_by_user_id) if a.resolved_by_user_id else None,
    )


def _hydrate_report(r: orm.WaterReport) -> WaterReport:
    return WaterReport(
        id=r.id, week_start_date=r.week_start_date, title=r.title, scope=r.scope,
        region_id=r.region_id, file_path=r.file_path,
        generated_by_user_id=str(r.generated_by_user_id) if r.generated_by_user_id else None,
        generated_at=r.generated_at, status=r.status,
    )


def _hydrate_threshold(t: orm.WaterThreshold) -> WaterThreshold:
    return WaterThreshold(
        id=t.id, threshold_name=t.threshold_name, value=float(t.value),
        description=t.description, updated_at=t.updated_at,
    )


def _hydrate_asset_reading(r: orm.AssetTelemetry) -> AssetReading:
    def f(v):
        return float(v) if v is not None else None
    return AssetReading(
        id=r.id, asset_id=r.asset_id, recorded_at=r.recorded_at,
        reservoir_level_m=f(r.reservoir_level_m), storage_pct=f(r.storage_pct),
        inflow_cumecs=f(r.inflow_cumecs), outflow_cumecs=f(r.outflow_cumecs),
        discharge_cumecs=f(r.discharge_cumecs),
        data_status=r.data_status, source=r.source,
    )


def _hydrate_asset_note(n: orm.AssetOperationalNote) -> AssetOperationalNote:
    return AssetOperationalNote(
        id=n.id, asset_id=n.asset_id, note=n.note,
        created_by_user_id=str(n.created_by_user_id), created_at=n.created_at,
    )


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------
def get_regions(region_type: Optional[str] = None,
                parent_region_id: Optional[int] = None,
                scope: Optional[List[int]] = None) -> List[Region]:
    with SessionLocal() as db:
        q = select(orm.Region)
        if region_type:
            q = q.where(orm.Region.type == region_type)
        if parent_region_id is not None:
            q = q.where(orm.Region.parent_region_id == parent_region_id)
        if scope:
            q = q.where(orm.Region.id.in_(scope))
        rows = db.execute(q.order_by(orm.Region.id)).scalars().all()
        return [_hydrate_region(r) for r in rows]


def get_region(region_id: int) -> Optional[Region]:
    with SessionLocal() as db:
        r = db.get(orm.Region, region_id)
        return _hydrate_region(r) if r else None


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------
def _region_filter(q, region_ids):
    """If a user has a restricted geo scope, narrow the query to those regions.
    Empty scope == national (no filter)."""
    if region_ids:
        q = q.where(orm.WaterIndicator.region_id.in_(region_ids))
    return q


def get_indicators(region_id: Optional[int] = None, severity: Optional[str] = None,
                   week_start_date: Optional[date] = None, limit: int = 100,
                   scope: Optional[List[int]] = None) -> List[WaterIndicator]:
    with SessionLocal() as db:
        q = select(orm.WaterIndicator)
        if region_id is not None:
            q = q.where(orm.WaterIndicator.region_id == region_id)
        if scope:
            q = q.where(orm.WaterIndicator.region_id.in_(scope))
        if severity:
            q = q.where(orm.WaterIndicator.severity == severity)
        if week_start_date:
            q = q.where(orm.WaterIndicator.week_start_date == week_start_date)
        q = q.order_by(orm.WaterIndicator.week_start_date.desc(),
                       orm.WaterIndicator.region_id.desc()).limit(limit)
        rows = db.execute(q).scalars().all()
        return [_hydrate_indicator(r) for r in rows]


def get_latest_indicators(scope: Optional[List[int]] = None) -> List[WaterIndicator]:
    """One indicator per district for the latest week present in DB."""
    with SessionLocal() as db:
        sub_q = select(orm.WaterIndicator.region_id,
                       func.max(orm.WaterIndicator.week_start_date).label("max_week"))
        if scope:
            sub_q = sub_q.where(orm.WaterIndicator.region_id.in_(scope))
        sub = sub_q.group_by(orm.WaterIndicator.region_id).subquery()
        q = (select(orm.WaterIndicator)
             .join(sub, and_(
                 orm.WaterIndicator.region_id == sub.c.region_id,
                 orm.WaterIndicator.week_start_date == sub.c.max_week,
             )))
        rows = db.execute(q).scalars().all()
        return [_hydrate_indicator(r) for r in rows]


def latest_indicator(region_id: int) -> Optional[WaterIndicator]:
    with SessionLocal() as db:
        q = (select(orm.WaterIndicator)
             .where(orm.WaterIndicator.region_id == region_id)
             .order_by(orm.WaterIndicator.week_start_date.desc())
             .limit(1))
        r = db.execute(q).scalar_one_or_none()
        return _hydrate_indicator(r) if r else None


def upsert_indicator(data: WaterIndicatorCreate) -> WaterIndicator:
    with SessionLocal() as db:
        existing = db.execute(
            select(orm.WaterIndicator).where(
                orm.WaterIndicator.region_id == data.region_id,
                orm.WaterIndicator.week_start_date == data.week_start_date,
            )
        ).scalar_one_or_none()
        iso = data.week_start_date.isocalendar()
        if existing is None:
            existing = orm.WaterIndicator(
                region_id=data.region_id,
                week_start_date=data.week_start_date,
                week_number=iso[1], year=iso[0],
            )
            db.add(existing)
        existing.surface_water_area_km2 = data.surface_water_area_km2
        existing.surface_water_change_pct = data.surface_water_change_pct
        existing.rainfall_mm_30day = data.rainfall_mm_30day
        existing.rainfall_anomaly = data.rainfall_anomaly
        existing.et_mm_8day = data.et_mm_8day
        existing.et_anomaly = data.et_anomaly
        existing.wai_score = data.wai_score
        existing.severity = classify_severity(data.wai_score)
        existing.data_source_version = data.data_source_version
        existing.data_status = data.data_status
        existing.data_quality = data.data_quality
        existing.data_provider = data.data_provider
        existing.wai_model_version = data.wai_model_version
        existing.source_observed_at = data.source_observed_at
        existing.last_validated_at = data.last_validated_at
        db.commit()
        db.refresh(existing)
        return _hydrate_indicator(existing)


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------
def get_predictions(region_id: Optional[int] = None, scope: Optional[List[int]] = None) -> List[WaterPrediction]:
    with SessionLocal() as db:
        q = select(orm.WaterPrediction)
        if region_id is not None:
            q = q.where(orm.WaterPrediction.region_id == region_id)
        if scope:
            q = q.where(orm.WaterPrediction.region_id.in_(scope))
        q = q.order_by(orm.WaterPrediction.target_week_start_date.desc())
        rows = db.execute(q).scalars().all()
        return [_hydrate_prediction(r) for r in rows]


# ---------------------------------------------------------------------------
# Assets & operational telemetry
# ---------------------------------------------------------------------------
def _asset_scope_ids(scope: Optional[List[int]]) -> Optional[List[int]]:
    """Assets hang off provinces. Resolve a district-level scope up to the
    province ids an operator actually holds so asset filters match. Returns
    None for national scope (all assets)."""
    if not scope:
        return None
    with SessionLocal() as db:
        region_rows = db.execute(
            select(orm.Region.id, orm.Region.parent_region_id)
            .where(orm.Region.id.in_(scope))
        ).all()
        parents = {r.parent_region_id for r in region_rows if r.parent_region_id is not None}
        # Include self + any parent provinces
        return sorted(set(scope).union(parents))


def get_assets(scope: Optional[List[int]] = None) -> List[AssetSummary]:
    """All assets visible to a user, each joined with its latest telemetry."""
    scoped_regions = _asset_scope_ids(scope)
    with SessionLocal() as db:
        q = select(orm.Asset)
        if scoped_regions is not None:
            q = q.where(orm.Asset.region_id.in_(scoped_regions))
        q = q.order_by(orm.Asset.asset_type, orm.Asset.name)
        assets = db.execute(q).scalars().all()

        latest: dict[int, orm.AssetTelemetry] = {}
        if assets:
            ids = [a.id for a in assets]
            rows = db.execute(
                select(orm.AssetTelemetry)
                .where(orm.AssetTelemetry.asset_id.in_(ids))
                .order_by(orm.AssetTelemetry.recorded_at.desc())
            ).scalars().all()
            seen: set[int] = set()
            for r in rows:
                if r.asset_id not in seen:
                    latest[r.asset_id] = r
                    seen.add(r.asset_id)

        return [
            AssetSummary(
                id=a.id, name=a.name, asset_type=a.asset_type,
                region_id=a.region_id,
                latest=_hydrate_asset_reading(latest[a.id]) if a.id in latest else None,
            )
            for a in assets
        ]


def get_asset_readings(asset_id: int, limit: int = 60) -> Optional[List[AssetReading]]:
    """Recent telemetry series for an asset (empty list if asset exists but no readings)."""
    with SessionLocal() as db:
        asset = db.get(orm.Asset, asset_id)
        if asset is None:
            return None
        rows = db.execute(
            select(orm.AssetTelemetry)
            .where(orm.AssetTelemetry.asset_id == asset_id)
            .order_by(orm.AssetTelemetry.recorded_at.desc())
            .limit(limit)
        ).scalars().all()
        return [_hydrate_asset_reading(r) for r in reversed(rows)]


def asset_in_scope(asset_id: int, allowed_regions: List[int]) -> bool:
    """True when the asset's province is within a user's allowed region set.

    Assets are anchored to provinces; the policy expands district-level grants
    up to their owning province so a district-scoped operator still sees the
    reservoirs / barrages that physically serve their district."""
    if not allowed_regions:
        return False
    with SessionLocal() as db:
        asset = db.get(orm.Asset, asset_id)
        if asset is None or asset.region_id is None:
            return False
        allowed = _asset_scope_ids(allowed_regions)
        return allowed is not None and asset.region_id in allowed


def get_asset_notes(asset_id: int) -> Optional[List[AssetOperationalNote]]:
    """Operator logbook entries for an asset (newest last)."""
    with SessionLocal() as db:
        if db.get(orm.Asset, asset_id) is None:
            return None
        rows = db.execute(
            select(orm.AssetOperationalNote)
            .where(orm.AssetOperationalNote.asset_id == asset_id)
            .order_by(orm.AssetOperationalNote.created_at.desc())
        ).scalars().all()
        return sorted([_hydrate_asset_note(n) for n in rows], key=lambda n: n.created_at)


def add_asset_note(asset_id: int, user_id: int, note: str) -> Optional[AssetOperationalNote]:
    """Append an operator note to an asset's operational logbook."""
    with SessionLocal() as db:
        if db.get(orm.Asset, asset_id) is None:
            return None
        entry = orm.AssetOperationalNote(
            asset_id=asset_id, note=note, created_by_user_id=user_id,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return _hydrate_asset_note(entry)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
def get_alerts(status: Optional[str] = None, severity: Optional[str] = None,
               region_id: Optional[int] = None, scope: Optional[List[int]] = None) -> List[WaterAlert]:
    with SessionLocal() as db:
        q = select(orm.WaterAlert)
        if status:
            q = q.where(orm.WaterAlert.status == status)
        if severity:
            q = q.where(orm.WaterAlert.severity == severity)
        if region_id is not None:
            q = q.where(orm.WaterAlert.region_id == region_id)
        if scope:
            q = q.where(orm.WaterAlert.region_id.in_(scope))
        q = q.order_by(orm.WaterAlert.created_at.desc())
        rows = db.execute(q).scalars().all()
        return [_hydrate_alert(r) for r in rows]


def get_alert(alert_id: int) -> Optional[WaterAlert]:
    with SessionLocal() as db:
        r = db.get(orm.WaterAlert, alert_id)
        return _hydrate_alert(r) if r else None


def update_alert(alert_id: int, status: Optional[str] = None,
                 assigned_to_user_id: Optional[str] = None,
                 notes: Optional[str] = None) -> Optional[WaterAlert]:
    with SessionLocal() as db:
        alert = db.get(orm.WaterAlert, alert_id)
        if alert is None:
            return None
        if status is not None:
            # State machine encloses the legacy PATCH path too (canonical).
            if not validate_alert_transition(alert.status, status):
                raise ValueError(
                    f"Illegal alert transition: {canonical_alert_status(alert.status)} -> {canonical_alert_status(status)}"
                )
            alert.status = canonical_alert_status(status)
            now = datetime.now(UTC)
            if canonical_alert_status(status) == "ACKNOWLEDGED":
                alert.acknowledged_at = alert.acknowledged_at or now
            if canonical_alert_status(status) == "RESOLVED":
                alert.resolved_at = alert.resolved_at or now
        if assigned_to_user_id is not None:
            alert.assigned_to_user_id = int(assigned_to_user_id)
        if notes is not None:
            alert.notes = notes
        db.commit()
        db.refresh(alert)
        return _hydrate_alert(alert)


# ---------------------------------------------------------------------------
# #12 SCADA alarm lifecycle (ISA-18.2 mindset)
#
# Acknowledgment captures responsibility; it never resolves an alert. Status
# transitions are enforced as a legal state machine so the operator must
# acknowledge -> investigate -> record action -> (supervisor verifies) ->
# resolve. Legacy seed statuses are normalised to their canonical values.
# ---------------------------------------------------------------------------
CANONICAL_STATUS = {
    "New": "ACTIVE", "Active": "ACTIVE", "ACTIVE": "ACTIVE",
    "Acknowledged": "ACKNOWLEDGED", "ACKNOWLEDGED": "ACKNOWLEDGED",
    "Resolved": "RESOLVED", "RESOLVED": "RESOLVED",
    "INVESTIGATING": "INVESTIGATING", "Investigated": "INVESTIGATING",
    "ACTION_REQUIRED": "ACTION_REQUIRED",
    "RESPONSE_COMPLETED": "RESPONSE_COMPLETED",
    "WAITING_FOR_VERIFICATION": "WAITING_FOR_VERIFICATION",
    "ESCALATED": "ESCALATED", "Escalated": "ESCALATED",
    "HANDOVER_REQUIRED": "HANDOVER_REQUIRED",
}
# Legal next states from each canonical state.
ALERT_TRANSITIONS = {
    "ACTIVE": {"ACKNOWLEDGED", "ESCALATED"},
    "ACKNOWLEDGED": {"INVESTIGATING", "ACTION_REQUIRED", "ESCALATED", "HANDOVER_REQUIRED",
                     "RESPONSE_COMPLETED", "WAITING_FOR_VERIFICATION"},
    "INVESTIGATING": {"ACTION_REQUIRED", "RESPONSE_COMPLETED", "ESCALATED",
                      "HANDOVER_REQUIRED", "WAITING_FOR_VERIFICATION"},
    "ACTION_REQUIRED": {"RESPONSE_COMPLETED", "ESCALATED", "WAITING_FOR_VERIFICATION"},
    "RESPONSE_COMPLETED": {"WAITING_FOR_VERIFICATION", "ESCALATED"},
    "WAITING_FOR_VERIFICATION": {"RESOLVED", "ESCALATED", "ACTION_REQUIRED"},
    "ESCALATED": {"INVESTIGATING", "ACTION_REQUIRED", "RESPONSE_COMPLETED",
                  "WAITING_FOR_VERIFICATION", "RESOLVED"},
    "HANDOVER_REQUIRED": {"INVESTIGATING", "ACTION_REQUIRED", "RESPONSE_COMPLETED",
                          "RESOLVED"},
    "RESOLVED": {"ACTIVE"},  # reopen
}

ALERT_STATUS_ORDER = [
    "ACTIVE", "ACKNOWLEDGED", "INVESTIGATING", "ACTION_REQUIRED",
    "RESPONSE_COMPLETED", "WAITING_FOR_VERIFICATION", "ESCALATED",
    "HANDOVER_REQUIRED", "RESOLVED",
]


def canonical_alert_status(status: Optional[str]) -> str:
    return CANONICAL_STATUS.get(status or "New", "ACTIVE")


def validate_alert_transition(current: str, target: str) -> bool:
    """Return True if moving current -> target is legal in the state machine."""
    from_s = canonical_alert_status(current)
    to_s = canonical_alert_status(target)
    if from_s == to_s:
        return True
    return to_s in ALERT_TRANSITIONS.get(from_s, set())


def _hydrate_alert_lifecycle(a: orm.WaterAlert, alert: WaterAlert) -> WaterAlert:
    """Backfill the #12 alert lifecycle fields into a hydrated DTO."""
    alert.acknowledged_by_user_id = str(a.acknowledged_by_user_id) if a.acknowledged_by_user_id else None
    alert.initial_assessment = a.initial_assessment
    alert.estimated_response_time = a.estimated_response_time
    alert.investigation_notes = a.investigation_notes
    alert.action_taken = a.action_taken
    alert.action_result = a.action_result
    alert.action_time = a.action_time
    alert.evidence_refs = list(a.evidence_refs or [])
    alert.escalated_to = a.escalated_to
    alert.escalated_at = a.escalated_at
    alert.verified_by_user_id = str(a.verified_by_user_id) if a.verified_by_user_id else None
    alert.verified_at = a.verified_at
    alert.resolved_by_user_id = str(a.resolved_by_user_id) if a.resolved_by_user_id else None
    return alert


def _lifecycle_transition(
    alert: orm.WaterAlert,
    target: str,
    *,
    actor_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> None:
    """Validate + apply a canonical status transition on the ORM row."""
    if not validate_alert_transition(alert.status, target):
        raise ValueError(f"Illegal alert transition: {canonical_alert_status(alert.status)} -> {target}")
    alert.status = canonical_alert_status(target)
    now = now or datetime.now(UTC)
    if canonical_alert_status(target) == "ACKNOWLEDGED":
        alert.acknowledged_at = alert.acknowledged_at or now
        alert.acknowledged_by_user_id = actor_id
    elif canonical_alert_status(target) in ("RESPONSE_COMPLETED", "RESOLVED"):
        if canonical_alert_status(target) == "RESOLVED":
            alert.resolved_at = alert.resolved_at or now
            alert.resolved_by_user_id = actor_id
    elif canonical_alert_status(target) == "ESCALATED":
        alert.escalated_at = alert.escalated_at or now


def acknowledge_alert(
    alert_id: int,
    user_id: int,
    initial_assessment: str,
    estimated_response_time: Optional[datetime] = None,
    notes: Optional[str] = None,
) -> Optional[WaterAlert]:
    """Operator accepts responsibility. NEVER resolves the alert."""
    with SessionLocal() as db:
        alert = db.get(orm.WaterAlert, alert_id)
        if alert is None:
            return None
        _lifecycle_transition(alert, "ACKNOWLEDGED", actor_id=user_id)
        alert.initial_assessment = initial_assessment
        if estimated_response_time is not None:
            alert.estimated_response_time = estimated_response_time
        if notes:
            alert.notes = notes
        db.commit()
        db.refresh(alert)
        return _hydrate_alert_lifecycle(alert, _hydrate_alert(alert))


def investigate_alert(
    alert_id: int,
    user_id: int,
    investigation_notes: str,
    target_status: Optional[str] = None,
) -> Optional[WaterAlert]:
    """Record SCADA/field findings; optionally move to ACTION_REQUIRED."""
    with SessionLocal() as db:
        alert = db.get(orm.WaterAlert, alert_id)
        if alert is None:
            return None
        target = canonical_alert_status(target_status or "INVESTIGATING")
        if target == "INVESTIGATING" and canonical_alert_status(alert.status) == "ACTIVE":
            target = "INVESTIGATING"
        # Allow moving to ACTION_REQUIRED from acknowledged/investigating.
        current = canonical_alert_status(alert.status)
        if target == "INVESTIGATING" and current == "ACKNOWLEDGED":
            _lifecycle_transition(alert, "INVESTIGATING", actor_id=user_id)
        elif target in ("ACTION_REQUIRED",) and current in ("ACKNOWLEDGED", "INVESTIGATING"):
            _lifecycle_transition(alert, "ACTION_REQUIRED", actor_id=user_id)
        else:
            _lifecycle_transition(alert, target, actor_id=user_id)
        alert.investigation_notes = investigation_notes
        db.commit()
        db.refresh(alert)
        return _hydrate_alert_lifecycle(alert, _hydrate_alert(alert))


def record_alert_response(
    alert_id: int,
    user_id: int,
    action_taken: str,
    action_result: Optional[str] = None,
    action_time: Optional[datetime] = None,
    evidence_refs: Optional[list] = None,
    notes: Optional[str] = None,
    require_verification: bool = True,
) -> Optional[WaterAlert]:
    """Record the approved operational action + outcome. Respond → either
    RESPONSE_COMPLETED (verification not required) or WAITING_FOR_VERIFICATION
    so a supervisor confirms it. Never self-resolves a critical event."""
    with SessionLocal() as db:
        alert = db.get(orm.WaterAlert, alert_id)
        if alert is None:
            return None
        # The state machine gates legality: an unacknowledged (ACTIVE) alert
        # cannot be responded to - responsibility must be captured first.
        target = "WAITING_FOR_VERIFICATION" if require_verification else "RESPONSE_COMPLETED"
        _lifecycle_transition(alert, target, actor_id=user_id)
        alert.action_taken = action_taken
        alert.action_result = action_result
        alert.action_time = action_time or datetime.now(UTC)
        if evidence_refs:
            alert.evidence_refs = list(evidence_refs)
        if notes:
            alert.notes = notes
        db.commit()
        db.refresh(alert)
        return _hydrate_alert_lifecycle(alert, _hydrate_alert(alert))


def verify_alert_response(
    alert_id: int,
    verifier_id: int,
    verified: bool = True,
) -> Optional[WaterAlert]:
    """Supervisor confirms the response (verified=True → RESOLVED) or sends it
    back for rework (verified=False → back to ACTION_REQUIRED)."""
    with SessionLocal() as db:
        alert = db.get(orm.WaterAlert, alert_id)
        if alert is None:
            return None
        current = canonical_alert_status(alert.status)
        if verified:
            if current != "WAITING_FOR_VERIFICATION":
                raise ValueError("Only a WAITING_FOR_VERIFICATION alert can be verified")
            alert.verified_by_user_id = verifier_id
            alert.verified_at = datetime.now(UTC)
            _lifecycle_transition(alert, "RESOLVED", actor_id=verifier_id, now=alert.verified_at)
        else:
            _lifecycle_transition(alert, "ACTION_REQUIRED", actor_id=verifier_id)
        db.commit()
        db.refresh(alert)
        return _hydrate_alert_lifecycle(alert, _hydrate_alert(alert))


def resolve_alert(
    alert_id: int,
    resolver_id: int,
    notes: Optional[str] = None,
) -> Optional[WaterAlert]:
    """Directly resolve an alert (supervisor's verification-materialised or an
    audit/emergency admin action). The state machine gates legality."""
    with SessionLocal() as db:
        alert = db.get(orm.WaterAlert, alert_id)
        if alert is None:
            return None
        _lifecycle_transition(alert, "RESOLVED", actor_id=resolver_id)
        if notes:
            alert.notes = notes
        db.commit()
        db.refresh(alert)
        return _hydrate_alert_lifecycle(alert, _hydrate_alert(alert))


def escalate_alert(
    alert_id: int,
    user_id: int,
    escalated_to: str,
    reason: Optional[str] = None,
) -> Optional[WaterAlert]:
    """Escalate over a threshold of authority. Chain: supervisor → regional →
    national. Status becomes ESCALATED (never cleared)."""
    with SessionLocal() as db:
        alert = db.get(orm.WaterAlert, alert_id)
        if alert is None:
            return None
        _lifecycle_transition(alert, "ESCALATED", actor_id=user_id)
        alert.escalated_to = escalated_to
        if reason:
            alert.notes = (alert.notes + "\n" if alert.notes else "") + f"ESCALATED: {reason}"
        db.commit()
        db.refresh(alert)
        return _hydrate_alert_lifecycle(alert, _hydrate_alert(alert))


def handover_alert(
    alert_id: int,
    user_id: int,
    notes: Optional[str] = None,
    assign_to_user_id: Optional[str] = None,
) -> Optional[WaterAlert]:
    """Shift handover: flag open items for the next operator."""
    with SessionLocal() as db:
        alert = db.get(orm.WaterAlert, alert_id)
        if alert is None:
            return None
        _lifecycle_transition(alert, "HANDOVER_REQUIRED", actor_id=user_id)
        if notes:
            alert.notes = (alert.notes + "\n" if alert.notes else "") + f"HANDOVER: {notes}"
        if assign_to_user_id:
            alert.assigned_to_user_id = int(assign_to_user_id)
        db.commit()
        db.refresh(alert)
        return _hydrate_alert_lifecycle(alert, _hydrate_alert(alert))
def get_thresholds() -> List[WaterThreshold]:
    with SessionLocal() as db:
        rows = db.execute(select(orm.WaterThreshold)).scalars().all()
        return [_hydrate_threshold(r) for r in rows]


def update_threshold(threshold_name: str, value: float) -> Optional[WaterThreshold]:
    with SessionLocal() as db:
        t = db.execute(select(orm.WaterThreshold).where(
            orm.WaterThreshold.threshold_name == threshold_name)).scalar_one_or_none()
        if t is None:
            return None
        t.value = value
        t.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(t)
        return _hydrate_threshold(t)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def get_reports(scope: Optional[str] = None) -> List[WaterReport]:
    with SessionLocal() as db:
        q = select(orm.WaterReport)
        if scope:
            q = q.where(orm.WaterReport.scope == scope)
        q = q.order_by(orm.WaterReport.week_start_date.desc())
        rows = db.execute(q).scalars().all()
        return [_hydrate_report(r) for r in rows]


def get_report(report_id: int) -> Optional[WaterReport]:
    with SessionLocal() as db:
        r = db.get(orm.WaterReport, report_id)
        return _hydrate_report(r) if r else None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
def get_overview(scope: Optional[List[int]] = None) -> WaterOverview:
    with SessionLocal() as db:
        sub_q = select(func.max(orm.WaterIndicator.week_start_date))
        latest_week = db.execute(sub_q).scalar()
        if latest_week is None:
            return WaterOverview(
                week_start_date=date.today(), regions_monitored=0, avg_wai_score=0.0,
                critical_regions=0, active_alerts=0, national_status="Unknown",
            )
        q = select(orm.WaterIndicator).where(orm.WaterIndicator.week_start_date == latest_week)
        if scope:
            q = q.where(orm.WaterIndicator.region_id.in_(scope))
        rows = db.execute(q).scalars().all()
        avg_wai = round(sum(float(r.wai_score) for r in rows) / len(rows), 1) if rows else 0.0
        critical = sum(1 for r in rows if r.severity in ("Critical", "Severe"))
        alert_q = select(func.count()).select_from(orm.WaterAlert).where(orm.WaterAlert.status == "New")
        if scope:
            alert_q = alert_q.where(orm.WaterAlert.region_id.in_(scope))
        active = db.execute(alert_q).scalar()
        return WaterOverview(
            week_start_date=latest_week,
            regions_monitored=len(rows),
            avg_wai_score=avg_wai,
            critical_regions=critical,
            active_alerts=int(active),
            national_status=classify_severity(avg_wai),
        )


def get_map_stations(scope: Optional[List[int]] = None) -> List[MapStation]:
    stations = []
    latest = get_latest_indicators(scope=scope)
    for ind in latest:
        region = get_region(ind.region_id)
        if region is None:
            continue
        stations.append(MapStation(
            region_id=region.id,
            name=region.name,
            lat=0.0, lon=0.0,  # centroids available from PostGIS; fill below
            wai_score=ind.wai_score,
            severity=ind.severity,
        ))
    # Fill centroid lat/lon from PostGIS ST_Centroid
    with SessionLocal() as db:
        rows = db.execute(
            select(orm.Region.id,
                   func.st_y(func.st_centroid(orm.Region.geom)).label("lat"),
                   func.st_x(func.st_centroid(orm.Region.geom)).label("lon"))
        ).all()
        centroids = {r.id: (float(r.lat), float(r.lon)) for r in rows}
    for s in stations:
        if s.region_id in centroids:
            s.lat, s.lon = centroids[s.region_id]
    return stations


# ---------------------------------------------------------------------------
# Seed sample water data (only if indicators table is empty)
# ---------------------------------------------------------------------------
def seed_if_empty() -> None:
    with SessionLocal() as db:
        count = db.execute(select(func.count()).select_from(orm.WaterIndicator)).scalar()

        if not count or count == 0:
            base_wai = {
                5: 58, 6: 42, 7: 50, 8: 30, 9: 45,
                10: 35, 11: 22, 12: 40, 13: 52,
                14: 48, 15: 55, 16: 62, 17: 33, 18: 47,
            }
            latest_week = date(2026, 7, 27)

            for i in range(1, 7):
                week_start = latest_week - timedelta(weeks=6 - i)
                iso = week_start.isocalendar()
                for region_id in DISTRICT_IDS:
                    drift = random.uniform(-4, 4)
                    wai = max(5, min(95, base_wai[region_id] + drift + (i - 6) * 1.5))
                    db.add(orm.WaterIndicator(
                        region_id=region_id, week_start_date=week_start,
                        week_number=iso[1], year=iso[0],
                        surface_water_area_km2=round(region_id * 12.5 + random.uniform(-30, 30), 2),
                        surface_water_change_pct=round(random.uniform(-6, 8), 2),
                        rainfall_mm_30day=round(random.uniform(0, 45), 1),
                        rainfall_anomaly=round(random.uniform(-55, 40), 1),
                        et_mm_8day=round(random.uniform(25, 70), 1),
                        et_anomaly=round(random.uniform(-15, 30), 1),
                        wai_score=round(wai, 1),
                        severity=classify_severity(wai),
                        data_source_version="GEE-JRC-2026.7",
                    ))
            db.commit()

        pred_count = db.execute(select(func.count()).select_from(orm.WaterPrediction)).scalar()
        if not pred_count or pred_count == 0:
            base_wai = {
                5: 58, 6: 42, 7: 50, 8: 30, 9: 45,
                10: 35, 11: 22, 12: 40, 13: 52,
                14: 48, 15: 55, 16: 62, 17: 33, 18: 47,
            }
            latest_week = date(2026, 7, 27)
            for region_id in DISTRICT_IDS:
                base = base_wai[region_id]
                for delta in (1, 2):
                    target = latest_week + timedelta(weeks=delta)
                    predicted = max(5, min(95, base + random.uniform(-6, 6)))
                    db.add(orm.WaterPrediction(
                        region_id=region_id, target_week_start_date=target,
                        model_type="RandomForest", model_version="rf-v1.3",
                        predicted_severity=classify_severity(predicted),
                        predicted_wai_score=round(predicted, 1),
                        confidence=round(random.uniform(0.72, 0.94), 2),
                    ))
            db.commit()

        alert_count = db.execute(select(func.count()).select_from(orm.WaterAlert)).scalar()
        if not alert_count or alert_count == 0:
            now = datetime.now(UTC)
            seed_alerts = [
                dict(region_id=11, week=date(2026, 7, 20), alert_type="WAI_CRITICAL", severity="Critical",
                     wai=22.0, rainfall=-48.0, et=22.0, sw=-5.2, status="New"),
                dict(region_id=8, week=date(2026, 7, 20), alert_type="WAI_SEVERE", severity="Severe",
                     wai=30.0, rainfall=-35.0, et=18.0, sw=-3.1, status="New"),
                dict(region_id=17, week=date(2026, 7, 13), alert_type="RAINFALL_DEFICIT", severity="Severe",
                     wai=33.0, rainfall=-55.0, et=15.0, sw=-2.0, status="Acknowledged",
                     ack=now - timedelta(days=2), assign="2", created=now - timedelta(days=3)),
                dict(region_id=10, week=date(2026, 7, 20), alert_type="HIGH_ET", severity="Warning",
                     wai=35.0, rainfall=-22.0, et=28.0, sw=-1.5, status="Acknowledged",
                     ack=now - timedelta(days=1), assign="3", created=now - timedelta(days=2)),
                dict(region_id=6, week=date(2026, 7, 6), alert_type="WAI_SEVERE", severity="Severe",
                     wai=38.0, rainfall=-30.0, et=14.0, sw=-2.8, status="Resolved",
                     ack=now - timedelta(days=5), resolved=now - timedelta(days=4),
                     created=now - timedelta(days=12), notes="Irrigation releases restored"),
            ]
            for s in seed_alerts:
                db.add(orm.WaterAlert(
                    region_id=s["region_id"], week_start_date=s["week"],
                    alert_type=s["alert_type"], severity=s["severity"],
                    wai_score=s["wai"], rainfall_anomaly=s["rainfall"],
                    et_anomaly=s["et"], surface_water_change_pct=s["sw"],
                    status=s["status"], assigned_to_user_id=int(s["assign"]) if s.get("assign") else None,
                    acknowledged_at=s.get("ack"), resolved_at=s.get("resolved"),
                    created_at=s.get("created", now), notes=s.get("notes"),
                ))
            db.commit()

        report_count = db.execute(select(func.count()).select_from(orm.WaterReport)).scalar()
        if not report_count or report_count == 0:
            for week, scope, title, uid in [
                (date(2026, 7, 20), "Province", "Weekly Water Availability Report - Sindh", "1"),
                (date(2026, 7, 13), "National", "National Water Stress Summary", "1"),
                (date(2026, 7, 6), "District", "Bahawalpur District Water Report", "2"),
            ]:
                db.add(orm.WaterReport(
                    week_start_date=week, title=title, scope=scope,
                    file_path=f"/reports/water/{week.isoformat()}.pdf",
                    generated_by_user_id=int(uid), status="Success",
                ))
            db.commit()

        telemetry_count = db.execute(select(func.count()).select_from(orm.AssetTelemetry)).scalar()
        if not telemetry_count or telemetry_count == 0:
            # Deterministic-ish operational profiles per asset type so the
            # operator console has a credible live series to render.
            profiles = {
                # asset_type: (level_m, storage_pct, inflow, outflow, discharge, noise)
                1: (455.0, 91.0, 7800.0, 6450.0, 6450.0, 22.0),   # Tarbela Dam (id 1)
                2: (378.0, 84.0, 5400.0, 4900.0, 4900.0, 18.0),   # Mangla Dam (id 2)
                3: (198.0, 62.0, 3200.0, 3050.0, 2990.0, 12.0),   # Chashma Barrage
                4: (196.5, 48.0, 4100.0, 3950.0, 9300.0, 15.0),   # Sukkur Barrage
                5: (3.2, None, None, None, 11800.0, 60.0),        # Indus River (flow)
                6: (4.1, None, None, None, 2400.0, 30.0),         # Jhelum River
                7: (None, None, None, None, 560.0, 8.0),          # Lower Chenab Canal
                8: (168.0, 38.0, 210.0, 175.0, 175.0, 6.0),       # Hub Dam
            }
            for asset_id in sorted(profiles):
                bl = profiles[asset_id]
                for i in range(24, 0, -1):  # last 24 hourly readings
                    t = datetime.now(UTC) - timedelta(hours=i)
                    jit = lambda span: round(random.uniform(-span, span), 2)
                    db.add(orm.AssetTelemetry(
                        asset_id=asset_id, recorded_at=t,
                        reservoir_level_m=round(bl[0] + jit(0.4), 2) if bl[0] is not None else None,
                        storage_pct=round(bl[1] + jit(1.2), 2) if bl[1] is not None else None,
                        inflow_cumecs=round(bl[2] + jit(bl[5]), 1) if bl[2] is not None else None,
                        outflow_cumecs=round(bl[3] + jit(bl[5]), 1) if bl[3] is not None else None,
                        discharge_cumecs=round(bl[4] + jit(bl[5]), 1) if bl[4] is not None else None,
                        data_status="Actual",
                        source="telemetry-live",
                    ))
            db.commit()

        note_count = db.execute(select(func.count()).select_from(orm.AssetOperationalNote)).scalar()
        if not note_count or note_count == 0:
            db.add_all([
                orm.AssetOperationalNote(
                    asset_id=4, note="Scheduled maintenance completed; gates aligned.",
                    created_by_user_id=3,
                ),
                orm.AssetOperationalNote(
                    asset_id=8, note="Level well below design; monitor inflow this week.",
                    created_by_user_id=3,
                ),
            ])
            db.commit()
