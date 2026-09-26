# Official Indus day used by the Soft OT twin.
# Gate percent is derived from published outflow. It is not a measured PLC register.
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from ot_runtime.catalog import DEVICE_BY_ASSET
from ot_runtime.interlocks import gate_from_outflow

GATE_MATCH_PCT = 0.5
BARRAGE_ASSET_IDS = frozenset({3, 4, 5, 6, 7, 8})
GAUGE_ASSET_IDS = frozenset({9, 10, 11})

ASSET_NAME_TO_ID = {
    "Tarbela Reservoir": 1,
    "Mangla Reservoir": 2,
    "Chashma Barrage": 3,
    "Kalabagh (Indus)": 4,
    "Kalabagh": 4,
    "Taunsa Barrage": 5,
    "Guddu Barrage": 6,
    "Sukkur Barrage": 7,
    "Kotri Barrage": 8,
    "Kabul @ Nowshera": 9,
    "Chenab @ Marala": 10,
    "Panjnad": 11,
}


@dataclass
class OfficialDay:
    observed_on: date
    asset_id: int
    level_ft: Optional[float] = None
    inflow_cusecs: Optional[float] = None
    outflow_cusecs: Optional[float] = None
    discharge_cusecs: Optional[float] = None
    canal_offtake_cusecs: float = 0.0
    gate_pct_derived: Optional[float] = None
    source_authority: str = "IRSA"
    source_url: str = ""
    device_code: str = ""

    def as_csv_row(self) -> Dict[str, Any]:
        return {
            "observed_on": self.observed_on.isoformat(),
            "asset_id": self.asset_id,
            "device_code": self.device_code,
            "level_ft": self.level_ft,
            "inflow_cusecs": self.inflow_cusecs,
            "outflow_cusecs": self.outflow_cusecs,
            "discharge_cusecs": self.discharge_cusecs,
            "canal_offtake_cusecs": self.canal_offtake_cusecs,
            "gate_pct_derived": self.gate_pct_derived,
            "source_authority": self.source_authority,
            "source_url": self.source_url,
        }


def canal_offtake_cusecs(withdrawals: Optional[Dict[str, float]]) -> float:
    """Prefer the report's Canal W/dls total. Otherwise sum the named canals."""
    if not withdrawals:
        return 0.0
    total = withdrawals.get("_total")
    if total is not None:
        return float(total)
    return float(sum(float(v) for k, v in withdrawals.items() if k != "_total" and v is not None))


def derive_gate_pct(asset_id: int, level_ft: Optional[float], outflow_cusecs: Optional[float]) -> Optional[float]:
    spec = DEVICE_BY_ASSET.get(asset_id)
    if spec is None or spec.kind != "PLC":
        return None
    if outflow_cusecs is None:
        return None
    level = level_ft if level_ft is not None else spec.normal_level_ft
    return round(
        gate_from_outflow(
            float(outflow_cusecs),
            float(level),
            spec.dead_level_ft,
            spec.normal_level_ft,
            spec.max_outflow_cusecs,
        ),
        3,
    )


def complete_day(day: OfficialDay) -> OfficialDay:
    spec = DEVICE_BY_ASSET.get(day.asset_id)
    if spec and not day.device_code:
        day.device_code = spec.device_code
    if day.discharge_cusecs is None:
        day.discharge_cusecs = day.outflow_cusecs if day.outflow_cusecs is not None else day.inflow_cusecs
    if day.gate_pct_derived is None:
        day.gate_pct_derived = derive_gate_pct(day.asset_id, day.level_ft, day.outflow_cusecs or day.discharge_cusecs)
    return day


def fill_gauge_from_ffd(
    day: OfficialDay,
    level_ft: Optional[float],
    discharge_cusecs: Optional[float],
    source_url: str = "",
) -> OfficialDay:
    """River stations take FFD level and discharge when the IRSA day has none."""
    if day.asset_id not in GAUGE_ASSET_IDS:
        return day
    filled = False
    if day.level_ft is None and level_ft is not None:
        day.level_ft = float(level_ft)
        filled = True
    if day.discharge_cusecs is None and discharge_cusecs is not None:
        day.discharge_cusecs = float(discharge_cusecs)
        if day.inflow_cusecs is None:
            day.inflow_cusecs = day.discharge_cusecs
        if day.outflow_cusecs is None:
            day.outflow_cusecs = day.discharge_cusecs
        filled = True
    if filled and day.source_authority == "IRSA" and day.level_ft is None:
        day.source_authority = "FFD"
    elif filled and day.level_ft is not None and day.source_authority == "IRSA" and level_ft is not None:
        day.source_authority = "IRSA+FFD"
    if filled and source_url and not day.source_url:
        day.source_url = source_url
    return day


def barrage_release(inflow_cusecs: Optional[float], offtake_cusecs: Optional[float], rated_cusecs: float) -> float:
    """River release is upstream arrival minus canal offtake, capped by the gate rating."""
    available = max(0.0, float(inflow_cusecs or 0.0) - float(offtake_cusecs or 0.0))
    return max(0.0, min(float(rated_cusecs), available))


def canal_shortfall_note(
    official_outflow: Optional[float],
    scenario_outflow: Optional[float],
    observed_on: date,
) -> Optional[str]:
    """Note only. Canal observation rows stay the official IRSA withdrawals."""
    if official_outflow is None or scenario_outflow is None:
        return None
    if scenario_outflow >= float(official_outflow) * 0.98:
        return None
    gap = float(official_outflow) - float(scenario_outflow)
    return (
        f"Soft OT scenario release is {gap:.0f} cusecs below the IRSA day {observed_on.isoformat()}. "
        "Canal withdrawals are unchanged."
    )


def flood_discharge(mode: str, official_discharge: Optional[float], scenario_discharge: Optional[float]):
    if mode == "SCENARIO" and scenario_discharge is not None:
        return scenario_discharge, "SOFT_OT_SCENARIO"
    return official_discharge, "OFFICIAL"


def ot_alert_candidates(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Alerts that name the device and the official day. They never replace IRSA alerts."""
    found: List[Dict[str, Any]] = []
    for row in rows:
        asset_id = int(row["asset_id"])
        device = row.get("device_code") or f"asset-{asset_id}"
        official_on = row.get("official_on") or ""
        reasons = list(row.get("interlock_reasons") or [])
        mode = row.get("mode") or "TRACK"
        if reasons:
            found.append({
                "asset_id": asset_id,
                "alert_type": "OT_INTERLOCK",
                "severity": "Warning",
                "message": (
                    f"{device} interlock on official day {official_on}: {', '.join(reasons)}. "
                    "This does not replace the IRSA alert."
                ),
                "active": True,
            })
        else:
            found.append({
                "asset_id": asset_id,
                "alert_type": "OT_INTERLOCK",
                "active": False,
            })
        if mode == "SCENARIO":
            official = row.get("official_outflow")
            scenario = row.get("scenario_outflow")
            found.append({
                "asset_id": asset_id,
                "alert_type": "OT_SCENARIO",
                "severity": "Watch",
                "message": (
                    f"{device} is in scenario on {official_on}. "
                    f"Official outflow {official} cusecs, scenario outflow {scenario} cusecs."
                ),
                "active": True,
            })
        else:
            found.append({
                "asset_id": asset_id,
                "alert_type": "OT_SCENARIO",
                "active": False,
            })
    return found


def parse_day(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
