# Device catalog for the software OT layer.
# Asset ids match aquavision.water_assets seed (1-11).
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

DeviceKind = Literal["RTU", "PLC"]
TagClass = Literal["AI", "DI", "AO", "DO"]


@dataclass(frozen=True)
class TagSpec:
    name: str
    tag_class: TagClass
    unit: str
    description: str


@dataclass(frozen=True)
class DeviceSpec:
    device_code: str
    kind: DeviceKind
    asset_id: int
    asset_name: str
    scan_ms: int
    publish_s: int
    dead_level_ft: float
    normal_level_ft: float
    warning_level_ft: Optional[float]
    critical_level_ft: Optional[float]
    max_outflow_cusecs: float
    level_k: float  # ft per (cusec * hour) — smaller for large reservoirs
    base_inflow_cusecs: float
    default_gate_pct: float
    tags: Tuple[TagSpec, ...] = field(default_factory=tuple)


RTU_TAGS = (
    TagSpec("AI.level_ft", "AI", "ft", "Gauge / reservoir level"),
    TagSpec("AI.inflow_cusecs", "AI", "cusecs", "Inflow"),
    TagSpec("AI.outflow_cusecs", "AI", "cusecs", "Outflow / release"),
    TagSpec("AI.discharge_cusecs", "AI", "cusecs", "River discharge"),
    TagSpec("DI.comms_ok", "DI", "bool", "Communications healthy"),
    TagSpec("DI.power_ok", "DI", "bool", "Site power healthy"),
)

PLC_TAGS = RTU_TAGS + (
    TagSpec("AI.gate_pos_pct", "AI", "pct", "Gate position feedback"),
    TagSpec("AO.gate_cmd_pct", "AO", "pct", "Gate setpoint from Virtual HMI"),
    TagSpec("DI.limit_open", "DI", "bool", "Open limit switch"),
    TagSpec("DI.limit_closed", "DI", "bool", "Closed limit switch"),
    TagSpec("DI.actuator_fault", "DI", "bool", "Command / feedback divergence or jam"),
    TagSpec("DO.gate_enable", "DO", "bool", "Internal enable — never published"),
)


def _rtu(
    code: str,
    asset_id: int,
    name: str,
    dead: float,
    normal: float,
    warning: Optional[float],
    critical: Optional[float],
    max_out: float,
    level_k: float,
    base_in: float,
) -> DeviceSpec:
    return DeviceSpec(
        device_code=code,
        kind="RTU",
        asset_id=asset_id,
        asset_name=name,
        scan_ms=15 * 60 * 1000,
        publish_s=15 * 60,
        dead_level_ft=dead,
        normal_level_ft=normal,
        warning_level_ft=warning,
        critical_level_ft=critical,
        max_outflow_cusecs=max_out,
        level_k=level_k,
        base_inflow_cusecs=base_in,
        default_gate_pct=40.0,
        tags=RTU_TAGS,
    )


def _plc(
    code: str,
    asset_id: int,
    name: str,
    dead: float,
    normal: float,
    warning: Optional[float],
    critical: Optional[float],
    max_out: float,
    level_k: float,
    base_in: float,
) -> DeviceSpec:
    return DeviceSpec(
        device_code=code,
        kind="PLC",
        asset_id=asset_id,
        asset_name=name,
        scan_ms=1000,
        publish_s=15,
        dead_level_ft=dead,
        normal_level_ft=normal,
        warning_level_ft=warning,
        critical_level_ft=critical,
        max_outflow_cusecs=max_out,
        level_k=level_k,
        base_inflow_cusecs=base_in,
        default_gate_pct=40.0,
        tags=PLC_TAGS,
    )


DEVICE_CATALOG: List[DeviceSpec] = [
    _rtu("RTU-TARBELA", 1, "Tarbela Reservoir", 1355, 1550, 1540, 1550, 250_000, 8e-7, 90_000),
    _rtu("RTU-MANGLA", 2, "Mangla Reservoir", 1040, 1242, 1235, 1242, 150_000, 1.2e-6, 45_000),
    _plc("PLC-CHASHMA", 3, "Chashma Barrage", 637, 648, 647, 648, 300_000, 4e-6, 85_000),
    _plc("PLC-KALABAGH", 4, "Kalabagh", 630, 640, 638, 640, 280_000, 4e-6, 80_000),
    _plc("PLC-TAUNSA", 5, "Taunsa Barrage", 490, 507, 505, 507, 250_000, 5e-6, 75_000),
    _plc("PLC-GUDDU", 6, "Guddu Barrage", 390, 404, 402, 404, 300_000, 5e-6, 70_000),
    _plc("PLC-SUKKUR", 7, "Sukkur Barrage", 255, 268, 266, 268, 250_000, 6e-6, 65_000),
    _plc("PLC-KOTRI", 8, "Kotri Barrage", 0, 10, 8, 10, 200_000, 8e-6, 55_000),
    _rtu("RTU-NOWSHERA", 9, "Kabul @ Nowshera", 0, 20, None, None, 80_000, 2e-5, 22_000),
    _rtu("RTU-MARALA", 10, "Chenab @ Marala", 0, 20, None, None, 90_000, 2e-5, 18_000),
    _rtu("RTU-PANJNAD", 11, "Panjnad", 0, 20, None, None, 70_000, 2e-5, 16_000),
]

# Indus / joining segments: (upstream_asset_id, downstream_asset_id, expected_hours)
TRAVEL_HOURS: List[Tuple[int, int, float]] = [
    (1, 4, 17.0),   # Tarbela -> Kalabagh
    (4, 5, 34.0),   # Kalabagh -> Taunsa
    (5, 6, 46.0),   # Taunsa -> Guddu
    (6, 7, 34.0),   # Guddu -> Sukkur
    (7, 8, 34.0),   # Sukkur -> Kotri
    (11, 6, 16.0),  # Panjnad joins Indus near Guddu
]

# Mangla is Jhelum; gauges are independent catchments (no Indus routing).

DEVICE_BY_ASSET: Dict[int, DeviceSpec] = {d.asset_id: d for d in DEVICE_CATALOG}
DEVICE_BY_CODE: Dict[str, DeviceSpec] = {d.device_code: d for d in DEVICE_CATALOG}

DOWNSTREAM_OF: Dict[int, int] = {up: down for up, down, _ in TRAVEL_HOURS}


def downstream_asset_id(asset_id: int) -> Optional[int]:
    return DOWNSTREAM_OF.get(asset_id)
