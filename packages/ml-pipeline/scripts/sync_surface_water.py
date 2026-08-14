"""
scripts/sync_surface_water.py
AquaVision - Sync surface water data from CSV into PostgreSQL.

Reads Data/raw/surface_water.csv and upserts into
aquavision.surface_water_weekly.

For each row:
  1. Look up previous week's water_area_km2 for the same region
  2. Calculate change_pct = ((current - previous) / previous) × 100
  3. Upsert into DB (insert or update on conflict)

Usage:
  python -m scripts.sync_surface_water [--csv PATH]
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
RAW_DIR = Path(__file__).resolve().parent.parent / "Data" / "raw"
CSV_PATH = RAW_DIR / "surface_water.csv"

SOURCE_VERSION = "S2-SR-HARMONIZED-2026.8"


def load_csv(path: Path) -> list[dict]:
    """Read surface_water.csv into list of dicts."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(
                {
                    "region_id": int(row["region_id"]),
                    "week_start_date": row["week_start_date"],
                    "ndwi_mean": _float_or_none(row.get("ndwi_mean")),
                    "mndwi_mean": _float_or_none(row.get("mndwi_mean")),
                    "water_area_km2": _float_or_none(row.get("water_area_km2")),
                    "cloud_pct": _float_or_none(row.get("cloud_pct")),
                }
            )
    return rows


def _float_or_none(val) -> float | None:
    if val in (None, "", "None", "null"):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def get_previous_water_area(engine, region_id: int, week_start: str) -> float | None:
    """Get water_area_km2 for the week immediately before the given week."""
    result = engine.execute(
        text(
            "SELECT water_area_km2 FROM aquavision.surface_water_weekly "
            "WHERE region_id = :rid AND week_start_date < :week "
            "ORDER BY week_start_date DESC LIMIT 1"
        ),
        {"rid": region_id, "week": week_start},
    ).fetchone()
    return result[0] if result else None


def upsert_row(engine, row: dict, prev_area: float | None) -> None:
    """Insert or update a single surface water record."""
    change_pct = None
    if prev_area is not None and prev_area > 0 and row["water_area_km2"] is not None:
        change_pct = ((row["water_area_km2"] - prev_area) / prev_area) * 100

    engine.execute(
        text(
            "INSERT INTO aquavision.surface_water_weekly "
            "(region_id, week_start_date, ndwi_mean, mndwi_mean, "
            " water_area_km2, prev_water_area_km2, change_pct, cloud_pct, "
            " data_status, source_version) "
            "VALUES "
            "(:region_id, :week_start_date, :ndwi_mean, :mndwi_mean, "
            " :water_area_km2, :prev_water_area, :change_pct, :cloud_pct, "
            " 'processed', :source_version) "
            "ON CONFLICT (region_id, week_start_date) DO UPDATE SET "
            " ndwi_mean = EXCLUDED.ndwi_mean, "
            " mndwi_mean = EXCLUDED.mndwi_mean, "
            " water_area_km2 = EXCLUDED.water_area_km2, "
            " prev_water_area_km2 = EXCLUDED.prev_water_area_km2, "
            " change_pct = EXCLUDED.change_pct, "
            " cloud_pct = EXCLUDED.cloud_pct, "
            " source_version = EXCLUDED.source_version"
        ),
        {
            "region_id": row["region_id"],
            "week_start_date": row["week_start_date"],
            "ndwi_mean": row["ndwi_mean"],
            "mndwi_mean": row["mndwi_mean"],
            "water_area_km2": row["water_area_km2"],
            "prev_water_area": prev_area,
            "change_pct": change_pct,
            "cloud_pct": row["cloud_pct"],
            "source_version": SOURCE_VERSION,
        },
    )


def run(csv_path: Path | None = None) -> dict:
    """Main sync: read CSV, compute change, upsert to DB."""
    path = csv_path or CSV_PATH
    if not path.exists():
        print(f"[sync_surface_water] CSV not found: {path}")
        return {"status": "error", "message": f"CSV not found: {path}"}

    rows = load_csv(path)
    print(f"[sync_surface_water] Loaded {len(rows)} rows from {path}")

    engine = create_engine(DB_URL, pool_pre_ping=True)
    inserted = 0
    updated = 0
    errors = 0

    with engine.begin() as conn:
        for row in rows:
            try:
                prev = get_previous_water_area(
                    conn, row["region_id"], row["week_start_date"]
                )
                upsert_row(conn, row, prev)
                if prev is not None:
                    updated += 1
                else:
                    inserted += 1
            except Exception as e:
                print(
                    f"[sync_surface_water] ERROR: region={row['region_id']} "
                    f"week={row['week_start_date']}: {e}"
                )
                errors += 1

    result = {
        "status": "success",
        "total": len(rows),
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
    }
    print(
        f"[sync_surface_water] Done: {inserted} inserted, "
        f"{updated} updated, {errors} errors"
    )
    return result


if __name__ == "__main__":
    csv_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(Path(csv_arg) if csv_arg else None)
