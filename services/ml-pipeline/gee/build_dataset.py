"""
gee/build_dataset.py
AquaVision - Join GEE region features with historical WAI labels from the DB.

- Reads Data/raw/region_features.csv (from gee_fetch.py)
- Reads labels from aquavision.water_indicators_weekly (wai_score, severity)
- Buckets weekly labels to their calendar month, re-keys every label one month
  earlier, then inner-joins on (region_id, month) so each row is
  (features at month t) -> (label at month t+1): the same one-month-ahead
  task predict_weekly serves (features at t -> WAI at t+1). The previous
  same-month join trained a same-month reconstruction, not a forecast.
- Keeps the observed WAI at month t as the current_wai INPUT feature (see
  wai_features.FEATURE_COLS): serving always has it, and it is the strongest
  predictor of next-month WAI.
- Writes Data/features/dataset.csv  (features + target)

Usage:
    python -m gee.build_dataset   (run from services/ml-pipeline)
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
    # observed WAI at month t, kept as an INPUT feature (before re-keying)
    current = labels[["region_id", "month", "wai_score"]].rename(
        columns={"wai_score": "current_wai"}
    )
    # Forecasting horizon: re-key each label to the month BEFORE it, so a
    # features row for month t joins the label computed for month t+1.
    # (Label M -> key M-1: features at t pick up wai(t+1).)
    labels["month"] = (
        pd.to_datetime(labels["month"]) - pd.DateOffset(months=1)
    ).dt.strftime("%Y-%m-%d")

    df = feats.merge(labels, on=["region_id", "month"], how="inner")
    df = df.merge(current, on=["region_id", "month"], how="inner")
    print(f"[build_dataset] inner join -> {len(df)} rows "
          f"(features at t -> label at t+1, current_wai = observed wai at t)")

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
