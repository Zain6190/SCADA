# Orchestrates plant + devices for one software OT tick.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional

from ot_runtime.anchor import plant_states_only, summarize_anchor
from ot_runtime.catalog import DEVICE_BY_ASSET, DEVICE_CATALOG, downstream_asset_id
from ot_runtime.interlocks import decide_interlocks, gate_from_outflow, outflow_from_gate, slew_gate
from ot_runtime.plant import VirtualPlant
from ot_runtime.plc import PlcSnapshot, SoftPLC
from ot_runtime.rtu import OFFICIAL_STALE_HOURS, RtuPacket, SoftRTU
from ot_runtime.series import (
    BARRAGE_ASSET_IDS,
    GATE_MATCH_PCT,
    OfficialDay,
    barrage_release,
    canal_shortfall_note,
    complete_day,
)


@dataclass
class PublishReading:
    asset_id: int
    device_code: str
    kind: str
    observed_at: datetime
    water_level_ft: Optional[float]
    inflow_cusecs: Optional[float]
    outflow_cusecs: Optional[float]
    discharge_cusecs: Optional[float]
    quality: str
    notes: str
    data_origin: str = "SYNTHETIC"
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TickResult:
    sim_time: datetime
    published: List[PublishReading]
    devices: List[Dict[str, Any]]
    divergences: List[Dict[str, Any]] = field(default_factory=list)
    cursor: Optional[str] = None


class OtRuntime:
    def __init__(self, sim_minutes: float = 15.0) -> None:
        self.plant = VirtualPlant(sim_minutes=sim_minutes)
        self.rtus: Dict[int, SoftRTU] = {
            d.asset_id: SoftRTU(d) for d in DEVICE_CATALOG if d.kind == "RTU"
        }
        self.plcs: Dict[int, SoftPLC] = {
            d.asset_id: SoftPLC(d, gate_pos_pct=d.default_gate_pct, gate_cmd_pct=d.default_gate_pct)
            for d in DEVICE_CATALOG
            if d.kind == "PLC"
        }
        self.sim_minutes = sim_minutes
        self.ticks = 0
        self.anchor_meta: Dict[str, Any] = summarize_anchor({})
        self.anchor_meta["assets"] = {}
        self._series: Dict[date, Dict[int, OfficialDay]] = {}
        self._dates: List[date] = []
        self.cursor: Optional[date] = None
        self.modes: Dict[int, str] = {d.asset_id: "TRACK" for d in DEVICE_CATALOG}
        self._prev_level: Dict[int, float] = {}
        self.divergences: Dict[int, Dict[str, Any]] = {}

    @property
    def anchored(self) -> bool:
        return bool(self.anchor_meta.get("applied"))

    def apply_official_anchor(
        self,
        states: Dict[int, Dict[str, Any]],
        match_gates: bool = True,
    ) -> Dict[str, Any]:
        """Seed the plant from official IRSA/FFD values and optionally match PLC gates."""
        hydro = plant_states_only(states)
        if hydro:
            self.plant.apply_anchor(hydro)
        if match_gates:
            for asset_id, plc in self.plcs.items():
                spec = DEVICE_BY_ASSET[asset_id]
                tank = self.plant.tanks[asset_id]
                outflow = tank.outflow_cusecs
                if asset_id in states and states[asset_id].get("outflow_cusecs") is None and states[asset_id].get(
                    "discharge_cusecs"
                ) is None:
                    continue
                if asset_id not in hydro:
                    continue
                gate = gate_from_outflow(
                    outflow,
                    tank.level_ft,
                    spec.dead_level_ft,
                    spec.normal_level_ft,
                    spec.max_outflow_cusecs,
                )
                plc.gate_cmd_pct = gate
                plc.gate_pos_pct = gate
                self.plant.set_gate(asset_id, gate)
        summary = summarize_anchor(states)
        assets_meta: Dict[str, Any] = {}
        for asset_id, patch in states.items():
            assets_meta[str(asset_id)] = {
                "source": patch.get("source"),
                "observed_at": patch.get("observed_at"),
                "fields": [
                    k
                    for k in ("level_ft", "inflow_cusecs", "outflow_cusecs", "discharge_cusecs")
                    if patch.get(k) is not None
                ],
            }
        summary["assets"] = assets_meta
        summary["applied_at"] = datetime.now(timezone.utc).isoformat()
        self.anchor_meta = summary
        return summary

    def anchor_label(self) -> Optional[str]:
        if not self.anchored:
            return None
        date = self.anchor_meta.get("date")
        sources = self.anchor_meta.get("sources") or []
        if not date:
            return None
        head = "+".join(sources) if sources else "IRSA/FFD"
        return f"{head}:{date}"

    def _with_anchor_note(self, notes: str) -> str:
        label = self.anchor_label()
        if not label:
            return notes
        extra = f"anchored_to={label}"
        return f"{notes}; {extra}" if notes else extra

    def set_setpoint(self, asset_id: int, tag: str, value: float) -> None:
        plc = self.plcs.get(asset_id)
        if plc is None:
            raise ValueError(f"Asset {asset_id} has no Soft PLC")
        if tag not in ("AO.gate_cmd_pct", "gate_cmd", "gate_cmd_pct"):
            raise ValueError(f"HMI may only write AO.gate_cmd_pct, not '{tag}'")
        plc.set_setpoint(value)
        self.plant.set_gate(asset_id, plc.gate_cmd_pct)
        if self.series_loaded:
            derived = self._derived_gate(asset_id)
            if derived is None or abs(plc.gate_cmd_pct - derived) > GATE_MATCH_PCT:
                self.modes[asset_id] = "SCENARIO"
            else:
                self.modes[asset_id] = "TRACK"

    def load_series(self, days: List[OfficialDay], cursor: Optional[date] = None) -> int:
        grouped: Dict[date, Dict[int, OfficialDay]] = {}
        for raw in days:
            day = complete_day(raw)
            grouped.setdefault(day.observed_on, {})[day.asset_id] = day
        self._series = grouped
        self._dates = sorted(grouped)
        if cursor is not None and cursor in grouped:
            self.cursor = cursor
        elif self.cursor not in grouped:
            self.cursor = self._dates[0] if self._dates else None
        for spec in DEVICE_CATALOG:
            self.modes.setdefault(spec.asset_id, "TRACK")
        self._seed_routes()
        self._sync_track_assets()
        return len(days)

    @property
    def series_loaded(self) -> bool:
        return bool(self._dates)

    def coverage(self) -> Dict[str, Any]:
        return {
            "days": len(self._dates),
            "first": self._dates[0].isoformat() if self._dates else None,
            "last": self._dates[-1].isoformat() if self._dates else None,
            "cursor": self.cursor.isoformat() if self.cursor else None,
            "holding_latest": bool(self._dates) and self.cursor == self._dates[-1],
            "scenario_assets": [aid for aid, mode in self.modes.items() if mode == "SCENARIO"],
        }

    def export_state(self) -> Dict[str, Any]:
        faults: Dict[str, List[str]] = {}
        for asset_id, plc in self.plcs.items():
            flags = []
            if plc.comms_down:
                flags.append("comms_down")
            if plc.jammed:
                flags.append("actuator_jam")
            faults[str(asset_id)] = flags
        for asset_id, rtu in self.rtus.items():
            flags = []
            if rtu.comms_down:
                flags.append("comms_down")
            if rtu.sensor_stuck:
                flags.append("sensor_stuck")
            if rtu.power_fail:
                flags.append("power_fail")
            faults[str(asset_id)] = flags
        return {
            "cursor": self.cursor.isoformat() if self.cursor else None,
            "modes": {str(k): v for k, v in self.modes.items()},
            "gates": {str(k): plc.gate_cmd_pct for k, plc in self.plcs.items()},
            "faults": faults,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        cursor = state.get("cursor")
        if cursor:
            parsed = date.fromisoformat(str(cursor)[:10])
            if parsed in self._series:
                self.cursor = parsed
        for key, mode in (state.get("modes") or {}).items():
            asset_id = int(key)
            if mode in ("TRACK", "SCENARIO"):
                self.modes[asset_id] = mode
        for key, gate in (state.get("gates") or {}).items():
            asset_id = int(key)
            if asset_id in self.plcs and gate is not None:
                self.plcs[asset_id].set_setpoint(float(gate))
                self.plcs[asset_id].gate_pos_pct = float(gate)
                self.plant.set_gate(asset_id, float(gate))
        for key, flags in (state.get("faults") or {}).items():
            asset_id = int(key)
            for flag in flags or []:
                if asset_id in self.plcs or asset_id in self.rtus:
                    try:
                        self.inject_fault(asset_id, flag)
                    except ValueError:
                        continue
        self._seed_routes()
        self._sync_track_assets()

    def inject_fault(self, asset_id: int, kind: str) -> None:
        if kind == "inflow_surge":
            self.plant.add_surge(asset_id, 80_000)
            if self.series_loaded:
                self.modes[asset_id] = "SCENARIO"
            return
        if asset_id in self.rtus:
            self.rtus[asset_id].inject_fault(kind)
            if self.series_loaded:
                self.modes[asset_id] = "SCENARIO"
            return
        if asset_id in self.plcs:
            self.plcs[asset_id].inject_fault(kind)
            if self.series_loaded:
                self.modes[asset_id] = "SCENARIO"
            return
        raise ValueError(f"No Soft OT device on asset {asset_id}")

    def clear_faults(self, asset_id: int) -> None:
        if asset_id in self.rtus:
            self.rtus[asset_id].clear_faults()
        if asset_id in self.plcs:
            self.plcs[asset_id].clear_faults()
        if not self.series_loaded:
            return
        derived = self._derived_gate(asset_id)
        plc = self.plcs.get(asset_id)
        if plc is None or derived is None or abs(plc.gate_cmd_pct - derived) <= GATE_MATCH_PCT:
            self.modes[asset_id] = "TRACK"
            self.divergences.pop(asset_id, None)

    def tick(self, now: Optional[datetime] = None, advance: bool = True) -> TickResult:
        now = now or datetime.now(timezone.utc)
        if not self.series_loaded:
            return self._tick_synthetic(now)
        result = self._tick_series(now)
        if advance and self.cursor is not None and self.cursor != self._dates[-1]:
            self.cursor = self._dates[self._dates.index(self.cursor) + 1]
            self._seed_routes()
            self._sync_track_assets()
        self.ticks += 1
        result.cursor = self.cursor.isoformat() if self.cursor else None
        return result

    def _tick_synthetic(self, now: datetime) -> TickResult:
        now = now or datetime.now(timezone.utc)
        dt_hours = self.sim_minutes / 60.0
        plc_gates = {aid: plc.gate_pos_pct for aid, plc in self.plcs.items()}
        ais = self.plant.step(plc_gates=plc_gates)
        published: List[PublishReading] = []
        device_rows: List[Dict[str, Any]] = []

        for spec in DEVICE_CATALOG:
            ai = ais[spec.asset_id]
            if spec.kind == "RTU":
                packets = self.rtus[spec.asset_id].scan(ai, now=now)
                rtu = self.rtus[spec.asset_id]
                for pkt in packets:
                    published.append(
                        PublishReading(
                            asset_id=pkt.asset_id,
                            device_code=pkt.device_code,
                            kind="RTU",
                            observed_at=pkt.observed_at,
                            water_level_ft=pkt.water_level_ft,
                            inflow_cusecs=pkt.inflow_cusecs,
                            outflow_cusecs=pkt.outflow_cusecs,
                            discharge_cusecs=pkt.discharge_cusecs,
                            quality=pkt.quality,
                            notes=self._with_anchor_note(pkt.notes),
                            extras={"comms_ok": pkt.comms_ok, "power_ok": pkt.power_ok},
                        )
                    )
                device_rows.append(
                    {
                        "device_code": spec.device_code,
                        "kind": "RTU",
                        "asset_id": spec.asset_id,
                        "comms_ok": not rtu.comms_down,
                        "buffered": len(rtu.buffer),
                        "ai": ai,
                    }
                )
            else:
                down_id = downstream_asset_id(spec.asset_id)
                down_crit = self.plant.is_critical(down_id) if down_id else False
                snap: PlcSnapshot = self.plcs[spec.asset_id].scan(
                    ai, dt_hours=dt_hours, downstream_critical=down_crit, now=now
                )
                self.plant.set_gate(spec.asset_id, snap.gate_pos_pct)
                published.append(
                    PublishReading(
                        asset_id=snap.asset_id,
                        device_code=snap.device_code,
                        kind="PLC",
                        observed_at=snap.observed_at,
                        water_level_ft=snap.water_level_ft,
                        inflow_cusecs=snap.inflow_cusecs,
                        outflow_cusecs=snap.outflow_cusecs,
                        discharge_cusecs=snap.discharge_cusecs,
                        quality=snap.quality,
                        notes=self._with_anchor_note(snap.notes),
                        extras={
                            "gate_pos_pct": snap.gate_pos_pct,
                            "gate_cmd_pct": snap.gate_cmd_pct,
                            "limit_open": snap.limit_open,
                            "limit_closed": snap.limit_closed,
                            "actuator_fault": snap.actuator_fault,
                            "comms_ok": snap.comms_ok,
                            "freeze": snap.freeze,
                            "reasons": snap.reasons,
                        },
                    )
                )
                device_rows.append(
                    {
                        "device_code": spec.device_code,
                        "kind": "PLC",
                        "asset_id": spec.asset_id,
                        "gate_pos_pct": snap.gate_pos_pct,
                        "gate_cmd_pct": snap.gate_cmd_pct,
                        "comms_ok": snap.comms_ok,
                        "actuator_fault": snap.actuator_fault,
                        "freeze": snap.freeze,
                        "reasons": snap.reasons,
                        "ai": ai,
                    }
                )

        self.ticks += 1
        return TickResult(sim_time=now, published=published, devices=device_rows)

    def _derived_gate(self, asset_id: int) -> Optional[float]:
        day = self._day(asset_id)
        return None if day is None else day.gate_pct_derived

    def _day(self, asset_id: int) -> Optional[OfficialDay]:
        if self.cursor is None:
            return None
        return self._series.get(self.cursor, {}).get(asset_id)

    def _official_at(self, day: OfficialDay) -> datetime:
        return datetime.combine(day.observed_on, time(12, 0), tzinfo=timezone.utc)

    def _quality_now(self, official_at: datetime, wall_now: datetime) -> datetime:
        """Historical replay days are current for that day. The latest day ages against the wall clock."""
        if self._dates and self.cursor == self._dates[-1]:
            return wall_now
        return official_at

    def _seed_routes(self) -> None:
        if not self._dates or self.cursor is None:
            return
        history: Dict[int, List[float]] = {}
        for observed_on in self._dates:
            if observed_on > self.cursor:
                break
            for asset_id, day in self._series[observed_on].items():
                discharge = day.discharge_cusecs if day.discharge_cusecs is not None else day.outflow_cusecs
                if discharge is None:
                    continue
                history.setdefault(asset_id, []).append(float(discharge))
        self.plant.seed_route_history(history)

    def _sync_track_assets(self) -> None:
        if self.cursor is None:
            return
        for asset_id, day in self._series.get(self.cursor, {}).items():
            if self.modes.get(asset_id) != "TRACK":
                continue
            tank = self.plant.tanks.get(asset_id)
            if tank is None:
                continue
            if day.level_ft is not None:
                tank.level_ft = float(day.level_ft)
            if day.inflow_cusecs is not None:
                tank.inflow_cusecs = float(day.inflow_cusecs)
                tank.local_inflow_cusecs = tank.inflow_cusecs
            if day.outflow_cusecs is not None:
                tank.outflow_cusecs = float(day.outflow_cusecs)
            discharge = day.discharge_cusecs if day.discharge_cusecs is not None else day.outflow_cusecs
            if discharge is not None:
                tank.discharge_cusecs = float(discharge)
            plc = self.plcs.get(asset_id)
            if plc is not None and day.gate_pct_derived is not None:
                plc.gate_cmd_pct = float(day.gate_pct_derived)
                plc.gate_pos_pct = float(day.gate_pct_derived)
                tank.gate_pct = plc.gate_pos_pct

    def _tick_series(self, now: datetime) -> TickResult:
        published: List[PublishReading] = []
        device_rows: List[Dict[str, Any]] = []
        divergences: List[Dict[str, Any]] = []
        dt_hours = self.sim_minutes / 60.0
        sim_time = (
            datetime.combine(self.cursor, time(12, 0), tzinfo=timezone.utc) if self.cursor else now
        )
        for spec in DEVICE_CATALOG:
            day = self._day(spec.asset_id)
            if day is None:
                continue
            official_at = self._official_at(day)
            quality_now = self._quality_now(official_at, now)
            mode = self.modes.get(spec.asset_id, "TRACK")
            if spec.kind == "PLC" and mode == "TRACK":
                mode = self._maybe_flip_track(spec.asset_id, day, dt_hours)
            if spec.kind == "PLC" and mode == "SCENARIO":
                reading, row, divergence = self._scenario_plc(spec, day, official_at, quality_now, dt_hours)
                if divergence:
                    divergences.append(divergence)
                    self.divergences[spec.asset_id] = divergence
            elif spec.kind == "RTU" and mode == "SCENARIO":
                reading, row = self._scenario_rtu(spec, day, official_at, quality_now)
            else:
                self.divergences.pop(spec.asset_id, None)
                reading, row = self._track_reading(spec, day, official_at, quality_now)
            published.append(reading)
            device_rows.append(row)
            if day.level_ft is not None:
                self._prev_level[spec.asset_id] = float(day.level_ft)
        return TickResult(
            sim_time=sim_time,
            published=published,
            devices=device_rows,
            divergences=divergences,
            cursor=self.cursor.isoformat() if self.cursor else None,
        )

    def _maybe_flip_track(self, asset_id: int, day: OfficialDay, dt_hours: float) -> str:
        plc = self.plcs[asset_id]
        derived = float(day.gate_pct_derived or plc.gate_cmd_pct)
        level = float(day.level_ft if day.level_ft is not None else plc.spec.normal_level_ft)
        prev = self._prev_level.get(asset_id, level)
        down_id = downstream_asset_id(asset_id)
        down_crit = self.plant.is_critical(down_id) if down_id else False
        decision = decide_interlocks(
            requested_cmd=derived,
            gate_pos=plc.gate_pos_pct,
            local_level=level,
            prev_level=prev,
            dt_hours=dt_hours,
            downstream_critical=down_crit,
            jammed=plc.jammed,
            comms_down=plc.comms_down,
        )
        if abs(decision.effective_cmd - derived) > GATE_MATCH_PCT or decision.freeze:
            self.modes[asset_id] = "SCENARIO"
            plc.gate_cmd_pct = decision.effective_cmd
            return "SCENARIO"
        return "TRACK"

    def _track_reading(self, spec, day: OfficialDay, official_at: datetime, quality_now: datetime):
        ai = {
            "level_ft": day.level_ft,
            "inflow_cusecs": day.inflow_cusecs,
            "outflow_cusecs": day.outflow_cusecs,
            "discharge_cusecs": day.discharge_cusecs if day.discharge_cusecs is not None else day.outflow_cusecs,
        }
        quality = "VALID"
        extras: Dict[str, Any] = {
            "source_authority": "SOFT_OT",
            "official_authority": day.source_authority,
            "official_on": day.observed_on.isoformat(),
            "mode": "TRACK",
        }
        if spec.kind == "RTU":
            rtu = self.rtus[spec.asset_id]
            if rtu.comms_down or rtu.sensor_stuck:
                quality = "SUSPECT"
            else:
                packets = rtu.scan(ai, now=quality_now, official_at=official_at)
                quality = packets[-1].quality if packets else "VALID"
            extras.update(comms_ok=not rtu.comms_down, power_ok=not rtu.power_fail)
        else:
            plc = self.plcs[spec.asset_id]
            extras.update(
                gate_pos_pct=plc.gate_pos_pct,
                gate_cmd_pct=plc.gate_cmd_pct,
                comms_ok=not plc.comms_down,
                actuator_fault=plc.jammed,
                reasons=[],
            )
            if plc.jammed or plc.comms_down:
                quality = "SUSPECT"
        reading = PublishReading(
            asset_id=spec.asset_id,
            device_code=spec.device_code,
            kind=spec.kind,
            observed_at=official_at,
            water_level_ft=ai["level_ft"],
            inflow_cusecs=ai["inflow_cusecs"],
            outflow_cusecs=ai["outflow_cusecs"],
            discharge_cusecs=ai["discharge_cusecs"],
            quality=quality,
            notes=self._with_anchor_note(f"{spec.kind.lower()}={spec.device_code}; mode=TRACK; official={day.source_authority}"),
            data_origin="OFFICIAL_REPLAY",
            extras=extras,
        )
        row = {
            "device_code": spec.device_code,
            "kind": spec.kind,
            "asset_id": spec.asset_id,
            "mode": "TRACK",
            "ai": {k: v for k, v in ai.items() if v is not None},
            "reasons": [],
        }
        return reading, row

    def _scenario_plc(self, spec, day: OfficialDay, official_at: datetime, quality_now: datetime, dt_hours: float):
        plc = self.plcs[spec.asset_id]
        level = float(day.level_ft if day.level_ft is not None else plc.spec.normal_level_ft)
        prev = self._prev_level.get(spec.asset_id, level)
        inflow = float(day.inflow_cusecs or 0.0)
        down_id = downstream_asset_id(spec.asset_id)
        down_crit = self.plant.is_critical(down_id) if down_id else False
        decision = decide_interlocks(
            requested_cmd=plc.gate_cmd_pct,
            gate_pos=plc.gate_pos_pct,
            local_level=level,
            prev_level=prev,
            dt_hours=dt_hours,
            downstream_critical=down_crit,
            jammed=plc.jammed,
            comms_down=plc.comms_down,
        )
        plc.gate_pos_pct = slew_gate(
            plc.gate_pos_pct,
            decision.effective_cmd,
            dt_hours,
            jammed=plc.jammed or decision.freeze,
        )
        rated = outflow_from_gate(
            plc.gate_pos_pct,
            level,
            spec.dead_level_ft,
            spec.normal_level_ft,
            spec.max_outflow_cusecs,
        )
        if spec.asset_id in BARRAGE_ASSET_IDS:
            outflow = barrage_release(inflow, day.canal_offtake_cusecs, rated)
        else:
            outflow = rated
        tank = self.plant.tanks[spec.asset_id]
        tank.inflow_cusecs = inflow
        tank.outflow_cusecs = outflow
        tank.discharge_cusecs = outflow
        tank.level_ft = level + (inflow - outflow) * dt_hours * spec.level_k
        lo = spec.dead_level_ft
        hi = (spec.critical_level_ft or spec.normal_level_ft) * 1.02
        tank.level_ft = max(lo, min(hi, tank.level_ft))
        tank.gate_pct = plc.gate_pos_pct
        age_h = (quality_now - official_at).total_seconds() / 3600.0
        quality = "SUSPECT" if (plc.jammed or plc.comms_down) else ("STALE" if age_h >= OFFICIAL_STALE_HOURS else "VALID")
        divergence = {
            "asset_id": spec.asset_id,
            "observed_on": day.observed_on.isoformat(),
            "official_outflow": day.outflow_cusecs,
            "scenario_outflow": round(outflow, 1),
            "official_gate_pct": day.gate_pct_derived,
            "scenario_gate_pct": round(plc.gate_pos_pct, 3),
            "reason": ",".join(decision.reasons) or "hmi_setpoint",
            "canal_note": canal_shortfall_note(day.outflow_cusecs, outflow, day.observed_on),
        }
        extras = {
            "source_authority": "SOFT_OT",
            "official_authority": day.source_authority,
            "official_on": day.observed_on.isoformat(),
            "mode": "SCENARIO",
            "gate_pos_pct": plc.gate_pos_pct,
            "gate_cmd_pct": plc.gate_cmd_pct,
            "comms_ok": not plc.comms_down,
            "actuator_fault": decision.fault,
            "freeze": decision.freeze,
            "reasons": decision.reasons,
            "official_outflow": day.outflow_cusecs,
        }
        reading = PublishReading(
            asset_id=spec.asset_id,
            device_code=spec.device_code,
            kind="PLC",
            observed_at=official_at,
            water_level_ft=round(tank.level_ft, 3),
            inflow_cusecs=round(inflow, 1),
            outflow_cusecs=round(outflow, 1),
            discharge_cusecs=round(outflow, 1),
            quality=quality,
            notes=self._with_anchor_note(
                f"plc={spec.device_code}; mode=SCENARIO; reasons={','.join(decision.reasons) or 'hmi_setpoint'}"
            ),
            data_origin="SCENARIO",
            extras=extras,
        )
        row = {
            "device_code": spec.device_code,
            "kind": "PLC",
            "asset_id": spec.asset_id,
            "mode": "SCENARIO",
            "gate_pos_pct": plc.gate_pos_pct,
            "gate_cmd_pct": plc.gate_cmd_pct,
            "reasons": decision.reasons,
            "ai": self.plant.as_ai(spec.asset_id),
        }
        return reading, row, divergence

    def _scenario_rtu(self, spec, day: OfficialDay, official_at: datetime, quality_now: datetime):
        ai = {
            "level_ft": day.level_ft if day.level_ft is not None else 0.0,
            "inflow_cusecs": day.inflow_cusecs if day.inflow_cusecs is not None else 0.0,
            "outflow_cusecs": day.outflow_cusecs if day.outflow_cusecs is not None else 0.0,
            "discharge_cusecs": day.discharge_cusecs if day.discharge_cusecs is not None else 0.0,
        }
        packets = self.rtus[spec.asset_id].scan(ai, now=quality_now, official_at=official_at)
        packet = packets[-1] if packets else None
        rtu = self.rtus[spec.asset_id]
        quality = packet.quality if packet else "SUSPECT"
        level = packet.water_level_ft if packet else ai["level_ft"]
        reading = PublishReading(
            asset_id=spec.asset_id,
            device_code=spec.device_code,
            kind="RTU",
            observed_at=official_at,
            water_level_ft=level,
            inflow_cusecs=ai["inflow_cusecs"],
            outflow_cusecs=ai["outflow_cusecs"],
            discharge_cusecs=ai["discharge_cusecs"],
            quality=quality,
            notes=self._with_anchor_note(f"rtu={spec.device_code}; mode=SCENARIO"),
            data_origin="SCENARIO",
            extras={
                "source_authority": "SOFT_OT",
                "official_authority": day.source_authority,
                "official_on": day.observed_on.isoformat(),
                "mode": "SCENARIO",
                "comms_ok": not rtu.comms_down,
                "power_ok": not rtu.power_fail,
            },
        )
        row = {
            "device_code": spec.device_code,
            "kind": "RTU",
            "asset_id": spec.asset_id,
            "mode": "SCENARIO",
            "comms_ok": not rtu.comms_down,
            "ai": ai,
            "reasons": ["sensor_stuck"] if rtu.sensor_stuck else ["comms_down"] if rtu.comms_down else [],
        }
        return reading, row

    def process_view(self) -> List[Dict[str, Any]]:
        rows = []
        for spec in DEVICE_CATALOG:
            day = self._day(spec.asset_id)
            live = self.plant.as_ai(spec.asset_id)
            mode = self.modes.get(spec.asset_id, "TRACK")
            plc = self.plcs.get(spec.asset_id)
            rtu = self.rtus.get(spec.asset_id)
            divergence = self.divergences.get(spec.asset_id)
            official_out = None if day is None else day.outflow_cusecs
            scenario_out = live["outflow_cusecs"] if mode == "SCENARIO" else official_out
            reasons: List[str] = []
            if divergence and divergence.get("reason") and divergence["reason"] != "hmi_setpoint":
                reasons = [part for part in str(divergence["reason"]).split(",") if part]
            if plc and plc.jammed:
                reasons.append("actuator_jam")
            if plc and plc.comms_down:
                reasons.append("comms_loss_hold_last_output")
            if rtu and rtu.comms_down:
                reasons.append("comms_down")
            if rtu and rtu.sensor_stuck:
                reasons.append("sensor_stuck")
            rows.append({
                "asset_id": spec.asset_id,
                "device_code": spec.device_code,
                "kind": spec.kind,
                "mode": mode,
                "comms_ok": (not plc.comms_down) if plc else (not rtu.comms_down if rtu else True),
                "official_on": day.observed_on.isoformat() if day else None,
                "official": None if day is None else day.as_csv_row(),
                "ot": {
                    "level_ft": live["level_ft"],
                    "inflow_cusecs": live["inflow_cusecs"],
                    "outflow_cusecs": live["outflow_cusecs"],
                    "discharge_cusecs": live["discharge_cusecs"],
                    "gate_cmd_pct": None if plc is None else plc.gate_cmd_pct,
                    "gate_pos_pct": None if plc is None else plc.gate_pos_pct,
                },
                "interlock_reasons": reasons,
                "official_outflow": official_out,
                "scenario_outflow": scenario_out,
                "divergence": divergence,
            })
        return rows

    def device_status(self) -> List[Dict[str, Any]]:
        rows = []
        for spec in DEVICE_CATALOG:
            ai = self.plant.as_ai(spec.asset_id)
            row: Dict[str, Any] = {
                "device_code": spec.device_code,
                "kind": spec.kind,
                "asset_id": spec.asset_id,
                "asset_name": spec.asset_name,
                "scan_ms": spec.scan_ms,
                "mode": self.modes.get(spec.asset_id, "TRACK"),
                "ai": ai,
            }
            if spec.asset_id in self.rtus:
                rtu = self.rtus[spec.asset_id]
                row.update(
                    comms_ok=not rtu.comms_down,
                    sensor_stuck=rtu.sensor_stuck,
                    buffered=len(rtu.buffer),
                )
            if spec.asset_id in self.plcs:
                plc = self.plcs[spec.asset_id]
                row.update(
                    gate_pos_pct=plc.gate_pos_pct,
                    gate_cmd_pct=plc.gate_cmd_pct,
                    comms_ok=not plc.comms_down,
                    actuator_fault=plc.jammed,
                )
            rows.append(row)
        return rows
