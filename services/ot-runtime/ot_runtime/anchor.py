# Map latest official IRSA / FFD rows onto VirtualPlant seed values.
# Pure functions — no database. Soft OT / USGS / BATADAL are never inputs.
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ot_runtime.catalog import DEVICE_BY_ASSET

RESERVOIR_IDS = frozenset({1, 2})
BARRAGE_IDS = frozenset({3, 4, 5, 6, 7, 8})
GAUGE_IDS = frozenset({9, 10, 11})
OFFICIAL_ASSET_IDS = RESERVOIR_IDS | BARRAGE_IDS | GAUGE_IDS
SKIP_AUTHORITIES = frozenset({"SOFT_OT", "USGS", "USGS/NWIS", "BATADAL", "KAGGLE"})


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _irsa_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    level = _num(row.get("water_level_ft") if "water_level_ft" in row else row.get("level_ft"))
    inflow = _num(row.get("inflow_cusecs"))
    outflow = _num(row.get("outflow_cusecs"))
    discharge = _num(row.get("discharge_cusecs"))
    upstream = _num(row.get("upstream_discharge_cusecs"))
    downstream = _num(row.get("downstream_discharge_cusecs"))
    if inflow is None:
        inflow = upstream
    if outflow is None:
        outflow = downstream
    if discharge is None:
        discharge = outflow if outflow is not None else inflow
    patch: Dict[str, Any] = {}
    if level is not None:
        patch["level_ft"] = level
    if inflow is not None:
        patch["inflow_cusecs"] = inflow
    if outflow is not None:
        patch["outflow_cusecs"] = outflow
    if discharge is not None:
        patch["discharge_cusecs"] = discharge
    if patch:
        patch["source"] = row.get("source") or row.get("source_authority") or "IRSA"
        patch["observed_at"] = _iso(row.get("observed_at"))
    return patch


def _ffd_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    level = _num(row.get("gauge_level_ft") if "gauge_level_ft" in row else row.get("level_ft"))
    discharge = _num(row.get("discharge_cusecs"))
    patch: Dict[str, Any] = {}
    if level is not None:
        patch["level_ft"] = level
    if discharge is not None:
        patch["discharge_cusecs"] = discharge
        patch["inflow_cusecs"] = discharge
        patch["outflow_cusecs"] = discharge
    if patch:
        patch["source"] = row.get("source") or "FFD"
        patch["observed_at"] = _iso(row.get("observed_at"))
    return patch


def _usable(row: Optional[Dict[str, Any]]) -> bool:
    if not row:
        return False
    authority = str(row.get("source_authority") or row.get("source") or "")
    return authority not in SKIP_AUTHORITIES


def map_official_anchor(
    irsa_by_asset: Dict[int, Dict[str, Any]],
    ffd_by_asset: Dict[int, Dict[str, Any]],
    asset_ids: Optional[Iterable[int]] = None,
) -> Dict[int, Dict[str, Any]]:
    """Latest official row per asset → plant seed dict.

    Reservoirs (1–2) and barrages (3–8) prefer IRSA. Gauges (9–11) prefer FFD,
    falling back to IRSA. Missing assets or null fields are omitted so the
    plant keeps catalog defaults / previous values.
    """
    ids = list(asset_ids) if asset_ids is not None else sorted(OFFICIAL_ASSET_IDS | set(DEVICE_BY_ASSET))
    out: Dict[int, Dict[str, Any]] = {}
    for asset_id in ids:
        irsa = irsa_by_asset.get(asset_id) if _usable(irsa_by_asset.get(asset_id)) else None
        ffd = ffd_by_asset.get(asset_id) if _usable(ffd_by_asset.get(asset_id)) else None
        patch: Dict[str, Any] = {}
        if asset_id in GAUGE_IDS:
            if irsa:
                patch.update(_irsa_fields(irsa))
            if ffd:
                overlay = _ffd_fields(ffd)
                patch.update(overlay)
        else:
            if irsa:
                patch.update(_irsa_fields(irsa))
        plant_keys = ("level_ft", "inflow_cusecs", "outflow_cusecs", "discharge_cusecs")
        if any(k in patch for k in plant_keys):
            out[int(asset_id)] = patch
    return out


def plant_states_only(anchor: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, float]]:
    """Drop provenance keys so VirtualPlant.apply_anchor only sees hydrology fields."""
    states: Dict[int, Dict[str, float]] = {}
    for asset_id, patch in anchor.items():
        hydro = {
            k: v
            for k, v in patch.items()
            if k in ("level_ft", "inflow_cusecs", "outflow_cusecs", "discharge_cusecs", "gate_pct")
            and v is not None
        }
        if hydro:
            states[int(asset_id)] = hydro
    return states


def summarize_anchor(anchor: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    dates = [p.get("observed_at") for p in anchor.values() if p.get("observed_at")]
    sources = sorted({str(p.get("source")) for p in anchor.values() if p.get("source")})
    latest = max(dates) if dates else None
    date_label = None
    if latest:
        date_label = str(latest)[:10]
    return {
        "applied": bool(anchor),
        "sources": sources,
        "observed_at": latest,
        "date": date_label,
        "asset_count": len(anchor),
        "banner": (
            f"Anchored to IRSA/FFD {date_label} — 15-minute values are simulated between reports"
            if date_label
            else "Not yet anchored to IRSA/FFD — catalog defaults until an official bulletin is loaded"
        ),
        "sensor_api_note": (
            "Live SENSOR_API 15-minute files stay a later optional AI input through existing ingest."
        ),
    }
