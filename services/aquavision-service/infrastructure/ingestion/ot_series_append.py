# Append one official IRSA day onto the Soft OT series.
# Does not write or update water_observations.
from __future__ import annotations

import csv
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("aquavision.ot.series")

REPO = Path(__file__).resolve().parents[4]
OT_ROOT = REPO / "services" / "ot-runtime"
if str(OT_ROOT) not in sys.path:
    sys.path.insert(0, str(OT_ROOT))

from ot_runtime.series import (  # noqa: E402
    ASSET_NAME_TO_ID,
    GAUGE_ASSET_IDS,
    OfficialDay,
    canal_offtake_cusecs,
    complete_day,
    fill_gauge_from_ffd,
)

CSV_PATH = REPO / "data" / "ot" / "indus_ot_daily.csv"
COLUMNS = [
    "observed_on",
    "asset_id",
    "device_code",
    "level_ft",
    "inflow_cusecs",
    "outflow_cusecs",
    "discharge_cusecs",
    "canal_offtake_cusecs",
    "gate_pct_derived",
    "source_authority",
    "source_url",
]
WRITES_OBSERVATIONS = False


def days_from_irsa_observations(observations: Iterable, target: date, source_url: str) -> list[OfficialDay]:
    found: dict[int, OfficialDay] = {}
    for obs in observations:
        asset_id = ASSET_NAME_TO_ID.get(getattr(obs, "asset_name", ""))
        if asset_id is None:
            continue
        inflow = obs.inflow_cusecs if obs.inflow_cusecs is not None else obs.upstream_discharge_cusecs
        outflow = obs.outflow_cusecs if obs.outflow_cusecs is not None else obs.downstream_discharge_cusecs
        discharge = obs.discharge_cusecs if obs.discharge_cusecs is not None else outflow
        found[asset_id] = complete_day(OfficialDay(
            observed_on=target,
            asset_id=asset_id,
            level_ft=obs.water_level_ft,
            inflow_cusecs=inflow,
            outflow_cusecs=outflow,
            discharge_cusecs=discharge,
            canal_offtake_cusecs=canal_offtake_cusecs(getattr(obs, "canal_withdrawals", None)),
            source_authority="IRSA",
            source_url=source_url,
        ))
    return list(found.values())


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_current(current: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(current.values(), key=lambda row: (row["observed_on"], int(row["asset_id"])))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(ordered)


def _num(value):
    if value is None or value == "":
        return None
    return float(value)


def _day_from_row(row: dict) -> OfficialDay:
    return OfficialDay(
        observed_on=date.fromisoformat(str(row["observed_on"])[:10]),
        asset_id=int(row["asset_id"]),
        level_ft=_num(row.get("level_ft")),
        inflow_cusecs=_num(row.get("inflow_cusecs")),
        outflow_cusecs=_num(row.get("outflow_cusecs")),
        discharge_cusecs=_num(row.get("discharge_cusecs")),
        canal_offtake_cusecs=float(row.get("canal_offtake_cusecs") or 0),
        gate_pct_derived=_num(row.get("gate_pct_derived")),
        source_authority=row.get("source_authority") or "IRSA",
        source_url=row.get("source_url") or "",
        device_code=row.get("device_code") or "",
    )


def _store_days(days: list[OfficialDay]) -> int:
    if not days:
        return 0
    try:
        from scripts.collect_ot_dataset import upsert_process_days
        return upsert_process_days(days)
    except Exception as exc:
        logger.warning("OT process table append skipped: %s", exc)
        return 0


def _refresh_runtime() -> None:
    try:
        from infrastructure.ot.persist import refresh_process_series
        refresh_process_series()
    except Exception as exc:
        logger.warning("OT series refresh skipped: %s", exc)


def append_days(days: list[OfficialDay], path: Path = CSV_PATH) -> int:
    """Upsert official days into the OT CSV. Existing IRSA observation rows are not touched."""
    if not days:
        return 0
    current = {(row["observed_on"], str(row["asset_id"])): row for row in _read_rows(path)}
    for day in days:
        row = complete_day(day).as_csv_row()
        current[(str(row["observed_on"]), str(row["asset_id"]))] = {key: row[key] for key in COLUMNS}
    _write_current(current, path)
    return len(days)


def append_irsa_observations(observations: Iterable, target: date, source_url: str) -> dict:
    days = days_from_irsa_observations(observations, target, source_url)
    written = append_days(days)
    stored = _store_days(days)
    if written:
        _refresh_runtime()
    return {"csv_rows": written, "stored": stored, "writes_observations": WRITES_OBSERVATIONS}


def append_ffd_observations(observations: Iterable, target: date, source_url: str, path: Path = CSV_PATH) -> dict:
    """Fill gauge level and discharge on the official day. IRSA fields on that row stay."""
    current = {(row["observed_on"], str(row["asset_id"])): row for row in _read_rows(path)}
    updated: list[OfficialDay] = []
    for obs in observations:
        asset_id = getattr(obs, "asset_id", None)
        if asset_id is None:
            name = getattr(obs, "station_name", None) or getattr(obs, "canonical_name", "") or ""
            asset_id = ASSET_NAME_TO_ID.get(name)
        if asset_id not in GAUGE_ASSET_IDS:
            continue
        key = (target.isoformat(), str(asset_id))
        if key in current:
            day = _day_from_row(current[key])
        else:
            day = OfficialDay(
                observed_on=target,
                asset_id=int(asset_id),
                source_authority="FFD",
                source_url=source_url,
            )
        fill_gauge_from_ffd(
            day,
            getattr(obs, "gauge_level_ft", None),
            getattr(obs, "discharge_cusecs", None),
            source_url,
        )
        day = complete_day(day)
        row = day.as_csv_row()
        current[key] = {key_name: row[key_name] for key_name in COLUMNS}
        updated.append(day)
    if not updated:
        return {"csv_rows": 0, "stored": 0, "writes_observations": WRITES_OBSERVATIONS}
    _write_current(current, path)
    stored = _store_days(updated)
    _refresh_runtime()
    return {"csv_rows": len(updated), "stored": stored, "writes_observations": WRITES_OBSERVATIONS}
