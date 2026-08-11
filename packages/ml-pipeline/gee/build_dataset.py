"""
gee/build_dataset.py
AquaVision - Join GEE region features with historical WAI labels from the DB.

- Reads Data/raw/region_features.csv (from gee_fetch.py)
- Reads labels from aquavision.water_indicators_weekly (wai_score, severity)
- Buckets weekly labels to their calendar month and inner-joins on (region_id, month)
- Writes Data/features/dataset.csv  (features + target)

Usage:
    python -m gee.build_dataset   (run from packages/ml-pipeline)
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import pandas as pd

FEATURES_CSV = Path(__file__).resolve().parent.parent / "Data" / "raw" / "region_features.csv"
OUT_CSV = Path(__file__).resolve().parent.parent / "Data" / "features" / "dataset.csv"
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)

FEATURE_COLS = ["rainfall_mm", "et_mm", "water_extent", "ndvi"]
TARGET_COL = "wai_score"
SEVERITY_COL = "severity"


def load_labels() -> pd.DataFrame:
    """wai_score + severity per (region_id, month) from the DB."""
    import psycopg2

    conn = psycopg2.connect(DB_URL.replace("postgresql+psycopg2://", "postgresql://"))
    sql = """
        SELECT region_id,
               to_char(date_trunc('month', week_start_date), 'YYYY-MM-01') AS month,
               wai_score, severity
        FROM aquavision.water_indicators_weekly
        WHERE wai_score IS NOT NULL
        ORDER BY week_start_date
    """
    df = pd.read_sql(sql, conn)
    conn.close()
    print(f"[build_dataset] {len(df)} labeled rows from DB")
    return df


def build() -> None:
    feats = pd.read_csv(FEATURES_CSV)
    feats["month"] = feats["month"].astype(str).str.slice(0, 7) + "-01"
    # -1 sentinel (JRC no-data after 2022) -> NaN so models ignore it
    feats.loc[feats["water_extent"] == -1, "water_extent"] = float("nan")
    print(f"[build_dataset] {len(feats)} feature rows from GEE CSV")

    labels = load_labels()
    labels["month"] = labels["month"].astype(str).str.slice(0, 7) + "-01"

    df = feats.merge(labels, on=["region_id", "month"], how="inner")
    print(f"[build_dataset] inner join -> {len(df)} labeled rows")

    if df.empty:
        print("[build_dataset] WARNING: no overlap between GEE features and labels!")
        return

    # Add month index as a seasonality feature (1..12)
    df["month_idx"] = pd.to_datetime(df["month"]).dt.month

    df = df.dropna(subset=[TARGET_COL])
    df = df.sort_values(["region_id", "month"]).reset_index(drop=True)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"[build_dataset] Wrote {len(df)} rows -> {OUT_CSV}")
    print(f"[build_dataset] Columns: {list(df.columns)}")
    print(df[[TARGET_COL, SEVERITY_COL]].value_counts().to_string())


if __name__ == "__main__":
    build()
