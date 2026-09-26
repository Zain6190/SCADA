# Soft PLC / RTU and Virtual HMI API.
# HMI routes write only to the simulator + water_ot_commands.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import (
    WaterAsset,
    WaterObservation,
    WaterOtCommand,
    WaterOtDevice,
    WaterOtTag,
    WaterOtTagValue,
    WaterSource,
)
from infrastructure.ot.persist import (
    SOFT_OT_AUTHORITY,
    apply_hmi_fault,
    apply_hmi_setpoint,
    apply_official_anchor_now,
    get_runtime,
    ot_report_section,
    run_ot_tick,
    seed_ot_catalog,
)

router = APIRouter(prefix="/ot", tags=["Soft OT"])


class SetpointRequest(BaseModel):
    asset_id: int
    tag: str = "AO.gate_cmd_pct"
    value: float = Field(..., ge=0, le=100)
    actor: str = "virtual-hmi"


class FaultRequest(BaseModel):
    asset_id: int
    kind: str = Field(..., description="comms_down | sensor_stuck | actuator_jam | inflow_surge | clear")
    actor: str = "virtual-hmi"


def _device_payload(device: WaterOtDevice, asset: Optional[WaterAsset], live: dict) -> dict:
    return {
        "id": device.id,
        "device_code": device.device_code,
        "kind": device.kind,
        "asset_id": device.asset_id,
        "asset_name": asset.canonical_name if asset else live.get("asset_name"),
        "scan_ms": device.scan_ms,
        "publish_s": device.publish_s,
        "is_active": device.is_active,
        "comms_ok": device.comms_ok,
        "last_scan_at": device.last_scan_at.isoformat() if device.last_scan_at else None,
        "notes": device.notes,
        "mode": live.get("mode") or getattr(device, "control_mode", None) or "TRACK",
        "simulation": True,
        "live": live,
    }


@router.get("/devices")
def list_devices(db: Session = Depends(get_session)):
    seed_ot_catalog(db)
    runtime = get_runtime(db=db)
    live = {row["asset_id"]: row for row in runtime.device_status()}
    devices = db.execute(select(WaterOtDevice).order_by(WaterOtDevice.asset_id)).scalars().all()
    out = []
    for d in devices:
        asset = db.get(WaterAsset, d.asset_id)
        out.append(_device_payload(d, asset, live.get(d.asset_id, {})))
    return out


@router.get("/devices/{device_id}")
def get_device(device_id: int, db: Session = Depends(get_session)):
    seed_ot_catalog(db)
    device = db.get(WaterOtDevice, device_id)
    if not device:
        raise HTTPException(404, "OT device not found")
    asset = db.get(WaterAsset, device.asset_id)
    live = next((r for r in get_runtime(db=db).device_status() if r["asset_id"] == device.asset_id), {})
    tags = db.execute(
        select(WaterOtTag).where(WaterOtTag.device_id == device.id).order_by(WaterOtTag.name)
    ).scalars().all()
    latest = []
    for tag in tags:
        val = db.execute(
            select(WaterOtTagValue)
            .where(WaterOtTagValue.tag_id == tag.id)
            .order_by(desc(WaterOtTagValue.observed_at))
            .limit(1)
        ).scalar_one_or_none()
        latest.append({
            "name": tag.name,
            "tag_class": tag.tag_class,
            "unit": tag.unit,
            "description": tag.description,
            "value": val.value if val else None,
            "quality": val.quality if val else None,
            "observed_at": val.observed_at.isoformat() if val else None,
            "published_to_aquavision": tag.tag_class in ("AI", "DI"),
        })
    commands = db.execute(
        select(WaterOtCommand)
        .where(WaterOtCommand.device_id == device.id)
        .order_by(desc(WaterOtCommand.created_at))
        .limit(20)
    ).scalars().all()
    return {
        **_device_payload(device, asset, live),
        "tags": latest,
        "commands": [
            {
                "id": c.id,
                "action": c.action,
                "tag_name": c.tag_name,
                "value": c.value,
                "actor": c.actor,
                "notes": c.notes,
                "created_at": c.created_at.isoformat(),
            }
            for c in commands
        ],
    }


@router.get("/tags")
def list_tags(db: Session = Depends(get_session)):
    seed_ot_catalog(db)
    rows = db.execute(
        select(WaterOtTag, WaterOtDevice)
        .join(WaterOtDevice, WaterOtTag.device_id == WaterOtDevice.id)
        .order_by(WaterOtDevice.asset_id, WaterOtTag.name)
    ).all()
    return [
        {
            "device_code": device.device_code,
            "kind": device.kind,
            "asset_id": device.asset_id,
            "name": tag.name,
            "tag_class": tag.tag_class,
            "unit": tag.unit,
            "published_to_aquavision": tag.tag_class in ("AI", "DI"),
        }
        for tag, device in rows
    ]


@router.get("/commands")
def list_commands(limit: int = 50, db: Session = Depends(get_session)):
    rows = db.execute(
        select(WaterOtCommand).order_by(desc(WaterOtCommand.created_at)).limit(limit)
    ).scalars().all()
    return [
        {
            "id": c.id,
            "device_id": c.device_id,
            "asset_id": c.asset_id,
            "action": c.action,
            "tag_name": c.tag_name,
            "value": c.value,
            "actor": c.actor,
            "notes": c.notes,
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]


@router.post("/tick")
def tick():
    return run_ot_tick(evaluate_thresholds=True)


@router.post("/anchor")
def anchor_official(db: Session = Depends(get_session)):
    """Reload Soft OT plant state from the latest IRSA/FFD rows. Does not write official observations."""
    seed_ot_catalog(db)
    meta = apply_official_anchor_now(db=db, force=True)
    return {
        "ok": True,
        "writes_observations": False,
        "banner": meta.get("banner"),
        "anchor": meta,
        "simulation": True,
    }


@router.post("/hmi/setpoint")
def hmi_setpoint(body: SetpointRequest, db: Session = Depends(get_session)):
    """Virtual HMI setpoint — Soft PLC AO only. Never writes water_observations."""
    before = db.execute(
        select(WaterObservation.id)
        .join(WaterSource, WaterObservation.source_id == WaterSource.id)
        .where(WaterSource.authority == SOFT_OT_AUTHORITY)
        .order_by(desc(WaterObservation.id))
        .limit(1)
    ).scalar_one_or_none()
    try:
        result = apply_hmi_setpoint(body.asset_id, body.tag, body.value, actor=body.actor, db=db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    after = db.execute(
        select(WaterObservation.id)
        .join(WaterSource, WaterObservation.source_id == WaterSource.id)
        .where(WaterSource.authority == SOFT_OT_AUTHORITY)
        .order_by(desc(WaterObservation.id))
        .limit(1)
    ).scalar_one_or_none()
    result["observation_id_before"] = before
    result["observation_id_after"] = after
    result["banner"] = "SIMULATION — does not control real infrastructure"
    return result


@router.post("/hmi/fault")
def hmi_fault(body: FaultRequest, db: Session = Depends(get_session)):
    allowed = {"comms_down", "sensor_stuck", "actuator_jam", "inflow_surge", "clear"}
    if body.kind not in allowed:
        raise HTTPException(400, f"kind must be one of {sorted(allowed)}")
    try:
        result = apply_hmi_fault(body.asset_id, body.kind, actor=body.actor, db=db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    result["banner"] = "SIMULATION — does not control real infrastructure"
    return result


@router.get("/process-view")
def process_view(db: Session = Depends(get_session)):
    """Official day, OT reading, mode, interlocks, and divergence for every asset."""
    runtime = get_runtime(db=db)
    return {
        "coverage": runtime.coverage(),
        "assets": runtime.process_view(),
        "banner": "Software twin. Commands do not leave this process.",
    }


@router.get("/report-section")
def report_section(db: Session = Depends(get_session)):
    return ot_report_section(get_runtime(db=db))


@router.get("/status")
def ot_status(db: Session = Depends(get_session)):
    seed_ot_catalog(db)
    runtime = get_runtime(db=db)
    devices = db.execute(select(WaterOtDevice)).scalars().all()
    source = db.execute(
        select(WaterSource).where(WaterSource.authority == SOFT_OT_AUTHORITY)
    ).scalar_one_or_none()
    obs_count = 0
    if source:
        from sqlalchemy import func
        obs_count = db.execute(
            select(func.count(WaterObservation.id)).where(WaterObservation.source_id == source.id)
        ).scalar() or 0
    anchor = runtime.anchor_meta or {}
    coverage = runtime.coverage()
    return {
        "runtime": "software-only",
        "hardware_required": False,
        "source_authority": SOFT_OT_AUTHORITY,
        "source_priority": 4,
        "data_origin": "OFFICIAL_REPLAY" if runtime.series_loaded else "SYNTHETIC",
        "data_status": "OFFICIAL_REPLAY" if runtime.series_loaded else "SIMULATED",
        "coverage": coverage,
        "devices": len(devices),
        "rtu": sum(1 for d in devices if d.kind == "RTU"),
        "plc": sum(1 for d in devices if d.kind == "PLC"),
        "published_observations": obs_count,
        "ticks": runtime.ticks,
        "banner": "SIMULATION — does not control real infrastructure",
        "anchor": anchor,
        "anchor_banner": anchor.get("banner"),
        "sensor_api_note": anchor.get("sensor_api_note")
        or "Live SENSOR_API 15-minute files stay a later optional AI input through existing ingest.",
    }
