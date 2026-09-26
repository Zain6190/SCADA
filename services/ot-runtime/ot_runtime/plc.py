# Soft PLC — local control scan, interlocks, command/feedback slew.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ot_runtime.catalog import DeviceSpec
from ot_runtime.interlocks import decide_interlocks, outflow_from_gate, slew_gate

LIMIT_OPEN_PCT = 98.0
LIMIT_CLOSED_PCT = 2.0


@dataclass
class PlcSnapshot:
    asset_id: int
    device_code: str
    observed_at: datetime
    water_level_ft: float
    inflow_cusecs: float
    outflow_cusecs: float
    discharge_cusecs: float
    gate_pos_pct: float
    gate_cmd_pct: float
    quality: str
    limit_open: bool
    limit_closed: bool
    actuator_fault: bool
    comms_ok: bool
    freeze: bool
    reasons: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class SoftPLC:
    spec: DeviceSpec
    gate_pos_pct: float = 40.0
    gate_cmd_pct: float = 40.0
    comms_down: bool = False
    jammed: bool = False
    last_level: Optional[float] = None

    def set_setpoint(self, pct: float) -> None:
        self.gate_cmd_pct = max(0.0, min(100.0, float(pct)))

    def scan(
        self,
        ai: Dict[str, float],
        dt_hours: float,
        downstream_critical: bool,
        now: Optional[datetime] = None,
    ) -> PlcSnapshot:
        now = now or datetime.now(timezone.utc)
        level = float(ai.get("level_ft", self.spec.normal_level_ft))
        inflow = float(ai.get("inflow_cusecs", self.spec.base_inflow_cusecs))
        prev = self.last_level if self.last_level is not None else level

        decision = decide_interlocks(
            requested_cmd=self.gate_cmd_pct,
            gate_pos=self.gate_pos_pct,
            local_level=level,
            prev_level=prev,
            dt_hours=dt_hours,
            downstream_critical=downstream_critical,
            jammed=self.jammed,
            comms_down=self.comms_down,
        )
        self.gate_pos_pct = slew_gate(
            self.gate_pos_pct,
            decision.effective_cmd,
            dt_hours,
            jammed=self.jammed or decision.freeze,
        )
        outflow = outflow_from_gate(
            self.gate_pos_pct,
            level,
            self.spec.dead_level_ft,
            self.spec.normal_level_ft,
            self.spec.max_outflow_cusecs,
        )
        self.last_level = level
        quality = "SUSPECT" if (self.jammed or self.comms_down) else "VALID"
        return PlcSnapshot(
            asset_id=self.spec.asset_id,
            device_code=self.spec.device_code,
            observed_at=now,
            water_level_ft=level,
            inflow_cusecs=inflow,
            outflow_cusecs=outflow,
            discharge_cusecs=outflow,
            gate_pos_pct=self.gate_pos_pct,
            gate_cmd_pct=self.gate_cmd_pct,
            quality=quality,
            limit_open=self.gate_pos_pct >= LIMIT_OPEN_PCT,
            limit_closed=self.gate_pos_pct <= LIMIT_CLOSED_PCT,
            actuator_fault=decision.fault,
            comms_ok=not self.comms_down,
            freeze=decision.freeze,
            reasons=decision.reasons,
            notes=f"plc={self.spec.device_code}; reasons={','.join(decision.reasons) or 'none'}",
        )

    def inject_fault(self, kind: str) -> None:
        if kind == "comms_down":
            self.comms_down = True
        elif kind == "actuator_jam":
            self.jammed = True
        else:
            raise ValueError(f"Unknown PLC fault '{kind}'")

    def clear_faults(self) -> None:
        self.comms_down = False
        self.jammed = False
