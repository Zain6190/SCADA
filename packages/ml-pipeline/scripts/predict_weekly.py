"""
scripts/predict_weekly.py
AquaVision - Serve the trained model: predict next-week WAI for all regions
and upsert into aquavision.water_predictions_weekly.

- Loads latest artifact (wai_reg_xgb-v1.0.joblib + severity encoder)
- Uses the latest month's GEE features as the input (features at t -> WAI at t+1)
- Writes model_version, predicted_wai_score, predicted_severity, confidence

Usage:
    python -m scripts.predict_weekly   (run from packages/ml-pipeline)
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ML_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ML_ROOT / "models" / "artifacts"
RAW_CSV = ML_ROOT / "Data" / "raw" / "region_features.csv"
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
FEATURE_COLS = ["rainfall_mm", "et_mm", "water_extent", "ndvi", "month_idx"]

DB_ENGINE = None


def _engine():
    global DB_ENGINE
    if DB_ENGINE is None:
        from sqlalchemy import create_engine

        DB_ENGINE = create_engine(DB_URL)
    return DB_ENGINE


def latest_artifact(pattern: str) -> Path:
    files = sorted(ARTIFACT_DIR.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No artifact matching {pattern} in {ARTIFACT_DIR}")
    return files[-1]


def predict_one_month_ahead() -> None:
    reg = joblib.load(latest_artifact("wai_reg_*.joblib"))
    # classifier used only for confidence proxy; severity derived from WAI thresholds
    le = joblib.load(latest_artifact("severity_encoder_*.joblib"))

    feats = pd.read_csv(RAW_CSV)
    feats["month"] = pd.to_datetime(feats["month"])
    latest_month = feats["month"].max()
    X = feats[feats["month"] == latest_month].copy()
    if X.empty:
        raise RuntimeError(f"No GEE features for latest month {latest_month}")

    # next month index for seasonality feature
    next_month_idx = (latest_month + pd.DateOffset(months=1)).month
    X["month_idx"] = next_month_idx
    X.loc[X["water_extent"] == -1, "water_extent"] = float("nan")
    for col in ["rainfall_mm", "et_mm", "water_extent", "ndvi"]:
        X[col] = X[col].fillna(feats[col].median())

    pred_wai = reg.predict(X[FEATURE_COLS])
    # severity via the same threshold buckets used for labels
    pred_sev = np.array([_classify(float(v)) for v in pred_wai])
    # confidence: 1 - scaled distance from nearest class boundary (proxy)
    conf = np.clip(1.0 - np.abs(pred_wai - np.round(pred_wai)) / 25.0, 0.5, 0.99)

    rows = [
        {
            "region_id": int(r.region_id),
            "wai": round(float(w), 2),
            "sev": s,
            "conf": round(float(c), 3),
        }
        for r, w, s, c in zip(X.itertuples(), pred_wai, pred_sev, conf)
    ]

    upsert_preds(rows, model_version="xgb-v1.0", target_month=latest_month + pd.DateOffset(months=1))
    print(f"[predict_weekly] Read {len(feats)} rows")
    print(f"[predict_weekly] Wrote {len(rows)} predictions for {target_str(latest_month)}")


def target_str(latest_month) -> str:
    return (latest_month + pd.DateOffset(months=1)).strftime("%Y-%m")


def _classify(wai: float) -> str:
    if wai < 25:
        return "Critical"
    if wai < 40:
        return "Severe"
    if wai < 55:
        return "Stressed"
    if wai < 70:
        return "Moderate"
    return "Normal"


def upsert_preds(rows: list[dict], model_version: str, target_month) -> None:
    eng = _engine()
    target_date = target_month.strftime("%Y-%m-01")
    with eng.begin() as conn:
        for row in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO aquavision.water_predictions_weekly
                        (region_id, target_week_start_date, model_type, model_version,
                         predicted_severity, predicted_wai_score, confidence)
                    VALUES
                        (:region_id, :target_date, 'XGBoost', :model_version,
                         :severity, :wai, :conf)
                    ON CONFLICT (region_id, target_week_start_date, model_version)
                    DO UPDATE SET predicted_severity = EXCLUDED.predicted_severity,
                                  predicted_wai_score = EXCLUDED.predicted_wai_score,
                                  confidence = EXCLUDED.confidence
                    """
                ),
                {
                    "region_id": row["region_id"],
                    "target_date": target_date,
                    "model_version": model_version,
                    "severity": row["sev"],
                    "wai": row["wai"],
                    "conf": row["conf"],
                },
            )
    print(
        f"[predict_weekly] Upserted into aquavision.water_predictions_weekly "
        f"for target {target_date}"
    )


if __name__ == "__main__":
    predict_one_month_ahead()
