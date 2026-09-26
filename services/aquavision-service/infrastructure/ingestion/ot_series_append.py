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
    OfficialDay,
    canal_offtake_cusecs,
    complete_day,
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


def append_days(days: list[OfficialDay], path: Path = CSV_PATH) -> int:
    """Upsert official days into the OT CSV. Existing IRSA observation rows are not touched."""
    if not days:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    current = {(row["observed_on"], row["asset_id"]): row for row in _read_rows(path)}
    for day in days:
        row = complete_day(day).as_csv_row()
        current[(str(row["observed_on"]), str(row["asset_id"]))] = {key: row[key] for key in COLUMNS}
    ordered = sorted(current.values(), key=lambda row: (row["observed_on"], int(row["asset_id"])))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(ordered)
    return len(days)


def append_irsa_observations(observations: Iterable, target: date, source_url: str) -> dict:
    days = days_from_irsa_observations(observations, target, source_url)
    written = append_days(days)
    stored = 0
    try:
        from scripts.collect_ot_dataset import upsert_process_days
        stored = upsert_process_days(days)
    except Exception as exc:
        logger.warning("OT process table append skipped: %s", exc)
    return {"csv_rows": written, "stored": stored, "writes_observations": WRITES_OBSERVATIONS}
