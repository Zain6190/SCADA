"""Batch ingest Kaggle data into Neon DB using psycopg2 COPY."""
import csv
import calendar
import io
import logging
from datetime import datetime, timezone
from typing import Optional

import os
import psycopg2
from psycopg2.extras import execute_values

NEON_URL = os.environ.get("DATABASE_URL", "")

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

INSERT_COLS = [
    "asset_id", "source_id", "observed_at", "data_status", "data_origin",
    "quality_status", "quality_flag", "source_authority", "source_priority",
    "source_parser_version", "water_level_ft", "inflow_cusecs", "outflow_cusecs",
    "discharge_cusecs",
]


def parse_date(date_str: str, year: int) -> Optional[datetime]:
    parts = date_str.strip().split("-")
    if len(parts) != 2:
        return None
    day = int(parts[0])
    month = MONTHS.get(parts[1])
    if not month:
        return None
    day = min(day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day, tzinfo=timezone.utc)


def ingest(csv_path: str, start_year: int = 2022, end_year: int = 2026):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("kaggle_neon")

    conn = psycopg2.connect(NEON_URL)
    cur = conn.cursor()

    # Ensure source
    cur.execute("SELECT id FROM aquavision.water_sources WHERE authority='KAGGLE'")
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO aquavision.water_sources (authority, source_url, source_type, update_frequency, description)
            VALUES ('KAGGLE', 'https://www.kaggle.com/datasets/syedasimalishah/pakistans-rivers-flow-data-at-different-dams',
                    'CSV', 'STATIC', 'Kaggle Pakistan Rivers Flow')
            RETURNING id
        """)
        source_id = cur.fetchone()[0]
    else:
        source_id = row[0]
    conn.commit()

    # Get assets
    cur.execute("SELECT id, canonical_name FROM aquavision.water_assets")
    assets = {r[1]: r[0] for r in cur.fetchall()}

    # Get existing keys
    cur.execute("SELECT asset_id, observed_at FROM aquavision.water_observations WHERE source_authority='KAGGLE'")
    existing = {(r[0], r[1]) for r in cur.fetchall()}
    logger.info(f"Source={source_id}, Assets={len(assets)}, Existing={len(existing)}")

    # Read CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    logger.info(f"Read {len(rows)} rows")

    now = datetime.now(timezone.utc)

    # Assign years (newest first)
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
        obs_date = parse_date(date_str, current_year)
        if obs_date and obs_date > now:
            obs_date = parse_date(date_str, current_year - 1)
        if obs_date:
            dated_rows.append((row, obs_date))

    logger.info(f"Dated {len(dated_rows)} rows")

    # Group by (asset, date)
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

    # Build batch rows
    new_rows = []
    for (asset_name, obs_date), fields in grouped.items():
        asset_id = assets.get(asset_name)
        if not asset_id:
            continue
        if (asset_id, obs_date) in existing:
            continue
        row_data = (
            asset_id, source_id, obs_date, "OBSERVED_OFFICIAL", "REAL",
            "VALID", "KAGGLE_DATASET", "KAGGLE", 3, "kaggle_ingest_v1.0",
            fields.get("water_level_ft"),
            fields.get("inflow_cusecs"),
            fields.get("outflow_cusecs"),
            fields.get("discharge_cusecs"),
        )
        new_rows.append(row_data)

    logger.info(f"New rows to insert: {len(new_rows)}")

    # Batch insert with execute_values
    batch_size = 1000
    inserted = 0
    for i in range(0, len(new_rows), batch_size):
        batch = new_rows[i:i+batch_size]
        cols_str = ", ".join(INSERT_COLS)
        execute_values(
            cur,
            f"INSERT INTO aquavision.water_observations ({cols_str}) VALUES %s ON CONFLICT DO NOTHING",
            batch,
            page_size=batch_size,
        )
        conn.commit()
        inserted += len(batch)
        logger.info(f"  Inserted {inserted}/{len(new_rows)}")

    # Summary
    cur.execute("""
        SELECT asset_id, count(*), min(observed_at)::date, max(observed_at)::date
        FROM aquavision.water_observations WHERE source_authority='KAGGLE'
        GROUP BY asset_id ORDER BY asset_id
    """)
    for r in cur.fetchall():
        logger.info(f"  Asset {r[0]}: {r[1]} obs ({r[2]} to {r[3]})")

    cur.execute("SELECT count(*) FROM aquavision.water_observations WHERE source_authority='KAGGLE'")
    total = cur.fetchone()[0]
    logger.info(f"Total KAGGLE observations in Neon: {total}")

    cur.close()
    conn.close()
    logger.info("DONE")


if __name__ == "__main__":
    import sys
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/real/kaggle/pakistans_rivers_flow.csv"
    ingest(csv_path)
