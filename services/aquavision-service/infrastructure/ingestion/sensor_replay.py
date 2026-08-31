# infrastructure/ingestion/sensor_replay.py
# Replay public SCADA telemetry (BATADAL C-Town) through the sensor ingest API.
#
# Purpose: AquaVision's official sources (IRSA, FFD/PMD) publish once per day.
# Several threshold rules - notably RATE_OF_CHANGE, which looks back 6 hours -
# cannot behave as designed at that cadence: the 6h lookback resolves to the
# previous day's reading, so a ~24h change gets compared against a 6h threshold.
# Replaying hourly telemetry exercises those rules properly.
#
# BATADAL is a SIMULATED water-distribution network, not Pakistani hydrology.
# Every row is written with data_origin=SYNTHETIC / data_status=SIMULATED and
# source_priority=4, so it can never displace the official record in
# aquavision.v_best_observations.
#
# Source: https://www.batadal.net/data.html  (BATADAL_dataset03.csv = clean year)
#
# Usage:
#   python -m infrastructure.ingestion.sensor_replay --csv BATADAL_dataset03.csv
#   python -m infrastructure.ingestion.sensor_replay --csv <f> --days 14 --dry-run

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import requests

logger = logging.getLogger("aquavision.sensor_replay")

# ─── Constants ─────────────────────────────────────────────────────────────

DEFAULT_API = "http://127.0.0.1:8100/water/sensors/ingest"
SOURCE_AUTHORITY = "SENSOR_REPLAY"
BATCH_SIZE = 100  # SensorBatchRequest caps readings at 100

# BATADAL is metric (level/pressure in metres, flow in LPS); AquaVision is
# imperial throughout. Direct conversion is documented here for reference, but
# the replay does NOT use it - see TankMapping for why both level and flow are
# rescaled onto each asset's operating band instead.
#   metres -> feet   : x 3.28084
#   LPS    -> cusecs : / 28.3168

# Deterministic replay anchor. Timestamps are rebased onto a window ending at
# this instant so (a) readings are recent enough not to trip DATA_STALENESS and
# (b) re-running the replay produces the SAME timestamps, which the endpoint's
# (asset_id, observed_at, source_id) uniqueness turns into clean duplicate
# rejections rather than a second copy of the series.
ANCHOR = datetime(2026, 8, 31, 0, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class TankMapping:
    """Maps one BATADAL tank onto an AquaVision asset.

    BATADAL is a municipal distribution network: tanks hold a few metres of
    water and pumps move a few hundred litres per second. Tarbela sits near
    1550 ft and passes hundreds of thousands of cusecs. A raw unit conversion
    therefore produces values that are either rejected by the ingest range check
    (water_level_ft > 2000) or so small no threshold can ever fire - a 120 LPS
    pump becomes 4.2 cusecs of inflow at Tarbela.

    So BOTH level and flow are rescaled: we borrow the SHAPE of each signal and
    map it onto the asset's real operating band.
    """
    tank_col: str          # e.g. "L_T1"
    asset_id: int
    asset_name: str
    band_low_ft: float     # maps to the tank's observed minimum
    band_high_ft: float    # maps to the tank's observed maximum
    flow_low_cusecs: float
    flow_high_cusecs: float
    inflow_col: Optional[str] = None
    outflow_col: Optional[str] = None


# Level bands come from db/seed.sql: dead_level_ft -> just above warning_level_ft,
# so a replayed peak reaches WARNING without permanently pinning every asset at
# CRITICAL. Flow bands are typical monsoon-season operating ranges for each
# structure. Asset ids 9-11 are river stations with no level thresholds and are
# fed by the USGS adapter instead.
TANK_MAPPINGS: List[TankMapping] = [
    TankMapping("L_T1", 1, "Tarbela Reservoir", 1355.0, 1545.0,
                20_000, 250_000, "F_PU1", "F_PU2"),
    TankMapping("L_T2", 2, "Mangla Reservoir", 1040.0, 1238.0,
                10_000, 150_000, "F_PU4", "F_PU5"),
    TankMapping("L_T3", 3, "Chashma Barrage", 637.0, 647.5,
                20_000, 300_000, "F_PU6", "F_PU7"),
    TankMapping("L_T4", 5, "Taunsa Barrage", 490.0, 506.0,
                15_000, 250_000, "F_PU8", "F_PU9"),
    TankMapping("L_T5", 6, "Guddu Barrage", 390.0, 403.0,
                15_000, 300_000, "F_PU10", "F_PU11"),
    TankMapping("L_T6", 7, "Sukkur Barrage", 255.0, 267.0,
                10_000, 250_000, "F_PU1", "F_PU3"),
    TankMapping("L_T7", 8, "Kotri Barrage", 0.5, 9.0,
                5_000, 200_000, "F_PU2", "F_PU5"),
]


# ─── CSV parsing ───────────────────────────────────────────────────────────

def _normalise_header(row: Dict[str, str]) -> Dict[str, str]:
    """BATADAL ships with leading spaces in several column names."""
    return {(k or "").strip(): v for k, v in row.items()}


def load_batadal(csv_path: Path) -> List[Dict[str, str]]:
    """Read a BATADAL CSV into a list of header-normalised rows."""
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        rows = [_normalise_header(r) for r in csv.DictReader(fh)]
    if not rows:
        raise ValueError(f"{csv_path} contained no data rows")
    logger.info("Loaded %d rows from %s", len(rows), csv_path.name)
    logger.info("Columns: %s", ", ".join(sorted(rows[0].keys())))
    return rows


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def column_range(rows: List[Dict[str, str]], column: str) -> Optional[tuple]:
    """Observed (min, max) for a column, or None if absent/empty."""
    values = [v for v in (_to_float(r.get(column)) for r in rows) if v is not None]
    if not values:
        return None
    return min(values), max(values)


def rescale(value: float, src_lo: float, src_hi: float, dst_lo: float, dst_hi: float) -> float:
    """Linear rescale of a source range onto a target operating band."""
    if src_hi - src_lo < 1e-9:
        return (dst_lo + dst_hi) / 2.0
    frac = (value - src_lo) / (src_hi - src_lo)
    return dst_lo + frac * (dst_hi - dst_lo)


# ─── Reading construction ──────────────────────────────────────────────────

def build_readings(
    rows: List[Dict[str, str]],
    mappings: List[TankMapping] = None,
    days: Optional[int] = None,
) -> List[dict]:
    """Convert BATADAL rows into sensor-API reading payloads.

    Timestamps are rebased so the LAST row lands on ANCHOR and each preceding
    row steps back one hour (BATADAL is hourly).
    """
    mappings = mappings or TANK_MAPPINGS

    # Normalise here as well as in load_batadal: this function is called
    # directly by tests and callers that did not go through the CSV loader, and
    # a stray leading space silently drops that column's readings.
    rows = [_normalise_header(r) for r in rows]

    if days is not None:
        keep = min(len(rows), days * 24)
        rows = rows[-keep:]
        logger.info("Limited to last %d rows (%d days)", len(rows), days)

    # Precompute each column's observed range once, over the rows being replayed.
    ranges: Dict[str, tuple] = {}
    for m in mappings:
        rng = column_range(rows, m.tank_col)
        if rng is None:
            logger.warning("Column %s not found or empty - skipping asset %s",
                           m.tank_col, m.asset_name)
            continue
        ranges[m.tank_col] = rng
        for flow_col in (m.inflow_col, m.outflow_col):
            if flow_col and flow_col not in ranges:
                flow_rng = column_range(rows, flow_col)
                if flow_rng is not None:
                    ranges[flow_col] = flow_rng

    n = len(rows)
    readings: List[dict] = []

    for idx, row in enumerate(rows):
        # last row -> ANCHOR, walking backwards one hour per row
        observed_at = ANCHOR - timedelta(hours=(n - 1 - idx))

        for m in mappings:
            if m.tank_col not in ranges:
                continue
            raw_level = _to_float(row.get(m.tank_col))
            if raw_level is None:
                continue

            src_lo, src_hi = ranges[m.tank_col]
            level_ft = round(
                rescale(raw_level, src_lo, src_hi, m.band_low_ft, m.band_high_ft), 2
            )

            reading = {
                "asset_id": m.asset_id,
                "timestamp": observed_at.isoformat(),
                "water_level_ft": level_ft,
                "sensor_id": f"BATADAL_{m.tank_col}",
                "quality": "VALID",
                # Provenance: this is a replayed simulation, not a measurement
                # taken on this asset. Never REAL.
                "origin": "SYNTHETIC",
                "status": "SIMULATED",
            }

            for col, field in ((m.inflow_col, "inflow_cusecs"),
                               (m.outflow_col, "outflow_cusecs")):
                if not col or col not in ranges:
                    continue
                raw_flow = _to_float(row.get(col))
                if raw_flow is None or raw_flow < 0:
                    continue
                f_lo, f_hi = ranges[col]
                reading[field] = round(
                    rescale(raw_flow, f_lo, f_hi, m.flow_low_cusecs, m.flow_high_cusecs), 1
                )

            readings.append(reading)

    n_assets = len({r["asset_id"] for r in readings})
    logger.info("Built %d readings across %d assets, %s -> %s",
                len(readings), n_assets,
                (ANCHOR - timedelta(hours=n - 1)).isoformat(), ANCHOR.isoformat())
    return readings


def batches(readings: List[dict], size: int = BATCH_SIZE) -> Iterator[List[dict]]:
    for i in range(0, len(readings), size):
        yield readings[i:i + size]


# ─── POST loop ─────────────────────────────────────────────────────────────

def post_readings(
    readings: List[dict],
    api_url: str = DEFAULT_API,
    api_key: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """POST readings in batches. Returns an aggregate summary.

    NOTE: every accepted batch triggers evaluate_all_assets() server-side. A
    full-year replay is ~600 batches and therefore ~600 threshold sweeps - run
    this against a LOCAL database, not a deployed one.
    """
    total = {"accepted": 0, "rejected": 0, "batches": 0, "failed_batches": 0}
    batch_list = list(batches(readings))

    if dry_run:
        logger.info("DRY RUN - %d readings in %d batches, nothing sent",
                    len(readings), len(batch_list))
        if batch_list:
            logger.info("First reading: %s", batch_list[0][0])
        total["batches"] = len(batch_list)
        return total

    for i, batch in enumerate(batch_list, start=1):
        payload = {"source": SOURCE_AUTHORITY, "readings": batch}
        if api_key:
            payload["api_key"] = api_key
        try:
            resp = requests.post(api_url, json=payload, timeout=60)
            resp.raise_for_status()
            body = resp.json()
            total["accepted"] += body.get("accepted", 0)
            total["rejected"] += body.get("rejected", 0)
            total["batches"] += 1
            if i % 25 == 0 or i == len(batch_list):
                logger.info("batch %d/%d - accepted=%d rejected=%d",
                            i, len(batch_list), total["accepted"], total["rejected"])
        except Exception as exc:  # noqa: BLE001 - one bad batch must not kill the replay
            total["failed_batches"] += 1
            logger.error("batch %d/%d failed: %s", i, len(batch_list), exc)

    return total


def replay(
    csv_path: Path,
    api_url: str = DEFAULT_API,
    days: Optional[int] = None,
    api_key: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Full pipeline: load CSV -> convert + rescale -> rebase -> POST."""
    rows = load_batadal(csv_path)
    readings = build_readings(rows, days=days)
    summary = post_readings(readings, api_url=api_url, api_key=api_key, dry_run=dry_run)
    summary["readings_built"] = len(readings)
    logger.info("Replay complete: %s", summary)
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Replay BATADAL SCADA telemetry through the AquaVision sensor API"
    )
    parser.add_argument("--csv", required=True, help="Path to a BATADAL CSV")
    parser.add_argument("--api", default=DEFAULT_API, help=f"Ingest URL (default {DEFAULT_API})")
    parser.add_argument("--days", type=int, default=None,
                        help="Replay only the last N days (hourly rows)")
    parser.add_argument("--api-key", default=None, help="API key, if configured")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build and report readings without sending")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"CSV not found: {path}")

    replay(path, api_url=args.api, days=args.days,
           api_key=args.api_key, dry_run=args.dry_run)
