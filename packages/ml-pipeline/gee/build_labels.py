"""
gee/build_labels.py
AquaVision - Path B: derive Water Availability Index (WAI) labels from GEE data.

No external labels needed. The WAI is a transparent, reproducible composite of
the GEE features we already fetched (per-region normalized so regions are
comparable), then discretized into the same severity buckets the seed uses.

Also builds a FORECASTING task:
    features at month t  ->  label = WAI at month t+1
so the model is genuinely predicting one month ahead, and the test set is held
out chronologically (last 20% of time) -> honest, measurable accuracy.

Usage:
    python -m gee.build_labels   (run from packages/ml-pipeline)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

RAW_CSV = Path(__file__).resolve().parent.parent / "Data" / "raw" / "region_features.csv"
OUT_CSV = Path(__file__).resolve().parent.parent / "Data" / "features" / "dataset.csv"

FEATURE_COLS = ["rainfall_mm", "et_mm", "water_extent", "ndvi"]
# weight of each component in the WAI (must sum to 1)
WEIGHTS = {"rainfall_mm": 0.35, "ndvi": 0.30, "water_extent": 0.20, "et_mm": 0.15}
HORIZON_MONTHS = 1


def classify(wai: float) -> str:
    if wai < 25:
        return "Critical"
    if wai < 40:
        return "Severe"
    if wai < 55:
        return "Stressed"
    if wai < 70:
        return "Moderate"
    return "Normal"


def compute_wai(df: pd.DataFrame) -> pd.DataFrame:
    """Per-region min-max normalize each available feature, then weight-mean.

    water_extent is missing (JRC ends ~2021) for most years; weights are
    renormalized over the components present in each row so the WAI stays
    0-100 across the full 5-year record.
    """
    df = df.copy()
    # -1 sentinel (JRC no-data after ~2021) -> NaN
    df.loc[df["water_extent"] == -1, "water_extent"] = float("nan")

    for col in FEATURE_COLS:
        if col == "et_mm":
            df[col + "_norm"] = 1.0 - _minmax(df[col])
        else:
            df[col + "_norm"] = _minmax(df[col])

    # weighted mean over available (non-NaN) components per row
    norm_cols = [c + "_norm" for c in FEATURE_COLS]
    present = df[norm_cols].notna()
    w = pd.Series([WEIGHTS[c] for c in FEATURE_COLS], index=norm_cols)
    w_avail = present.multiply(w, axis=1)          # weight where present
    w_sum = w_avail.sum(axis=1).replace(0, np.nan)  # total weight used
    df["wai_score"] = (df[norm_cols].fillna(0).multiply(w_avail, axis=1).sum(axis=1) / w_sum) * 100.0
    df["severity"] = df["wai_score"].apply(classify)
    return df


def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.5, index=s.index)
    return (s - lo) / (hi - lo)


def build() -> None:
    feats = pd.read_csv(RAW_CSV)
    feats["month"] = pd.to_datetime(feats["month"])
    print(f"[build_labels] {len(feats)} region-months from GEE")

    labeled = compute_wai(feats)

    # ---- build forecasting target: WAI one month ahead ----
    labeled = labeled.sort_values(["region_id", "month"])
    labeled["target_wai"] = labeled.groupby("region_id")["wai_score"].shift(-HORIZON_MONTHS)
    labeled["target_severity"] = labeled.groupby("region_id")["severity"].shift(-HORIZON_MONTHS)
    labeled["month_idx"] = labeled["month"].dt.month

    # keep only rows that have a future target
    pred = labeled.dropna(subset=["target_wai"]).copy()
    pred = pred.rename(columns={"wai_score": "current_wai", "severity": "current_severity"})
    pred["wai_score"] = pred["target_wai"]
    pred["severity"] = pred["target_severity"]

    out_cols = [
        "region_id",
        "month",
        "month_idx",
        "rainfall_mm",
        "et_mm",
        "water_extent",
        "ndvi",
        "current_wai",
        "current_severity",
        "wai_score",   # label = next month WAI
        "severity",    # label = next month severity
    ]
    pred = pred[out_cols].reset_index(drop=True)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pred.to_csv(OUT_CSV, index=False)
    print(f"[build_labels] Wrote {len(pred)} forecasting rows -> {OUT_CSV}")
    print(f"[build_labels] Time range: {pred['month'].min().date()} .. {pred['month'].max().date()}")
    print(f"[build_labels] Severity distribution:\n{pred['severity'].value_counts().to_string()}")


if __name__ == "__main__":
    build()
