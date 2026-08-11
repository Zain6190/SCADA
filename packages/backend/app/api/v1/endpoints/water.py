# packages/backend/app/api/v1/endpoints/water.py
# AquaVision AI - REST endpoints for the water monitoring & early-warning system.
from datetime import date
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from typing import List, Optional

from app.models.water import (
    Region, WaterIndicator, WaterIndicatorCreate, WaterPrediction,
    WaterAlert, WaterAlertUpdate, WaterReport, WaterThreshold,
    WaterOverview, MapStation, AssetReading, AssetSummary,
    AssetOperationalNote, AssetOperationalNoteCreate,
    AlertAcknowledge, AlertInvestigate, AlertRespond, AlertEscalate,
    AlertVerify, AlertHandover,
)
from app.services import water_service, report_service
from app.core.rbac import require_permissions
from app.services.audit_service import log_security_event, write_audit

router = APIRouter()

READ = require_permissions("AQUAVISION_READ")
WRITE = require_permissions("AQUAVISION_MANAGE_DATA")
ACK = require_permissions("AQUAVISION_ACKNOWLEDGE_ALERT")
CONFIG = require_permissions("AQUAVISION_CONFIGURE")
ADD_NOTE = require_permissions("AQUAVISION_ADD_NOTE")
EXPORT = require_permissions("AQUAVISION_EXPORT")


def _scope(auth: dict) -> Optional[List[int]]:
    """Return the user's restricted region list, or None for national scope."""
    return auth["region_scope"]["region_ids"]


def _asset_in_scope(asset_id: int, allowed_regions: List[int]) -> bool:
    """True when the asset's province is within a user's allowed region set
    (assets hang off provinces; district scopes resolve to their provinces)."""
    return water_service.asset_in_scope(asset_id, allowed_regions)


@router.get("/overview", response_model=WaterOverview)
async def get_overview(auth: dict = Depends(READ)):
    """National dashboard KPIs for the latest week (scoped to the user's regions)."""
    return water_service.get_overview(scope=_scope(auth))


@router.get("/regions", response_model=List[Region])
async def get_regions(region_type: Optional[str] = Query(None, pattern="^(province|district|tehsil)$"),
                      auth: dict = Depends(READ)):
    """List administrative regions visible to the caller."""
    return water_service.get_regions(region_type=region_type, scope=_scope(auth))


@router.get("/map-data", response_model=List[MapStation])
async def get_map_data(auth: dict = Depends(READ)):
    """Per-district WAI + centroid coordinates for the live telemetry map."""
    return water_service.get_map_stations(scope=_scope(auth))


@router.get("/indicators")
async def get_indicators(
    region_id: Optional[int] = None,
    severity: Optional[str] = Query(None, pattern="^(Normal|Moderate|Stressed|Critical|Severe)$"),
    week_start_date: Optional[date] = None,
    limit: int = Query(100, ge=1, le=1000),
    auth: dict = Depends(READ),
):
    """Weekly water indicators, filtered to the caller's access level."""
    rows = water_service.get_indicators(
        region_id=region_id, severity=severity,
        week_start_date=week_start_date, limit=limit, scope=_scope(auth),
    )
    return water_service.filter_indicators(rows, auth["permissions"])


@router.get("/indicators/latest")
async def get_latest_indicators(auth: dict = Depends(READ)):
    """Latest week's indicators per district, filtered to access level."""
    rows = water_service.get_latest_indicators(scope=_scope(auth))
    return water_service.filter_indicators(rows, auth["permissions"])


@router.post("/indicators", response_model=WaterIndicator, status_code=201)
async def create_indicator(payload: WaterIndicatorCreate, auth: dict = Depends(WRITE)):
    """Ingest a new weekly indicator (ETL pipeline entry point)."""
    result = water_service.upsert_indicator(payload)
    write_audit(
        action="WATER_INDICATOR_UPSERTED",
        module="water",
        user_id=auth["user_id"],
        resource_type="water_indicator",
        resource_id=str(result.id),
        region_id=result.region_id,
        after_value={"region_id": result.region_id, "week_start_date": str(result.week_start_date)},
        result="success",
    )
    return result


@router.get("/predictions", response_model=List[WaterPrediction])
async def get_predictions(region_id: Optional[int] = None, auth: dict = Depends(READ)):
    """2-week-ahead water stress predictions."""
    return water_service.get_predictions(region_id=region_id, scope=_scope(auth))


@router.get("/assets", response_model=List[AssetSummary])
async def get_assets(region_id: Optional[int] = None, auth: dict = Depends(READ)):
    """Water assets visible to the caller, each with its latest telemetry.
    `region_id` narrows to a single district (used by the admin user-lifecycle
    asset picker)."""
    scope = auth["region_scope"]
    if region_id is not None and scope["restricted"] and scope["region_ids"] and region_id not in scope["region_ids"]:
        log_security_event(
            action="ACCESS_DENIED_OUT_OF_SCOPE",
            user_id=auth["user_id"],
            details={"resource_type": "water_asset_filter", "region_id": region_id},
        )
        raise HTTPException(status_code=403, detail="Region outside your access scope")
    if region_id is not None:
        return water_service.get_assets(scope=[region_id])
    return water_service.get_assets(scope=_scope(auth))


@router.get("/assets/{asset_id}/readings", response_model=List[AssetReading])
async def get_asset_readings(
    asset_id: int,
    limit: int = Query(60, ge=1, le=240),
    auth: dict = Depends(READ),
):
    """Recent telemetry series for a single asset (scoped)."""
    readings = water_service.get_asset_readings(asset_id, limit=limit)
    if readings is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    scope = auth["region_scope"]
    if scope["restricted"] and scope["region_ids"] and not _asset_in_scope(asset_id, scope["region_ids"]):
        log_security_event(
            action="ACCESS_DENIED_OUT_OF_SCOPE",
            user_id=auth["user_id"],
            details={"resource_type": "water_asset", "resource_id": str(asset_id)},
        )
        raise HTTPException(status_code=403, detail="Asset outside your access scope")
    return readings


@router.get("/assets/{asset_id}/notes", response_model=List[AssetOperationalNote])
async def get_asset_notes(asset_id: int, auth: dict = Depends(READ)):
    """Operator logbook notes for an asset (scoped)."""
    notes = water_service.get_asset_notes(asset_id)
    if notes is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    scope = auth["region_scope"]
    if scope["restricted"] and scope["region_ids"] and not _asset_in_scope(asset_id, scope["region_ids"]):
        raise HTTPException(status_code=403, detail="Asset outside your access scope")
    return notes


@router.post("/assets/{asset_id}/notes", response_model=AssetOperationalNote, status_code=201)
async def add_asset_note(
    asset_id: int,
    payload: AssetOperationalNoteCreate,
    auth: dict = Depends(ADD_NOTE),
):
    """Append an operator note to an asset's operational logbook."""
    scope = auth["region_scope"]
    if scope["restricted"] and scope["region_ids"] and not _asset_in_scope(asset_id, scope["region_ids"]):
        log_security_event(
            action="ACCESS_DENIED_OUT_OF_SCOPE",
            user_id=auth["user_id"],
            details={"resource_type": "water_asset", "resource_id": str(asset_id)},
        )
        raise HTTPException(status_code=403, detail="Asset outside your access scope")
    note = water_service.add_asset_note(asset_id, auth["user_id"], payload.note)
    if note is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    write_audit(
        action="OPERATIONAL_NOTE_ADDED",
        module="water",
        user_id=auth["user_id"],
        resource_type="water_asset",
        resource_id=str(asset_id),
        after_value={"note": payload.note},
        result="success",
    )
    return note


@router.get("/alerts", response_model=List[WaterAlert])
async def get_alerts(
    status: Optional[str] = Query(None, pattern="^(New|Acknowledged|Resolved)$"),
    severity: Optional[str] = Query(None, pattern="^(Critical|Severe|Warning)$"),
    region_id: Optional[int] = None,
    auth: dict = Depends(READ),
):
    """Water alerts; restricted to the caller's geographic scope."""
    return water_service.get_alerts(status=status, severity=severity,
                                    region_id=region_id, scope=_scope(auth))


@router.get("/alerts/{alert_id}", response_model=WaterAlert)
async def get_alert(alert_id: int, auth: dict = Depends(READ)):
    alert = water_service.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    scope = auth["region_scope"]
    if scope["restricted"] and scope["region_ids"] and alert.region_id not in scope["region_ids"]:
        raise HTTPException(status_code=403, detail="Region outside your access scope")
    return alert


@router.patch("/alerts/{alert_id}", response_model=WaterAlert)
async def update_alert(alert_id: int, payload: WaterAlertUpdate, auth: dict = Depends(ACK)):
    """Acknowledge / resolve an alert or assign it to a user."""
    alert = water_service.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    scope = auth["region_scope"]
    if scope["restricted"] and scope["region_ids"] and alert.region_id not in scope["region_ids"]:
        log_security_event(
            action="ACCESS_DENIED_OUT_OF_SCOPE",
            user_id=auth["user_id"],
            details={"resource_type": "water_alert", "resource_id": str(alert_id), "region_id": alert.region_id},
        )
        raise HTTPException(status_code=403, detail="Region outside your access scope")
    try:
        result = water_service.update_alert(
            alert_id,
            status=payload.status,
            assigned_to_user_id=payload.assigned_to_user_id,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    write_audit(
        action="ALERT_UPDATED",
        module="water",
        user_id=auth["user_id"],
        resource_type="water_alert",
        resource_id=str(alert_id),
        region_id=alert.region_id,
        before_value={"status": alert.status},
        after_value={"status": payload.status, "assigned_to_user_id": payload.assigned_to_user_id},
        result="success",
    )
    return result


def _alert_in_scope(alert: WaterAlert, auth: dict) -> bool:
    scope = auth["region_scope"]
    return not (scope["restricted"] and scope["region_ids"] and alert.region_id not in scope["region_ids"])


def _deny_out_of_scope(auth: dict, alert: WaterAlert) -> None:
    log_security_event(
        action="ACCESS_DENIED_OUT_OF_SCOPE",
        user_id=auth["user_id"],
        details={"resource_type": "water_alert", "resource_id": str(alert.id), "region_id": alert.region_id},
    )
    raise HTTPException(status_code=403, detail="Region outside your access scope")


def _lifecycle_route(alert_id: int, auth: dict, call, audit_action: str, after: dict):
    alert = water_service.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if not _alert_in_scope(alert, auth):
        _deny_out_of_scope(auth, alert)
    try:
        result = call(auth["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    write_audit(
        action=audit_action,
        module="water",
        user_id=auth["user_id"],
        resource_type="water_alert",
        resource_id=str(alert_id),
        region_id=alert.region_id,
        before_value={"status": alert.status},
        after_value={"status": result.status, **after} if result else after,
        result="success",
    )
    return result


OPS = require_permissions("AQUAVISION_ACKNOWLEDGE_ALERT", "AQUAVISION_ADD_NOTE")
VERIFY = require_permissions("AQUAVISION_VERIFY_RESPONSE")
RESOLVE = require_permissions("AQUAVISION_RESOLVE_ALERT")


@router.post("/alerts/{alert_id}/acknowledge", response_model=WaterAlert)
async def acknowledge_alert(alert_id: int, payload: AlertAcknowledge, auth: dict = Depends(ACK)):
    """Operator accepts responsibility for an alert (never resolves it)."""
    return _lifecycle_route(
        alert_id, auth,
        lambda uid: water_service.acknowledge_alert(
            alert_id, uid, payload.initial_assessment,
            payload.estimated_response_time, payload.notes,
        ),
        "ALERT_ACKNOWLEDGED",
        {"initial_assessment": payload.initial_assessment},
    )


@router.post("/alerts/{alert_id}/investigate", response_model=WaterAlert)
async def investigate_alert(alert_id: int, payload: AlertInvestigate, auth: dict = Depends(OPS)):
    """Record SCADA / field findings from the investigation."""
    return _lifecycle_route(
        alert_id, auth,
        lambda uid: water_service.investigate_alert(
            alert_id, uid, payload.investigation_notes, payload.status,
        ),
        "ALERT_INVESTIGATED",
        {"investigation_notes": payload.investigation_notes},
    )


@router.post("/alerts/{alert_id}/respond", response_model=WaterAlert)
async def record_response(alert_id: int, payload: AlertRespond, auth: dict = Depends(OPS)):
    """Record the approved operational action and its outcome. Unless the
    procedure allows direct clearance, the alert waits for supervisor
    verification rather than auto-resolving."""
    return _lifecycle_route(
        alert_id, auth,
        lambda uid: water_service.record_alert_response(
            alert_id, uid, payload.action_taken,
            payload.action_result, payload.action_time,
            payload.evidence_refs, payload.notes, payload.require_verification,
        ),
        "ALERT_RESPONSE_RECORDED",
        {"action_taken": payload.action_taken, "require_verification": payload.require_verification},
    )


@router.post("/alerts/{alert_id}/verify", response_model=WaterAlert)
async def verify_response(alert_id: int, payload: AlertVerify, auth: dict = Depends(VERIFY)):
    """Supervisor confirms the operator's response (→ RESOLVED) or sends it
    back for rework (verified=False → ACTION_REQUIRED)."""
    return _lifecycle_route(
        alert_id, auth,
        lambda uid: water_service.verify_alert_response(alert_id, uid, payload.verified),
        "ALERT_VERIFIED",
        {"verified": payload.verified},
    )


@router.post("/alerts/{alert_id}/resolve", response_model=WaterAlert)
async def resolve_alert(alert_id: int, auth: dict = Depends(RESOLVE)):
    """Supervisor / emergency-admin resolution of a responded alert."""
    return _lifecycle_route(
        alert_id, auth,
        lambda uid: water_service.resolve_alert(alert_id, uid),
        "ALERT_RESOLVED",
        {},
    )


@router.post("/alerts/{alert_id}/escalate", response_model=WaterAlert)
async def escalate_alert(alert_id: int, payload: AlertEscalate, auth: dict = Depends(ACK)):
    """Escalate over a threshold of authority (supervisor / regional / national)."""
    return _lifecycle_route(
        alert_id, auth,
        lambda uid: water_service.escalate_alert(alert_id, uid, payload.escalated_to, payload.reason),
        "ALERT_ESCALATED",
        {"escalated_to": payload.escalated_to},
    )


@router.post("/alerts/{alert_id}/handover", response_model=WaterAlert)
async def handover_alert(alert_id: int, payload: AlertHandover, auth: dict = Depends(OPS)):
    """End-of-shift handover: flag open items for the next operator."""
    return _lifecycle_route(
        alert_id, auth,
        lambda uid: water_service.handover_alert(
            alert_id, uid, payload.notes, payload.assign_to_user_id,
        ),
        "ALERT_HANDOVER",
        {"assign_to_user_id": payload.assign_to_user_id},
    )


@router.get("/thresholds", response_model=List[WaterThreshold], dependencies=[Depends(READ)])
async def get_thresholds():
    """Configurable alert / severity thresholds."""
    return water_service.get_thresholds()


@router.put("/thresholds/{threshold_name}", response_model=WaterThreshold)
async def update_threshold(threshold_name: str, value: float = Query(..., description="New threshold value"),
                           auth: dict = Depends(CONFIG)):
    """Update a threshold value (e.g. wai_critical_min)."""
    before = water_service.get_thresholds()
    threshold = water_service.update_threshold(threshold_name, value)
    if threshold is None:
        raise HTTPException(status_code=404, detail="Threshold not found")
    write_audit(
        action="THRESHOLD_UPDATED",
        module="water",
        user_id=auth["user_id"],
        resource_type="water_threshold",
        resource_id=threshold_name,
        before_value={"value": next((t.value for t in before if t.threshold_name == threshold_name), None)},
        after_value={"value": value},
        result="success",
    )
    return threshold


@router.get("/reports", response_model=List[WaterReport], dependencies=[Depends(READ)])
async def get_reports(scope: Optional[str] = Query(None, pattern="^(National|Province|District)$")):
    """Metadata for generated weekly water reports."""
    return water_service.get_reports(scope=scope)


# ---------------------------------------------------------------------------
# Exports (CSV / GeoJSON) - honour scope + access level.
# ---------------------------------------------------------------------------
@router.get("/export/indicators.csv")
async def export_indicators_csv(
    region_id: Optional[int] = None,
    severity: Optional[str] = Query(None, pattern="^(Normal|Moderate|Stressed|Critical|Severe)$"),
    week_start_date: Optional[date] = None,
    limit: int = Query(1000, ge=1, le=10000),
    auth: dict = Depends(EXPORT),
):
    """Access-filtered indicator export as a downloadable CSV file."""
    rows = water_service.get_indicators(
        region_id=region_id, severity=severity,
        week_start_date=week_start_date, limit=limit, scope=_scope(auth),
    )
    filtered = water_service.filter_indicators(rows, auth["permissions"])
    csv_text = report_service.indicators_to_csv(filtered)
    filename = f"aquavision_indicators_{date.today().isoformat()}.csv"
    return Response(
        content="\ufeff" + csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/indicators.geojson")
async def export_indicators_geojson(
    region_id: Optional[int] = None,
    severity: Optional[str] = Query(None, pattern="^(Normal|Moderate|Stressed|Critical|Severe)$"),
    week_start_date: Optional[date] = None,
    limit: int = Query(1000, ge=1, le=10000),
    auth: dict = Depends(EXPORT),
):
    """Access-filtered indicator export as GeoJSON points (region centroids)."""
    rows = water_service.get_indicators(
        region_id=region_id, severity=severity,
        week_start_date=week_start_date, limit=limit, scope=_scope(auth),
    )
    fc = report_service.indicators_geojson(rows, _scope(auth), auth["permissions"])
    filename = f"aquavision_indicators_{date.today().isoformat()}.geojson"
    return Response(
        content=json.dumps(fc),
        media_type="application/geo+json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/regions.geojson")
async def export_regions_geojson(auth: dict = Depends(EXPORT)):
    """Latest-week severity choropleth as GeoJSON polygons joined with the
    latest access-filtered indicators per district."""
    fc = report_service.latest_geojson(_scope(auth), auth["permissions"])
    return Response(
        content=json.dumps(fc),
        media_type="application/geo+json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="aquavision_latest.geojson"'},
    )


# ---------------------------------------------------------------------------
# Weekly PDF reports
# ---------------------------------------------------------------------------
@router.post("/reports/generate", response_model=WaterReport, status_code=201)
async def generate_report(auth: dict = Depends(EXPORT)):
    """Generate a weekly PDF report (national scope respected), persist its
    metadata, and return the report row so the UI can offer a download."""
    week, title, file_path = report_service.generate_weekly_report(
        auth["user_id"], _scope(auth),
    )
    report = report_service.create_report(
        week_start_date=week, title=title, scope="National",
        user_id=auth["user_id"], file_path=file_path,
    )
    write_audit(
        action="REPORT_GENERATED",
        module="water",
        user_id=auth["user_id"],
        resource_type="water_report",
        resource_id=str(report.id),
        after_value={"title": title, "file_path": file_path, "week_start_date": week.isoformat()},
        result="success",
    )
    return water_service._hydrate_report(report)


@router.get("/reports/{report_id}/download")
async def download_report(report_id: int, auth: dict = Depends(READ)):
    """Stream a previously generated weekly PDF report file."""
    report = water_service.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "Success":
        raise HTTPException(status_code=409, detail="Report is not ready for download")
    path = report_service.resolve_report_file(report.file_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Report file not found on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"aquavision-weekly-{report.week_start_date.isoformat()}.pdf",
    )
