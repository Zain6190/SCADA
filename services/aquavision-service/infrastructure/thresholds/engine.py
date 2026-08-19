# infrastructure/thresholds/engine.py
# Threshold evaluation engine: reads observations, evaluates rules, generates alerts.
#
# Supported threshold types:
#   1. ABSOLUTE - value exceeds fixed threshold (level > 1552 ft)
#   2. RATE_OF_CHANGE - value changes too fast (rise > 1 ft in 6h)
#   3. RELATIONSHIP - combined condition (high inflow + low outflow + rising level)
#   4. DATA_STALENESS - no observation within expected window
#   5. FORECAST - model prediction exceeds threshold
#
# Phase 2C: Added auto-clear, escalation timers, cooldown dedup,
#           FALSE_OR_INVALID_DATA wiring, notification dispatcher.

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import Session

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import (
    WaterAsset, WaterAssetThreshold, WaterObservation,
    WaterOperationalAlert, WaterAlertAuditLog, WaterFFDObservation,
)

logger = logging.getLogger("aquavision.thresholds")

# ─── Severity Levels ────────────────────────────────────────────────────────
SEVERITY_NORMAL = "NORMAL"
SEVERITY_WATCH = "WATCH"
SEVERITY_ADVISORY = "ADVISORY"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"

SEVERITY_ORDER = {
    SEVERITY_NORMAL: 0,
    SEVERITY_WATCH: 1,
    SEVERITY_ADVISORY: 2,
    SEVERITY_WARNING: 3,
    SEVERITY_CRITICAL: 4,
}

# ─── Alert Statuses ─────────────────────────────────────────────────────────
STATUS_NEW = "NEW"
STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
STATUS_INVESTIGATING = "INVESTIGATING"
STATUS_ESCALATED = "ESCALATED"
STATUS_ACTION_REQUIRED = "ACTION_REQUIRED"
STATUS_WAITING_VERIFICATION = "WAITING_FOR_VERIFICATION"
STATUS_RESOLVED = "RESOLVED"
STATUS_FALSE_INVALID = "FALSE_OR_INVALID_DATA"

# ─── Phase 2C: Escalation & Cooldown Config ────────────────────────────────
ESCALATION_HOURS = 6  # Auto-escalate if unacknowledged after 6 hours
COOLDOWN_HOURS = {
    SEVERITY_WATCH: 6,
    SEVERITY_ADVISORY: 2,
    SEVERITY_WARNING: 0.5,  # 30 minutes
    SEVERITY_CRITICAL: 0.17,  # 10 minutes
}


# ─── Alert Types ────────────────────────────────────────────────────────────
class AlertType:
    HIGH_INFLOW = "HIGH_INFLOW"
    RISING_LEVEL = "RISING_LEVEL"
    RAPID_RISE = "RAPID_RISE"
    LEVEL_ABOVE_WARNING = "LEVEL_ABOVE_WARNING"
    LEVEL_ABOVE_DANGER = "LEVEL_ABOVE_DANGER"
    LEVEL_ABOVE_CRITICAL = "LEVEL_ABOVE_CRITICAL"
    HIGH_INFLOW_LOW_OUTFLOW = "HIGH_INFLOW_LOW_OUTFLOW"
    FORECAST_DANGER_24H = "FORECAST_DANGER_24H"
    FORECAST_DANGER_7D = "FORECAST_DANGER_7D"
    DATA_STALE = "DATA_STALE"
    HIGH_DISCHARGE = "HIGH_DISCHARGE"
    FFD_FLOOD_HIGH = "FFD_FLOOD_HIGH"
    FFD_FLOOD_MEDIUM = "FFD_FLOOD_MEDIUM"
    FFD_FLOOD_LOW = "FFD_FLOOD_LOW"


# Clear condition maps: which alert types auto-clear when condition normalizes.
# Maps alert_type -> (field_to_check, threshold_field, direction)
# "below" means clear when value < threshold
CLEAR_CONDITIONS = {
    AlertType.LEVEL_ABOVE_WARNING: ("water_level_ft", "warning_level_ft", "below"),
    AlertType.LEVEL_ABOVE_DANGER: ("water_level_ft", "danger_level_ft", "below"),
    AlertType.LEVEL_ABOVE_CRITICAL: ("water_level_ft", "critical_level_ft", "below"),
    AlertType.HIGH_INFLOW: ("inflow_cusecs", "warning_inflow", "below"),
    AlertType.HIGH_DISCHARGE: ("discharge_cusecs", "warning_discharge", "below"),
}


def _higher_severity(a: str, b: str) -> str:
    """Return the higher of two severity levels."""
    if SEVERITY_ORDER.get(a, 0) >= SEVERITY_ORDER.get(b, 0):
        return a
    return b


def _get_threshold(db: Session, asset_id: int) -> Optional[WaterAssetThreshold]:
    """Load threshold rules for an asset."""
    return db.execute(
        select(WaterAssetThreshold).where(
            WaterAssetThreshold.asset_id == asset_id,
            WaterAssetThreshold.is_active == True,
        )
    ).scalar_one_or_none()


def _get_latest_observation(db: Session, asset_id: int) -> Optional[WaterObservation]:
    """Get the most recent observation for an asset."""
    return db.execute(
        select(WaterObservation)
        .where(WaterObservation.asset_id == asset_id)
        .order_by(desc(WaterObservation.observed_at))
        .limit(1)
    ).scalar_one_or_none()


def _get_previous_observation(db: Session, asset_id: int, before: datetime) -> Optional[WaterObservation]:
    """Get the observation immediately before a given time."""
    return db.execute(
        select(WaterObservation)
        .where(
            WaterObservation.asset_id == asset_id,
            WaterObservation.observed_at < before,
        )
        .order_by(desc(WaterObservation.observed_at))
        .limit(1)
    ).scalar_one_or_none()


def _get_observation_n_hours_ago(db: Session, asset_id: int, current_time: datetime, hours: int) -> Optional[WaterObservation]:
    """Get the closest observation N hours before current_time."""
    from datetime import timezone
    # Make current_time offset-naive for comparison if needed
    if current_time.tzinfo is not None:
        current_time = current_time.replace(tzinfo=None)
    target = current_time - timedelta(hours=hours)
    return db.execute(
        select(WaterObservation)
        .where(
            WaterObservation.asset_id == asset_id,
            WaterObservation.observed_at <= target,
        )
        .order_by(desc(WaterObservation.observed_at))
        .limit(1)
    ).scalar_one_or_none()


def _open_alert_exists(db: Session, asset_id: int, alert_type: str) -> bool:
    """Check if there's already an open (non-resolved) alert of this type for this asset."""
    result = db.execute(
        select(func.count(WaterOperationalAlert.id)).where(
            WaterOperationalAlert.asset_id == asset_id,
            WaterOperationalAlert.alert_type == alert_type,
            WaterOperationalAlert.status.notin_([STATUS_RESOLVED, STATUS_FALSE_INVALID]),
        )
    ).scalar()
    return result > 0


def _create_alert(
    db: Session,
    asset_id: int,
    alert_type: str,
    severity: str,
    message: str,
    triggered_value: float = None,
    threshold_value: float = None,
    observation_id: int = None,
    reading_level_ft: float = None,
    reading_inflow_cusecs: float = None,
    reading_outflow_cusecs: float = None,
    reading_discharge_cusecs: float = None,
    rate_of_change_ft_6h: float = None,
    alert_source: str = "RULE",
    rule_version: str = None,
    model_version: str = None,
) -> WaterOperationalAlert:
    """Create a new operational alert and log it."""
    
    # Calculate downstream impact if inflow data available
    impact_summary = None
    impact_population = None
    impact_bridges = None
    impact_hospitals = None
    impact_furthest = None
    impact_arrival_hours = None
    
    flow_cusecs = reading_inflow_cusecs or reading_discharge_cusecs
    if flow_cusecs and flow_cusecs > 100000:
        try:
            from infrastructure.impact.downstream_engine import DownstreamImpactEngine
            from infrastructure.db.engine import engine as sa_engine
            from datetime import datetime as dt
            
            impact_engine = DownstreamImpactEngine(sa_engine)
            result = impact_engine.calculate(
                source_asset_id=asset_id,
                release_flow_cusecs=flow_cusecs,
                release_time=dt.now(timezone.utc),
            )
            if result.segments:
                impact_summary = f"{result.total_population_exposed:,} people, {result.total_bridges} bridges, {result.total_hospitals} hospitals"
                impact_population = result.total_population_exposed
                impact_bridges = result.total_bridges
                impact_hospitals = result.total_hospitals
                impact_furthest = result.furthest_asset
                impact_arrival_hours = result.total_travel_hours
                logger.info(f"Downstream impact calculated: {impact_summary}")
        except Exception as e:
            logger.warning(f"Failed to calculate downstream impact: {e}")
    
    alert = WaterOperationalAlert(
        asset_id=asset_id,
        alert_type=alert_type,
        severity=severity,
        observation_id=observation_id,
        triggered_value=triggered_value,
        threshold_value=threshold_value,
        message=message,
        reading_level_ft=reading_level_ft,
        reading_inflow_cusecs=reading_inflow_cusecs,
        reading_outflow_cusecs=reading_outflow_cusecs,
        reading_discharge_cusecs=reading_discharge_cusecs,
        rate_of_change_ft_6h=rate_of_change_ft_6h,
        status=STATUS_NEW,
        alert_source=alert_source,
        alert_domain="OPERATIONAL",
        rule_version=rule_version or "threshold_v1.0",
        model_version=model_version,
        downstream_impact_summary=impact_summary,
        downstream_population_exposed=impact_population,
        downstream_bridges_at_risk=impact_bridges,
        downstream_hospitals_at_risk=impact_hospitals,
        downstream_furthest_asset=impact_furthest,
        downstream_furthest_arrival_hours=impact_arrival_hours,
    )
    db.add(alert)
    db.flush()

    # Audit log
    audit = WaterAlertAuditLog(
        alert_id=alert.id,
        action="CREATED",
        performed_by="SYSTEM",
        old_status=None,
        new_status=STATUS_NEW,
        notes=f"Alert generated by threshold engine: {message}",
    )
    db.add(audit)
    db.flush()

    logger.info(f"Alert created: {severity} | {alert_type} | Asset {asset_id} | {message}")
    return alert


# ─── Phase 2C: Auto-Clear ──────────────────────────────────────────────────

def _auto_clear_resolved_alerts(db: Session, asset_id: int, obs: WaterObservation, threshold: WaterAssetThreshold) -> List[str]:
    """Check open alerts and auto-resolve those whose condition has normalized.
    
    Returns list of alert_types that were auto-cleared.
    """
    cleared = []
    open_alerts = db.execute(
        select(WaterOperationalAlert).where(
            WaterOperationalAlert.asset_id == asset_id,
            WaterOperationalAlert.status.notin_([STATUS_RESOLVED, STATUS_FALSE_INVALID]),
        )
    ).scalars().all()

    for alert in open_alerts:
        condition = CLEAR_CONDITIONS.get(alert.alert_type)
        if not condition:
            continue

        obs_field, thresh_field, direction = condition
        obs_val = getattr(obs, obs_field, None)
        thresh_val = getattr(threshold, thresh_field, None)

        if obs_val is None or thresh_val is None:
            continue

        should_clear = False
        if direction == "below" and float(obs_val) < float(thresh_val):
            should_clear = True

        if should_clear:
            old_status = alert.status
            alert.status = STATUS_RESOLVED
            alert.resolved_at = datetime.utcnow()

            audit = WaterAlertAuditLog(
                alert_id=alert.id,
                action="AUTO_CLEARED",
                performed_by="SYSTEM",
                old_status=old_status,
                new_status=STATUS_RESOLVED,
                notes=f"Condition normalized: {obs_field}={obs_val} is now below threshold {thresh_val}",
            )
            db.add(audit)
            cleared.append(alert.alert_type)
            logger.info(f"Auto-cleared: {alert.alert_type} on asset {asset_id}")

    return cleared


# ─── Phase 2C: Escalation Timers ───────────────────────────────────────────

def _check_escalation(db: Session) -> List[WaterOperationalAlert]:
    """Auto-escalate alerts that have been NEW for longer than ESCALATION_HOURS.
    
    Returns list of escalated alerts.
    """
    cutoff = datetime.utcnow() - timedelta(hours=ESCALATION_HOURS)
    escalated = []

    stale_alerts = db.execute(
        select(WaterOperationalAlert).where(
            WaterOperationalAlert.status == STATUS_NEW,
            WaterOperationalAlert.created_at < cutoff,
        )
    ).scalars().all()

    for alert in stale_alerts:
        old_status = alert.status
        alert.status = STATUS_ESCALATED
        alert.escalated_at = datetime.utcnow()

        audit = WaterAlertAuditLog(
            alert_id=alert.id,
            action="ESCALATED",
            performed_by="SYSTEM",
            old_status=old_status,
            new_status=STATUS_ESCALATED,
            notes=f"Auto-escalated after {ESCALATION_HOURS}h without acknowledgment",
        )
        db.add(audit)
        escalated.append(alert)
        logger.info(f"Auto-escalated alert {alert.id}: {alert.alert_type} on asset {alert.asset_id}")

    return escalated


# ─── Phase 2C: Cooldown Dedup ──────────────────────────────────────────────

def _cooldown_allows(db: Session, asset_id: int, alert_type: str, severity: str) -> bool:
    """Check if cooldown period has elapsed since last alert of same type+severity.
    
    Returns True if we should create a new alert (cooldown expired or no prior alert).
    """
    cooldown_hours = COOLDOWN_HOURS.get(severity, 0)
    if cooldown_hours <= 0:
        return True

    cutoff = datetime.utcnow() - timedelta(hours=cooldown_hours)
    recent = db.execute(
        select(func.count(WaterOperationalAlert.id)).where(
            WaterOperationalAlert.asset_id == asset_id,
            WaterOperationalAlert.alert_type == alert_type,
            WaterOperationalAlert.created_at >= cutoff,
        )
    ).scalar()

    return recent == 0


# ─── Phase 2C: FALSE_OR_INVALID_DATA ───────────────────────────────────────

def _wire_false_invalid_data(db: Session, asset_id: int) -> List[str]:
    """Check for quarantined observations and mark corresponding alerts as FALSE_OR_INVALID_DATA.
    
    Returns list of alert_types that were marked false/invalid.
    """
    from infrastructure.db.models import WaterObservationQuarantine
    marked = []

    # Get open alerts for this asset
    open_alerts = db.execute(
        select(WaterOperationalAlert).where(
            WaterOperationalAlert.asset_id == asset_id,
            WaterOperationalAlert.status.notin_([STATUS_RESOLVED, STATUS_FALSE_INVALID]),
        )
    ).scalars().all()

    for alert in open_alerts:
        if not alert.observation_id:
            continue

        # Check if this observation was quarantined
        quarantine = db.execute(
            select(WaterObservationQuarantine).where(
                WaterObservationQuarantine.observation_id == alert.observation_id,
            )
        ).scalar_one_or_none()

        if quarantine:
            old_status = alert.status
            alert.status = STATUS_FALSE_INVALID

            audit = WaterAlertAuditLog(
                alert_id=alert.id,
                action="FALSE_OR_INVALID_DATA",
                performed_by="SYSTEM",
                old_status=old_status,
                new_status=STATUS_FALSE_INVALID,
                notes=f"Observation {alert.observation_id} quarantined: {quarantine.reason}",
            )
            db.add(audit)
            marked.append(alert.alert_type)
            logger.info(f"Marked FALSE_OR_INVALID_DATA: alert {alert.id} (obs {alert.observation_id} quarantined)")

    return marked


# ─── Phase 2C: Notification Dispatcher ──────────────────────────────────────

def _dispatch_notifications(db: Session, alerts: List[WaterOperationalAlert]) -> None:
    """Dispatch notifications for critical/warning alerts.
    
    Creates NotificationDelivery records with dedup keys.
    Delivery is QUEUED — actual sending is handled by the notification worker.
    """
    from infrastructure.db.models import NotificationDelivery

    for alert in alerts:
        if alert.severity not in (SEVERITY_WARNING, SEVERITY_CRITICAL):
            continue

        asset = db.get(WaterAsset, alert.asset_id)
        asset_name = asset.canonical_name if asset else f"Asset {alert.asset_id}"

        # Default recipient for now — in production, look up from preferences
        recipient = "ops-team@ibcp.gov.pk"
        channel = "EMAIL"

        # Dedup key: same alert_type + asset within 1 hour = same notification
        dedup_key = f"alert:{alert.alert_type}:{alert.asset_id}:{alert.severity}"

        # Check if already delivered recently (1 hour cooldown)
        cutoff = datetime.utcnow() - timedelta(hours=1)
        recent = db.execute(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.dedup_key == dedup_key,
                NotificationDelivery.recipient == recipient,
                NotificationDelivery.created_at >= cutoff,
            )
        ).scalar()

        if recent > 0:
            continue

        delivery = NotificationDelivery(
            alert_key=alert.alert_type,
            recipient=recipient,
            channel=channel,
            dedup_key=dedup_key,
            status="QUEUED",
            created_at=datetime.utcnow(),
        )
        db.add(delivery)
        logger.info(f"Notification queued: {channel} to {recipient} for {alert.alert_type} on {asset_name}")

    db.flush()


# ─── Threshold Evaluation Functions ─────────────────────────────────────────

def _eval_absolute_level(
    db: Session, asset: WaterAsset, threshold: WaterAssetThreshold, obs: WaterObservation
) -> List[Tuple[str, str, str, float, float]]:
    """Check absolute level thresholds. Returns list of (alert_type, severity, message, triggered, threshold_val)."""
    alerts = []
    level = obs.water_level_ft
    if level is None:
        return alerts

    if threshold.critical_level_ft and level >= threshold.critical_level_ft:
        alerts.append((
            AlertType.LEVEL_ABOVE_CRITICAL,
            SEVERITY_CRITICAL,
            f"{asset.canonical_name}: Level {level:.2f} ft exceeds CRITICAL ({threshold.critical_level_ft:.2f} ft)",
            level, threshold.critical_level_ft,
        ))
    elif threshold.danger_level_ft and level >= threshold.danger_level_ft:
        alerts.append((
            AlertType.LEVEL_ABOVE_DANGER,
            SEVERITY_CRITICAL,
            f"{asset.canonical_name}: Level {level:.2f} ft exceeds DANGER ({threshold.danger_level_ft:.2f} ft)",
            level, threshold.danger_level_ft,
        ))
    elif threshold.warning_level_ft and level >= threshold.warning_level_ft:
        alerts.append((
            AlertType.LEVEL_ABOVE_WARNING,
            SEVERITY_WARNING,
            f"{asset.canonical_name}: Level {level:.2f} ft exceeds WARNING ({threshold.warning_level_ft:.2f} ft)",
            level, threshold.warning_level_ft,
        ))

    return alerts


def _eval_absolute_inflow(
    db: Session, asset: WaterAsset, threshold: WaterAssetThreshold, obs: WaterObservation
) -> List[Tuple[str, str, str, float, float]]:
    """Check absolute inflow thresholds."""
    alerts = []
    inflow = obs.inflow_cusecs
    if inflow is None:
        return alerts

    if threshold.danger_inflow and inflow >= threshold.danger_inflow:
        alerts.append((
            AlertType.HIGH_INFLOW,
            SEVERITY_WARNING,
            f"{asset.canonical_name}: Inflow {inflow:,.0f} cusecs exceeds DANGER ({threshold.danger_inflow:,.0f} cusecs)",
            inflow, threshold.danger_inflow,
        ))
    elif threshold.warning_inflow and inflow >= threshold.warning_inflow:
        alerts.append((
            AlertType.HIGH_INFLOW,
            SEVERITY_WATCH,
            f"{asset.canonical_name}: Inflow {inflow:,.0f} cusecs exceeds WARNING ({threshold.warning_inflow:,.0f} cusecs)",
            inflow, threshold.warning_inflow,
        ))

    return alerts


def _eval_absolute_discharge(
    db: Session, asset: WaterAsset, threshold: WaterAssetThreshold, obs: WaterObservation
) -> List[Tuple[str, str, str, float, float]]:
    """Check absolute discharge thresholds (river stations)."""
    alerts = []
    discharge = obs.discharge_cusecs
    if discharge is None:
        return alerts

    if threshold.danger_discharge and discharge >= threshold.danger_discharge:
        alerts.append((
            AlertType.HIGH_DISCHARGE,
            SEVERITY_CRITICAL,
            f"{asset.canonical_name}: Discharge {discharge:,.0f} cusecs exceeds DANGER ({threshold.danger_discharge:,.0f} cusecs)",
            discharge, threshold.danger_discharge,
        ))
    elif threshold.warning_discharge and discharge >= threshold.warning_discharge:
        alerts.append((
            AlertType.HIGH_DISCHARGE,
            SEVERITY_WARNING,
            f"{asset.canonical_name}: Discharge {discharge:,.0f} cusecs exceeds WARNING ({threshold.warning_discharge:,.0f} cusecs)",
            discharge, threshold.warning_discharge,
        ))

    return alerts


def _eval_rate_of_change(
    db: Session, asset: WaterAsset, threshold: WaterAssetThreshold, obs: WaterObservation
) -> List[Tuple[str, str, str, float, float]]:
    """Check rate-of-change thresholds (level rise in 6 hours)."""
    alerts = []
    if obs.water_level_ft is None:
        return alerts

    prev = _get_observation_n_hours_ago(db, asset.id, obs.observed_at, 6)
    if prev is None or prev.water_level_ft is None:
        return alerts

    rise_ft = float(obs.water_level_ft) - float(prev.water_level_ft)
    if rise_ft <= 0:
        return alerts  # only trigger on rises, not falls

    if threshold.level_rise_critical_6h and rise_ft >= threshold.level_rise_critical_6h:
        alerts.append((
            AlertType.RAPID_RISE,
            SEVERITY_CRITICAL,
            f"{asset.canonical_name}: Level rose {rise_ft:.2f} ft in 6h (CRITICAL threshold: {threshold.level_rise_critical_6h:.2f} ft)",
            rise_ft, threshold.level_rise_critical_6h,
        ))
    elif threshold.level_rise_warning_6h and rise_ft >= threshold.level_rise_warning_6h:
        alerts.append((
            AlertType.RAPID_RISE,
            SEVERITY_WARNING,
            f"{asset.canonical_name}: Level rose {rise_ft:.2f} ft in 6h (WARNING threshold: {threshold.level_rise_warning_6h:.2f} ft)",
            rise_ft, threshold.level_rise_warning_6h,
        ))
    elif threshold.level_rise_watch_6h and rise_ft >= threshold.level_rise_watch_6h:
        alerts.append((
            AlertType.RISING_LEVEL,
            SEVERITY_WATCH,
            f"{asset.canonical_name}: Level rose {rise_ft:.2f} ft in 6h (WATCH threshold: {threshold.level_rise_watch_6h:.2f} ft)",
            rise_ft, threshold.level_rise_watch_6h,
        ))

    return alerts


def _eval_relationship(
    db: Session, asset: WaterAsset, threshold: WaterAssetThreshold, obs: WaterObservation
) -> List[Tuple[str, str, str, float, float]]:
    """Check relationship thresholds (combined conditions)."""
    alerts = []
    if obs.inflow_cusecs is None or obs.outflow_cusecs is None or obs.water_level_ft is None:
        return alerts

    inflow = float(obs.inflow_cusecs)
    outflow = float(obs.outflow_cusecs)
    level = float(obs.water_level_ft)

    # Get previous level for trend
    prev = _get_observation_n_hours_ago(db, asset.id, obs.observed_at, 6)
    if prev is None or prev.water_level_ft is None:
        return alerts

    rising = level > float(prev.water_level_ft)
    high_inflow = threshold.warning_inflow and inflow >= threshold.warning_inflow
    low_outflow = outflow < inflow * 0.9  # outflow is significantly less than inflow

    if high_inflow and low_outflow and rising:
        alerts.append((
            AlertType.HIGH_INFLOW_LOW_OUTFLOW,
            SEVERITY_WARNING,
            f"{asset.canonical_name}: High inflow ({inflow:,.0f}) + low outflow ({outflow:,.0f}) + rising level ({level:.2f} ft). Water is accumulating.",
            inflow, threshold.warning_inflow or 0,
        ))

    return alerts


def _eval_staleness(
    db: Session, asset: WaterAsset, threshold: WaterAssetThreshold, obs: WaterObservation
) -> List[Tuple[str, str, str, float, float]]:
    """Check if data is stale (no observation within expected window)."""
    alerts = []
    now = datetime.utcnow()
    obs_time = obs.observed_at
    # Handle timezone-aware datetimes
    if obs_time.tzinfo is not None:
        from datetime import timezone
        now = now.replace(tzinfo=timezone.utc)
    hours_since = (now - obs_time).total_seconds() / 3600

    if hours_since >= threshold.stale_hours_critical:
        alerts.append((
            AlertType.DATA_STALE,
            SEVERITY_CRITICAL,
            f"{asset.canonical_name}: No data for {hours_since:.0f} hours (CRITICAL threshold: {threshold.stale_hours_critical}h)",
            hours_since, threshold.stale_hours_critical,
        ))
    elif hours_since >= threshold.stale_hours_warning:
        alerts.append((
            AlertType.DATA_STALE,
            SEVERITY_WATCH,
            f"{asset.canonical_name}: No data for {hours_since:.0f} hours (WARNING threshold: {threshold.stale_hours_warning}h)",
            hours_since, threshold.stale_hours_warning,
        ))

    return alerts


def _eval_ffd_status(
    db: Session, asset: WaterAsset
) -> List[Tuple[str, str, str, float, float]]:
    """Check FFD flood status for the asset.
    
    FFD flood_status mapping:
      HIGH / VERY_HIGH / EXCEPTIONALLY_HIGH → CRITICAL alert
      MEDIUM → WARNING alert
      LOW → WATCH alert (informational)
      BELOW_LOW → no alert
    """
    from sqlalchemy import cast, Date
    alerts = []

    ffd_obs = db.execute(
        select(WaterFFDObservation)
        .where(WaterFFDObservation.asset_id == asset.id)
        .order_by(desc(WaterFFDObservation.observed_at))
        .limit(1)
    ).scalar_one_or_none()

    if not ffd_obs or not ffd_obs.flood_status:
        return alerts

    status = ffd_obs.flood_status.upper()
    inflow = ffd_obs.discharge_cusecs or 0

    if status in ("HIGH", "VERY_HIGH", "EXCEPTIONALLY_HIGH"):
        alerts.append((
            AlertType.FFD_FLOOD_HIGH,
            SEVERITY_CRITICAL,
            f"{asset.canonical_name}: FFD reports {status} flood status (inflow: {inflow:,.0f} cusecs)",
            inflow, 0,
        ))
    elif status == "MEDIUM":
        alerts.append((
            AlertType.FFD_FLOOD_MEDIUM,
            SEVERITY_WARNING,
            f"{asset.canonical_name}: FFD reports MEDIUM flood status (inflow: {inflow:,.0f} cusecs)",
            inflow, 0,
        ))
    elif status == "LOW":
        alerts.append((
            AlertType.FFD_FLOOD_LOW,
            SEVERITY_WATCH,
            f"{asset.canonical_name}: FFD reports LOW flood status (inflow: {inflow:,.0f} cusecs)",
            inflow, 0,
        ))

    return alerts


# ─── Main Evaluation Function ───────────────────────────────────────────────

def evaluate_asset(db: Session, asset_id: int) -> List[WaterOperationalAlert]:
    """Evaluate all threshold rules for a single asset. Returns list of new alerts.
    
    Phase 2C: Now includes auto-clear, cooldown dedup, FALSE_OR_INVALID_DATA
    wiring, escalation, and notification dispatch.
    """
    asset = db.get(WaterAsset, asset_id)
    if not asset:
        logger.warning(f"Asset {asset_id} not found")
        return []

    threshold = _get_threshold(db, asset_id)
    if not threshold:
        logger.debug(f"No threshold rules for asset {asset.canonical_name}, skipping")
        return []

    obs = _get_latest_observation(db, asset_id)
    if not obs:
        logger.debug(f"No observations for asset {asset.canonical_name}, skipping")
        return []

    # Phase 2C: Auto-clear resolved alerts first
    _auto_clear_resolved_alerts(db, asset_id, obs, threshold)

    # Phase 2C: Mark FALSE_OR_INVALID_DATA for quarantined observations
    _wire_false_invalid_data(db, asset_id)

    # Collect all triggered conditions
    triggered = []
    triggered.extend(_eval_absolute_level(db, asset, threshold, obs))
    triggered.extend(_eval_absolute_inflow(db, asset, threshold, obs))
    triggered.extend(_eval_absolute_discharge(db, asset, threshold, obs))
    triggered.extend(_eval_rate_of_change(db, asset, threshold, obs))
    triggered.extend(_eval_relationship(db, asset, threshold, obs))
    triggered.extend(_eval_staleness(db, asset, threshold, obs))
    triggered.extend(_eval_ffd_status(db, asset))

    # Create alerts with cooldown dedup
    new_alerts = []
    for alert_type, severity, message, triggered_val, threshold_val in triggered:
        if _open_alert_exists(db, asset_id, alert_type):
            continue
        if not _cooldown_allows(db, asset_id, alert_type, severity):
            logger.debug(f"Cooldown active for {alert_type}/{severity} on asset {asset_id}, skipping")
            continue

        alert_source = "FFD" if alert_type.startswith("FFD_") else "RULE"
        alert = _create_alert(
            db=db,
            asset_id=asset_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            triggered_value=triggered_val,
            threshold_value=threshold_val,
            observation_id=obs.id,
            reading_level_ft=obs.water_level_ft,
            reading_inflow_cusecs=obs.inflow_cusecs,
            reading_outflow_cusecs=obs.outflow_cusecs,
            reading_discharge_cusecs=obs.discharge_cusecs,
            alert_source=alert_source,
        )
        new_alerts.append(alert)

    # Phase 2C: Dispatch notifications for new critical/warning alerts
    if new_alerts:
        _dispatch_notifications(db, new_alerts)

    db.commit()
    return new_alerts


def evaluate_all_assets(db: Session = None) -> dict:
    """Evaluate thresholds for all active assets. Called after each ingestion cycle.
    
    Phase 2C: Also runs escalation checks across all assets.
    """
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        assets = db.execute(
            select(WaterAsset).where(WaterAsset.is_active == True)
        ).scalars().all()

        total_alerts = 0
        results = {}

        for asset in assets:
            alerts = evaluate_asset(db, asset.id)
            if alerts:
                results[asset.canonical_name] = [
                    {"type": a.alert_type, "severity": a.severity, "message": a.message}
                    for a in alerts
                ]
                total_alerts += len(alerts)

        # Phase 2C: Check escalations across all assets
        escalated = _check_escalation(db)

        logger.info(
            f"Threshold evaluation complete: {len(assets)} assets checked, "
            f"{total_alerts} new alerts, {len(escalated)} escalations"
        )
        return {
            "assets_checked": len(assets),
            "new_alerts": total_alerts,
            "escalations": len(escalated),
            "alerts": results,
        }
    finally:
        if close_session:
            db.close()


# ─── Convenience: Wire to IRSA Ingestion ───────────────────────────────────

def run_threshold_engine_after_ingestion() -> dict:
    """Called automatically after IRSA ingestion completes."""
    logger.info("Running threshold engine after ingestion...")
    return evaluate_all_assets()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = evaluate_all_assets()
    print(f"\nThreshold evaluation result:")
    print(f"  Assets checked: {result['assets_checked']}")
    print(f"  New alerts: {result['new_alerts']}")
    for asset, alerts in result["alerts"].items():
        print(f"\n  {asset}:")
        for a in alerts:
            print(f"    [{a['severity']}] {a['type']}: {a['message']}")
