# infrastructure/thresholds/engine.py
# Threshold evaluation engine: reads observations, evaluates rules, generates alerts.
#
# Supported threshold types:
#   1. ABSOLUTE - value exceeds fixed threshold (level > 1552 ft)
#   2. RATE_OF_CHANGE - value changes too fast (rise > 1 ft in 6h)
#   3. RELATIONSHIP - combined condition (high inflow + low outflow + rising level)
#   4. DATA_STALENESS - no observation within expected window
#   5. FORECAST - model prediction exceeds threshold

import logging
from datetime import datetime, timedelta
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
    """Evaluate all threshold rules for a single asset. Returns list of new alerts."""
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

    # Collect all triggered conditions
    triggered = []
    triggered.extend(_eval_absolute_level(db, asset, threshold, obs))
    triggered.extend(_eval_absolute_inflow(db, asset, threshold, obs))
    triggered.extend(_eval_absolute_discharge(db, asset, threshold, obs))
    triggered.extend(_eval_rate_of_change(db, asset, threshold, obs))
    triggered.extend(_eval_relationship(db, asset, threshold, obs))
    triggered.extend(_eval_staleness(db, asset, threshold, obs))
    triggered.extend(_eval_ffd_status(db, asset))

    # Create alerts (skip if same type already open)
    new_alerts = []
    for alert_type, severity, message, triggered_val, threshold_val in triggered:
        if not _open_alert_exists(db, asset_id, alert_type):
            # Determine alert source from alert type
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

    db.commit()
    return new_alerts


def evaluate_all_assets(db: Session = None) -> dict:
    """Evaluate thresholds for all active assets. Called after each ingestion cycle."""
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

        logger.info(f"Threshold evaluation complete: {len(assets)} assets checked, {total_alerts} new alerts")
        return {
            "assets_checked": len(assets),
            "new_alerts": total_alerts,
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
