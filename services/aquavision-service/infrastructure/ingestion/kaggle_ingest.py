# infrastructure/ingestion/kaggle_ingest.py
# Ingest historical data from Kaggle "Pakistan's Rivers Flow" dataset.
# Source: https://www.kaggle.com/datasets/syedasimalishah/pakistans-rivers-flow-data-at-different-dams
#
# ~4.7 years of daily data for Tarbela, Mangla, Nowshera (Kabul), Marala (Chenab).
# Units: water level in feet, flows in 1000 cusecs (multiply by 1000).

import csv
import calendar
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterAsset, WaterObservation, WaterSource

logger = logging.getLogger("aquavision.ingest.kaggle")

COLUMN_MAP = {
    "Indus-Tarbela-Water-Level": ("Tarbela Reservoir", "water_level_ft"),
    "Indus-Tarbela-Inflow": ("Tarbela Reservoir", "inflow_cusecs"),
    "Indus-Tarbela-Outflow": ("Tarbela Reservoir", "outflow_cusecs"),
    "Kabul-Nowshera-Inflow": ("Kabul @ Nowshera", "discharge_cusecs"),
    "Jehlum-Mangla-Water-Level": ("Mangla Reservoir", "water_level_ft"),
    "Jehlum-Mangla-Inflow": ("Mangla Reservoir", "inflow_cusecs"),
    "Jehlum-Mangla-Outflow": ("Mangla Reservoir", "outflow_cusecs"),
    "Chenab-Marala-Inflow": ("Chenab @ Marala", "discharge_cusecs"),
}

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_kaggle_date(date_str: str, year: int) -> Optional[datetime]:
    parts = date_str.strip().split("-")
    if len(parts) != 2:
        return None
    day = int(parts[0])
    month = MONTHS.get(parts[1])
    if not month:
        return None
    max_day = calendar.monthrange(year, month)[1]
    day = min(day, max_day)
    return datetime(year, month, day, tzinfo=timezone.utc)


def ingest_kaggle_csv(csv_path: str, db: Session, start_year: int = 2022, end_year: int = 2026) -> Dict:
    source = db.execute(select(WaterSource).where(WaterSource.authority == "KAGGLE")).scalar_one_or_none()
    if not source:
        source = WaterSource(
            authority="KAGGLE",
            source_url="https://www.kaggle.com/datasets/syedasimalishah/pakistans-rivers-flow-data-at-different-dams",
            source_type="CSV", update_frequency="STATIC",
            description="Kaggle: Pakistan's Rivers Flow Data at different Dams",
        )
        db.add(source)
        db.flush()

    assets = {a.canonical_name: a.id for a in db.execute(select(WaterAsset)).scalars().all()}

    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    logger.info(f"Read {len(rows)} rows from Kaggle CSV")

    now = datetime.now(timezone.utc)

    # Pass 1: assign year to each row (data is newest-first, no year column)
    dated_rows = []
    current_year = end_year
    current_month = 12
    for row in rows:
        date_str = row.get("Date", "").strip()
        if not date_str:
            continue
        parts = date_str.split("-")
        if len(parts) != 2:
            continue
        month = MONTHS.get(parts[1])
        if not month:
            continue
        if month > current_month:
            current_year -= 1
        current_month = month
        if current_year < start_year:
            break
        obs_date = _parse_kaggle_date(date_str, current_year)
        if obs_date and obs_date > now:
            obs_date = _parse_kaggle_date(date_str, current_year - 1)
        if obs_date:
            dated_rows.append((row, obs_date))

    logger.info(f"Dated {len(dated_rows)} rows")

    # Pass 2: group fields by (asset_name, obs_date)
    grouped = {}
    for row, obs_date in dated_rows:
        for col_name, (asset_name, field) in COLUMN_MAP.items():
            value_str = row.get(col_name, "").strip()
            if not value_str or value_str == "0":
                continue
            try:
                value = float(value_str)
            except ValueError:
                continue
            if field in ("inflow_cusecs", "outflow_cusecs", "discharge_cusecs"):
                value = value * 1000
            key = (asset_name, obs_date)
            if key not in grouped:
                grouped[key] = {}
            grouped[key][field] = value

    logger.info(f"Grouped into {len(grouped)} observation slots")

    # Pass 3: insert/update
    stored = 0
    skipped = 0
    asset_counts = {}
    for (asset_name, obs_date), fields in grouped.items():
        asset_id = assets.get(asset_name)
        if not asset_id:
            continue
        existing = db.execute(
            select(WaterObservation).where(
                WaterObservation.asset_id == asset_id,
                WaterObservation.observed_at == obs_date,
            )
        ).scalar_one_or_none()
        if existing:
            for field, value in fields.items():
                if getattr(existing, field, None) is None:
                    setattr(existing, field, value)
            skipped += 1
        else:
            obs = WaterObservation(
                asset_id=asset_id, source_id=source.id, observed_at=obs_date,
                data_status="OBSERVED_OFFICIAL", data_origin="REAL",
                quality_status="VALID", quality_flag="KAGGLE_DATASET",
                source_authority="KAGGLE",
                source_priority=3,
                source_parser_version="kaggle_ingest_v1.0",
                **fields,
            )
            db.add(obs)
            stored += 1
            asset_counts[asset_name] = asset_counts.get(asset_name, 0) + 1

    db.commit()
    return {"total_rows": len(rows), "stored": stored, "skipped": skipped, "asset_counts": asset_counts}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/real/kaggle/pakistans_rivers_flow.csv"
    with SessionLocal() as db:
        result = ingest_kaggle_csv(csv_path, db)
        print(f"Kaggle ingestion: {result}")
