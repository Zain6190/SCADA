# Persist Soft OT catalog / ticks into AquaVision without touching official sources.
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import (
    WaterAsset,
    WaterFFDObservation,
    WaterObservation,
    WaterOtCommand,
    WaterOtDevice,
    WaterOtDivergence,
    WaterOtProcessDay,
    WaterOtRuntimeState,
    WaterOtTag,
    WaterOtTagValue,
    WaterSource,
)

logger = logging.getLogger("aquavision.ot")

OT_ROOT = Path(__file__).resolve().parents[3] / "ot-runtime"
if str(OT_ROOT) not in sys.path:
    sys.path.insert(0, str(OT_ROOT))

from ot_runtime.anchor import GAUGE_IDS, SKIP_AUTHORITIES, map_official_anchor  # noqa: E402
from ot_runtime.catalog import DEVICE_CATALOG  # noqa: E402
from ot_runtime.runtime import OtRuntime, PublishReading  # noqa: E402

SOFT_OT_AUTHORITY = "SOFT_OT"
SOFT_OT_PRIORITY = 4
SOFT_OT_ORIGIN = "SYNTHETIC"
SOFT_OT_STATUS = "SIMULATED"

_RUNTIME: Optional[OtRuntime] = None
_ANCHORING = False


def get_runtime(db: Optional[Session] = None, auto_anchor: bool = True) -> OtRuntime:
    global _RUNTIME, _ANCHORING
    if _RUNTIME is None:
        _RUNTIME = OtRuntime(sim_minutes=15.0)
    if auto_anchor and not _RUNTIME.series_loaded and not _ANCHORING:
        _ANCHORING = True
        try:
            loaded = load_process_series(_RUNTIME, db=db)
            if loaded:
                restore_runtime_state(_RUNTIME, db=db)
            elif not _RUNTIME.anchored:
                apply_official_anchor_now(db=db, force=False)
        finally:
            _ANCHORING = False
    return _RUNTIME


def _observation_to_irsa_dict(obs: WaterObservation) -> Dict[str, Any]:
    return {
        "asset_id": obs.asset_id,
        "water_level_ft": obs.water_level_ft,
        "inflow_cusecs": obs.inflow_cusecs,
        "outflow_cusecs": obs.outflow_cusecs,
        "discharge_cusecs": obs.discharge_cusecs,
        "upstream_discharge_cusecs": obs.upstream_discharge_cusecs,
        "downstream_discharge_cusecs": obs.downstream_discharge_cusecs,
        "source_authority": obs.source_authority,
        "source": "IRSA",
        "observed_at": obs.observed_at,
        "source_priority": obs.source_priority,
    }


def _ffd_to_dict(obs: WaterFFDObservation) -> Dict[str, Any]:
    return {
        "asset_id": obs.asset_id,
        "gauge_level_ft": obs.gauge_level_ft,
        "discharge_cusecs": obs.discharge_cusecs,
        "source_authority": "FFD",
        "source": "FFD",
        "observed_at": obs.observed_at,
    }


def load_official_anchor(db: Session) -> Dict[int, Dict[str, Any]]:
    """Latest IRSA observation per asset + latest FFD row per river station.

    Skips Soft OT / USGS / BATADAL / Kaggle. Does not write official rows.
    """
    skip = tuple(SKIP_AUTHORITIES)
    latest_irsa = (
        select(
            WaterObservation.asset_id.label("asset_id"),
            func.max(WaterObservation.observed_at).label("max_at"),
        )
        .where(
            or_(
                WaterObservation.source_authority == "IRSA",
                WaterObservation.source_priority == 1,
            ),
            or_(
                WaterObservation.source_authority.is_(None),
                WaterObservation.source_authority.notin_(skip),
            ),
        )
        .group_by(WaterObservation.asset_id)
        .subquery()
    )
    irsa_rows = db.execute(
        select(WaterObservation).join(
            latest_irsa,
            and_(
                WaterObservation.asset_id == latest_irsa.c.asset_id,
                WaterObservation.observed_at == latest_irsa.c.max_at,
            ),
        )
    ).scalars().all()
    irsa_by_asset: Dict[int, Dict[str, Any]] = {}
    for obs in irsa_rows:
        if obs.source_authority in SKIP_AUTHORITIES:
            continue
        irsa_by_asset[int(obs.asset_id)] = _observation_to_irsa_dict(obs)

    latest_ffd = (
        select(
            WaterFFDObservation.asset_id.label("asset_id"),
            func.max(WaterFFDObservation.observed_at).label("max_at"),
        )
        .where(WaterFFDObservation.asset_id.in_(tuple(GAUGE_IDS)))
        .group_by(WaterFFDObservation.asset_id)
        .subquery()
    )
    ffd_rows = db.execute(
        select(WaterFFDObservation).join(
            latest_ffd,
            and_(
                WaterFFDObservation.asset_id == latest_ffd.c.asset_id,
                WaterFFDObservation.observed_at == latest_ffd.c.max_at,
            ),
        )
    ).scalars().all()
    ffd_by_asset: Dict[int, Dict[str, Any]] = {}
    for obs in ffd_rows:
        if obs.asset_id is None:
            continue
        ffd_by_asset[int(obs.asset_id)] = _ffd_to_dict(obs)

    return map_official_anchor(irsa_by_asset, ffd_by_asset)


def apply_official_anchor_now(
    db: Optional[Session] = None,
    force: bool = True,
) -> Dict[str, Any]:
    """Load latest official rows and seed the in-memory plant."""
    runtime = get_runtime(auto_anchor=False)
    if runtime.anchored and not force:
        return runtime.anchor_meta
    own = db is None
    session = db
    try:
        if session is None:
            if SessionLocal is None:
                return runtime.anchor_meta
            session = SessionLocal()
        states = load_official_anchor(session)
        return runtime.apply_official_anchor(states, match_gates=True)
    except Exception as exc:
        logger.warning("Soft OT official anchor skipped: %s", exc)
        return runtime.anchor_meta
    finally:
        if own and session is not None:
            session.close()


def reanchor_soft_ot_from_ingest(reason: str = "official-ingest") -> Dict[str, Any]:
    """Called after IRSA/FFD ingest. Never writes official observations."""
    try:
        meta = apply_official_anchor_now(force=True)
        logger.info("Soft OT re-anchored after %s: %s", reason, meta.get("banner"))
        return meta
    except Exception as exc:
        logger.warning("Soft OT re-anchor after %s failed: %s", reason, exc)
        return {"applied": False, "error": str(exc)}


def _source(db: Session) -> WaterSource:
    source = db.execute(
        select(WaterSource).where(WaterSource.authority == SOFT_OT_AUTHORITY)
    ).scalar_one_or_none()
    if source:
        return source
    source = WaterSource(
        authority=SOFT_OT_AUTHORITY,
        source_url="soft-ot-runtime",
        source_type="SIMULATED_OT",
        update_frequency="SUB_DAILY",
        description="Software PLC/RTU runtime — simulated telemetry",
    )
    db.add(source)
    db.flush()
    return source


def seed_ot_catalog(db: Optional[Session] = None) -> int:
    """Upsert all catalog devices and tags. Returns device count."""
    own = db is None
    db = db or SessionLocal()
    try:
        _source(db)
        count = 0
        for spec in DEVICE_CATALOG:
            asset = db.get(WaterAsset, spec.asset_id)
            if not asset:
                logger.warning("Skipping OT device %s — asset %s missing", spec.device_code, spec.asset_id)
                continue
            device = db.execute(
                select(WaterOtDevice).where(WaterOtDevice.device_code == spec.device_code)
            ).scalar_one_or_none()
            if not device:
                device = WaterOtDevice(
                    device_code=spec.device_code,
                    kind=spec.kind,
                    asset_id=spec.asset_id,
                    scan_ms=spec.scan_ms,
                    publish_s=spec.publish_s,
                    notes="SIMULATION — does not control real infrastructure",
                )
                db.add(device)
                db.flush()
            else:
                device.kind = spec.kind
                device.scan_ms = spec.scan_ms
                device.publish_s = spec.publish_s
            existing = {t.name: t for t in db.execute(
                select(WaterOtTag).where(WaterOtTag.device_id == device.id)
            ).scalars()}
            for tag in spec.tags:
                row = existing.get(tag.name)
                if not row:
                    db.add(WaterOtTag(
                        device_id=device.id,
                        name=tag.name,
                        tag_class=tag.tag_class,
                        unit=tag.unit,
                        description=tag.description,
                    ))
            count += 1
        db.commit()
        return count
    finally:
        if own:
            db.close()


def publish_soft_ot_readings(
    readings: List[PublishReading],
    db: Optional[Session] = None,
    evaluate_thresholds: bool = True,
) -> Dict[str, Any]:
    """Write AI packets as water_observations under SOFT_OT (priority 4)."""
    own = db is None
    db = db or SessionLocal()
    accepted = 0
    rejected = 0
    errors: List[str] = []
    ids: List[int] = []
    try:
        source = _source(db)
        for r in readings:
            existing = db.execute(
                select(WaterObservation).where(
                    WaterObservation.asset_id == r.asset_id,
                    WaterObservation.observed_at == r.observed_at,
                    WaterObservation.source_id == source.id,
                )
            ).scalar_one_or_none()
            if existing:
                rejected += 1
                errors.append(f"Duplicate SOFT_OT reading asset={r.asset_id} at {r.observed_at}")
                continue
            extras = r.extras or {}
            origin = getattr(r, "data_origin", None) or SOFT_OT_ORIGIN
            status = SOFT_OT_STATUS if origin == SOFT_OT_ORIGIN else origin
            di_bits = []
            for key in ("comms_ok", "power_ok", "limit_open", "limit_closed", "actuator_fault", "freeze"):
                if key in extras:
                    di_bits.append(f"{key}={1 if extras[key] else 0}")
            notes = r.notes
            if di_bits:
                notes = f"{notes}; di:{','.join(di_bits)}"
            obs = WaterObservation(
                asset_id=r.asset_id,
                source_id=source.id,
                observed_at=r.observed_at,
                water_level_ft=r.water_level_ft,
                inflow_cusecs=r.inflow_cusecs,
                outflow_cusecs=r.outflow_cusecs,
                discharge_cusecs=r.discharge_cusecs,
                data_status=status,
                data_origin=origin,
                quality_status=r.quality or "VALID",
                quality_flag=f"SOFT_OT_{r.device_code}",
                source_authority=SOFT_OT_AUTHORITY,
                source_publication_time=datetime.now(timezone.utc),
                source_parser_version="soft_ot_v1",
                source_priority=SOFT_OT_PRIORITY,
                notes=notes,
            )
            db.add(obs)
            db.flush()
            ids.append(obs.id)
            accepted += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()

    if accepted > 0 and evaluate_thresholds:
        try:
            from infrastructure.thresholds.engine import evaluate_all_assets
            evaluate_all_assets()
        except Exception as exc:
            logger.warning("Threshold evaluation after SOFT_OT publish failed: %s", exc)

    return {"accepted": accepted, "rejected": rejected, "errors": errors, "observation_ids": ids}


def _write_tag_values(db: Session, device: WaterOtDevice, values: Dict[str, float], quality: str, when: datetime) -> None:
    tags = {t.name: t for t in db.execute(
        select(WaterOtTag).where(WaterOtTag.device_id == device.id)
    ).scalars()}
    for name, value in values.items():
        tag = tags.get(name)
        if not tag:
            continue
        db.add(WaterOtTagValue(
            tag_id=tag.id,
            value=value,
            quality=quality,
            observed_at=when,
        ))


def persist_tick_tags(db: Session, runtime: OtRuntime, when: datetime) -> None:
    for spec in DEVICE_CATALOG:
        device = db.execute(
            select(WaterOtDevice).where(WaterOtDevice.device_code == spec.device_code)
        ).scalar_one_or_none()
        if not device:
            continue
        ai = runtime.plant.as_ai(spec.asset_id)
        values: Dict[str, float] = {
            "AI.level_ft": ai["level_ft"],
            "AI.inflow_cusecs": ai["inflow_cusecs"],
            "AI.outflow_cusecs": ai["outflow_cusecs"],
            "AI.discharge_cusecs": ai["discharge_cusecs"],
            "DI.comms_ok": 1.0,
            "DI.power_ok": 1.0,
        }
        if spec.asset_id in runtime.rtus:
            rtu = runtime.rtus[spec.asset_id]
            values["DI.comms_ok"] = 0.0 if rtu.comms_down else 1.0
            values["DI.power_ok"] = 0.0 if rtu.power_fail else 1.0
            device.comms_ok = not rtu.comms_down
        if spec.asset_id in runtime.plcs:
            plc = runtime.plcs[spec.asset_id]
            values["AI.gate_pos_pct"] = plc.gate_pos_pct
            values["AO.gate_cmd_pct"] = plc.gate_cmd_pct
            values["DI.limit_open"] = 1.0 if plc.gate_pos_pct >= 98 else 0.0
            values["DI.limit_closed"] = 1.0 if plc.gate_pos_pct <= 2 else 0.0
            values["DI.actuator_fault"] = 1.0 if plc.jammed else 0.0
            values["DI.comms_ok"] = 0.0 if plc.comms_down else 1.0
            values["DO.gate_enable"] = 0.0 if plc.comms_down or plc.jammed else 1.0
            device.comms_ok = not plc.comms_down
        device.last_scan_at = when
        _write_tag_values(db, device, values, "VALID", when)


def apply_hmi_setpoint(
    asset_id: int,
    tag: str,
    value: float,
    actor: str = "virtual-hmi",
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Write AO into the simulator + audit table. Does NOT write water_observations."""
    own = db is None
    db = db or SessionLocal()
    try:
        seed_ot_catalog(db)
        runtime = get_runtime(db=db)
        runtime.set_setpoint(asset_id, tag, value)
        device = db.execute(
            select(WaterOtDevice).where(WaterOtDevice.asset_id == asset_id, WaterOtDevice.kind == "PLC")
        ).scalar_one_or_none()
        if not device:
            raise ValueError(f"No Soft PLC for asset {asset_id}")
        cmd = WaterOtCommand(
            device_id=device.id,
            asset_id=asset_id,
            tag_name=tag,
            value=value,
            action="SETPOINT",
            actor=actor,
            notes="SIMULATION — setpoint stays inside Soft PLC",
        )
        db.add(cmd)
        db.commit()
        return {
            "ok": True,
            "action": "SETPOINT",
            "asset_id": asset_id,
            "tag": tag,
            "value": value,
            "writes_observations": False,
        }
    finally:
        if own:
            db.close()


def apply_hmi_fault(
    asset_id: int,
    kind: str,
    actor: str = "virtual-hmi",
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    own = db is None
    db = db or SessionLocal()
    try:
        seed_ot_catalog(db)
        runtime = get_runtime(db=db)
        if kind == "clear":
            runtime.clear_faults(asset_id)
            action = "CLEAR_FAULT"
        else:
            runtime.inject_fault(asset_id, kind)
            action = "FAULT"
        device = db.execute(
            select(WaterOtDevice).where(WaterOtDevice.asset_id == asset_id)
        ).scalar_one_or_none()
        if not device:
            raise ValueError(f"No Soft OT device for asset {asset_id}")
        db.add(WaterOtCommand(
            device_id=device.id,
            asset_id=asset_id,
            tag_name=kind,
            value=None,
            action=action,
            actor=actor,
            notes="SIMULATION — fault injection, no hardware",
        ))
        db.commit()
        return {"ok": True, "action": action, "asset_id": asset_id, "kind": kind, "writes_observations": False}
    finally:
        if own:
            db.close()


def _week_start(value):
    day = value.date() if isinstance(value, datetime) else value
    return day - timedelta(days=day.weekday())


def _days_from_csv() -> list:
    """Fallback when water_ot_process_days is not loaded yet. The CSV is the collected IRSA/FFD series."""
    import csv
    from ot_runtime.series import OfficialDay, parse_day

    path = None
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "ot" / "indus_ot_daily.csv"
        if candidate.exists():
            path = candidate
            break
    if path is None:
        return []
    days = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            observed = parse_day(row.get("observed_on"))
            if observed is None or not row.get("asset_id"):
                continue

            def _num(key: str):
                raw = row.get(key)
                if raw is None or raw == "":
                    return None
                return float(raw)

            days.append(OfficialDay(
                observed_on=observed,
                asset_id=int(row["asset_id"]),
                level_ft=_num("level_ft"),
                inflow_cusecs=_num("inflow_cusecs"),
                outflow_cusecs=_num("outflow_cusecs"),
                discharge_cusecs=_num("discharge_cusecs"),
                canal_offtake_cusecs=float(_num("canal_offtake_cusecs") or 0),
                gate_pct_derived=_num("gate_pct_derived"),
                source_authority=row.get("source_authority") or "IRSA",
                source_url=row.get("source_url") or "",
                device_code=row.get("device_code") or "",
            ))
    return days


def load_process_series(runtime: OtRuntime, db: Optional[Session] = None) -> int:
    """Load water_ot_process_days into the runtime. Official observation rows are not written."""
    own = db is None
    session = db
    days = []
    try:
        if session is None:
            if SessionLocal is None:
                session = None
            else:
                session = SessionLocal()
        if session is not None:
            rows = session.execute(
                select(WaterOtProcessDay).order_by(WaterOtProcessDay.observed_on, WaterOtProcessDay.asset_id)
            ).scalars().all()
            from ot_runtime.series import OfficialDay
            days = [
                OfficialDay(
                    observed_on=row.observed_on,
                    asset_id=int(row.asset_id),
                    level_ft=row.level_ft,
                    inflow_cusecs=row.inflow_cusecs,
                    outflow_cusecs=row.outflow_cusecs,
                    discharge_cusecs=row.discharge_cusecs,
                    canal_offtake_cusecs=float(row.canal_offtake_cusecs or 0),
                    gate_pct_derived=row.gate_pct_derived,
                    source_authority=row.source_authority,
                    source_url=row.source_url or "",
                    device_code=row.device_code,
                )
                for row in rows
            ]
    except Exception as exc:
        logger.warning("Soft OT process table not loaded: %s", exc)
        days = []
    finally:
        if own and session is not None:
            session.close()
    if not days:
        days = _days_from_csv()
    if not days:
        return 0
    return runtime.load_series(days)


def restore_runtime_state(runtime: OtRuntime, db: Optional[Session] = None) -> bool:
    own = db is None
    session = db
    try:
        if session is None:
            if SessionLocal is None:
                return False
            session = SessionLocal()
        row = session.get(WaterOtRuntimeState, 1)
        if row is None or not row.state_json:
            return False
        runtime.restore_state(row.state_json)
        return True
    except Exception as exc:
        logger.warning("Soft OT state restore skipped: %s", exc)
        return False
    finally:
        if own and session is not None:
            session.close()


def save_runtime_state(runtime: OtRuntime, db: Session, divergences: Optional[List[Dict[str, Any]]] = None) -> None:
    state = runtime.export_state()
    row = db.get(WaterOtRuntimeState, 1)
    if row is None:
        row = WaterOtRuntimeState(id=1)
        db.add(row)
    row.cursor_date = runtime.cursor
    row.state_json = state
    row.updated_at = datetime.now(timezone.utc)
    for spec in DEVICE_CATALOG:
        device = db.execute(
            select(WaterOtDevice).where(WaterOtDevice.device_code == spec.device_code)
        ).scalar_one_or_none()
        if device is None:
            continue
        device.control_mode = runtime.modes.get(spec.asset_id, "TRACK")
        plc = runtime.plcs.get(spec.asset_id)
        if plc is not None:
            device.gate_cmd_pct = plc.gate_cmd_pct
        flags = (state.get("faults") or {}).get(str(spec.asset_id)) or []
        device.fault_state = ",".join(flags) or None
    for item in divergences or []:
        observed = item.get("observed_on")
        if not observed:
            continue
        db.add(WaterOtDivergence(
            asset_id=int(item["asset_id"]),
            observed_on=observed if isinstance(observed, date) else date.fromisoformat(str(observed)[:10]),
            official_outflow=item.get("official_outflow"),
            scenario_outflow=item.get("scenario_outflow"),
            official_gate_pct=item.get("official_gate_pct"),
            scenario_gate_pct=item.get("scenario_gate_pct"),
            reason=item.get("reason"),
        ))
        note = item.get("canal_note")
        if not note:
            continue
        observed_on = observed if isinstance(observed, date) else date.fromisoformat(str(observed)[:10])
        db.execute(text("""
            UPDATE aquavision.water_channel_condition AS c
            SET notes = :note
            FROM aquavision.water_channels AS ch
            WHERE c.channel_id = ch.id
              AND ch.feeds_from_asset_id = :asset_id
              AND c.method = 'GAUGE_DISCHARGE'
              AND c.observed_week = :week
        """), {
            "note": note,
            "asset_id": int(item["asset_id"]),
            "week": _week_start(observed_on),
        })


def ot_report_section(runtime: Optional[OtRuntime] = None) -> Dict[str, Any]:
    runtime = runtime or get_runtime(auto_anchor=True)
    devices = []
    for row in runtime.process_view():
        devices.append({
            "device_code": row["device_code"],
            "asset_id": row["asset_id"],
            "mode": row["mode"],
            "official_on": row["official_on"],
            "interlock_reasons": row["interlock_reasons"],
            "official_outflow": row["official_outflow"],
            "scenario_outflow": row["scenario_outflow"],
            "comms_ok": row["comms_ok"],
        })
    section = {
        "title": "Soft OT",
        "coverage": runtime.coverage(),
        "devices": devices,
        "open_interlocks": [d for d in devices if d["interlock_reasons"]],
        "scenarios": [d for d in devices if d["mode"] == "SCENARIO"],
    }
    report_dir = Path(__file__).resolve().parents[4] / "data" / "reports"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        path = report_dir / f"ot-section-{stamp}.txt"
        lines = [
            "Soft OT section",
            f"Days loaded: {section['coverage'].get('days')}",
            f"Cursor: {section['coverage'].get('cursor')}",
            f"Last official day: {section['coverage'].get('last')}",
        ]
        for device in devices:
            if device["mode"] != "SCENARIO" and not device["interlock_reasons"]:
                continue
            lines.append(
                f"{device['device_code']} {device['mode']} official={device['official_on']} "
                f"outflow {device['official_outflow']} -> {device['scenario_outflow']} "
                f"interlocks={','.join(device['interlock_reasons']) or 'none'}"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        section["file_path"] = str(path)
    except Exception as exc:
        logger.warning("OT report section file skipped: %s", exc)
        section["file_path"] = None
    return section


def run_ot_tick(evaluate_thresholds: bool = True) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        seeded = seed_ot_catalog(db)
        runtime = get_runtime(db=db)
        result = runtime.tick()
        persist_tick_tags(db, runtime, result.sim_time)
        try:
            save_runtime_state(runtime, db, result.divergences)
        except Exception as exc:
            logger.warning("Soft OT state save skipped: %s", exc)
        db.commit()
        published = publish_soft_ot_readings(
            result.published, evaluate_thresholds=evaluate_thresholds
        )
        if evaluate_thresholds:
            try:
                from infrastructure.thresholds.engine import evaluate_ot_process
                evaluate_ot_process(runtime.process_view())
            except Exception as exc:
                logger.warning("OT process alerts skipped: %s", exc)
        return {
            "seeded_devices": seeded,
            "ticks": runtime.ticks,
            "sim_time": result.sim_time.isoformat(),
            "cursor": result.cursor,
            "device_count": len(result.devices),
            "publish": published,
            "devices": result.devices,
            "divergences": result.divergences,
        }
    finally:
        db.close()
