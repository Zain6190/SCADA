"""
scripts/predict_weekly.py
AquaVision - Serve the trained model: predict next-week WAI for all regions
and upsert into aquavision.water_predictions_weekly.

- Loads the latest regressor + interval artifacts (model version stamped in
  models/artifacts/metrics.json by the training run)
- Uses the latest month's GEE features + observed WAI as input; the
  regressor predicts the month-over-month delta, level = current_wai + delta
  (features at t -> WAI at t+1)
- Writes model_version, predicted_wai_score, predicted_severity, confidence

Usage:
    python -m scripts.predict_weekly   (run from services/ml-pipeline)
"""
from __future__ import annotations

import json
import os
import sys
from math import erf, sqrt
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

sys.path.insert(0, str(ML_ROOT))
from wai_features import (  # noqa: E402
    FEATURE_COLS,
    fetch_current_wai,
    fetch_known_regions,
)

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


_Z80 = 1.2816


def load_interval() -> dict | None:
    """Latest wai_interval_*.joblib, or None — serving then degrades to
    uninformative confidence (0.5) and NULL bounds instead of inventing one."""
    files = sorted(ARTIFACT_DIR.glob("wai_interval_*.joblib"))
    if not files:
        return None
    return joblib.load(files[-1])


def band_and_confidence(X, current, pred_delta, level, interval):
    """Calibrated [lo, hi] band (level scale) + honest per-row confidence.

    Band: quantile delta models +/- conformal inflation (residual +/- p80
    when quantiles are unavailable), clipped to the 0..100 WAI domain and
    forced to contain the point prediction.
    Confidence = P(|actual - pred| <= 10 WAI points) under a Gaussian whose
    sigma comes from the band half-width (half = 1.2816*sigma for an 80%
    band); 10 points is the scale at which a 15-wide severity bucket can
    flip. A documented Gaussian approximation on top of marginal conformal
    coverage — honest under exchangeability, degrades under regime shift.
    """
    n = len(X)
    if interval is None:
        print(
            "[predict_weekly] warning: no interval artifact; serving "
            "confidence=0.5 and NULL bounds"
        )
        return np.full(n, None), np.full(n, None), np.full(n, 0.5)
    if interval.get("q10") is not None:
        d_lo = interval["q10"].predict(X[FEATURE_COLS])
        d_hi = interval["q90"].predict(X[FEATURE_COLS])
        infl = float(interval.get("inflation", 0.0))
    else:
        p80 = float(interval["residual_p80"])
        d_lo = pred_delta - p80
        d_hi = pred_delta + p80
        infl = 0.0
    lo = np.clip(current + d_lo - infl, 0.0, 100.0)
    hi = np.clip(current + d_hi + infl, 0.0, 100.0)
    lo = np.minimum(lo, level)
    hi = np.maximum(hi, level)
    sigma = np.maximum((hi - lo) / 2.0 / _Z80, 1e-6)
    conf = np.clip([erf(10.0 / (s * sqrt(2.0))) for s in sigma], 0.05, 0.99)
    return lo, hi, np.asarray(conf)


def served_model_version() -> str:
    """Version stamped by the latest training run - metrics.json is the single
    source of truth (stale stamp would mislabel rows the same way twice)."""
    try:
        data = json.loads((ARTIFACT_DIR / "metrics.json").read_text(encoding="utf-8"))
        version = data.get("model_version")
        if version:
            return str(version)
    except (OSError, ValueError):
        pass
    return os.getenv("GEE_MODEL_VERSION", "xgb-v1.1")


def predict_one_month_ahead() -> None:
    reg = joblib.load(latest_artifact("wai_reg_*.joblib"))

    feats = pd.read_csv(RAW_CSV)
    feats["month"] = pd.to_datetime(feats["month"])
    latest_month = feats["month"].max()
    X = feats[feats["month"] == latest_month].copy()
    if X.empty:
        raise RuntimeError(f"No GEE features for latest month {latest_month}")
    # only regions the app registered (FK on water_predictions_weekly)
    known = fetch_known_regions(_engine())
    skipped = int((~X["region_id"].isin(known)).sum())
    X = X[X["region_id"].isin(known)].copy()
    if skipped:
        print(
            f"[predict_weekly] skipped {skipped} feature rows for unregistered "
            f"regions (not in shared.regions)"
        )
    if X.empty:
        raise RuntimeError("No feature rows for registered regions")

    # month_idx = season of the INPUT month, matching how build_dataset
    # trains (features at t -> WAI at t+1, month_idx from month t)
    X["month_idx"] = latest_month.month
    X.loc[X["water_extent"] == -1, "water_extent"] = float("nan")
    for col in [
        "rainfall_mm",
        "et_mm",
        "water_extent",
        "ndvi",
        "sm_rootzone",
        "sm_surface",
    ]:
        X[col] = X[col].fillna(feats[col].median())
    # feature contract: observed WAI at/before the input month (the regressor
    # predicts the delta against it; regions with no history yet fall back to
    # the cross-region median rather than NaN)
    X["current_wai"] = X["region_id"].map(fetch_current_wai(_engine(), latest_month))
    missing = int(X["current_wai"].isna().sum())
    if missing:
        X["current_wai"] = X["current_wai"].fillna(X["current_wai"].median())
        print(
            f"[predict_weekly] note: {missing} regions lack observed WAI history "
            f"-> current_wai filled with cross-region median"
        )
    if X["current_wai"].isna().any():
        raise RuntimeError("current_wai unavailable for every region; cannot serve")

    current = X["current_wai"].to_numpy()
    pred_delta = reg.predict(X[FEATURE_COLS])
    pred_wai = np.clip(current + pred_delta, 0.0, 100.0)
    # severity via the same threshold buckets used for labels
    pred_sev = np.array([_classify(float(v)) for v in pred_wai])
    lo, hi, conf = band_and_confidence(
        X, current, pred_delta, pred_wai, load_interval()
    )

    rows = [
        {
            "region_id": int(r.region_id),
            "wai": round(float(w), 2),
            "sev": s,
            "conf": round(float(c), 3),
            "lo": None if l is None else round(float(l), 2),
            "hi": None if h is None else round(float(h), 2),
        }
        for r, w, s, c, l, h in zip(
            X.itertuples(), pred_wai, pred_sev, conf, lo, hi
        )
    ]

    upsert_preds(
        rows,
        model_version=served_model_version(),
        target_month=latest_month + pd.DateOffset(months=1),
    )
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
                         predicted_severity, predicted_wai_score, confidence,
                         lower_bound, upper_bound)
                    VALUES
                        (:region_id, :target_date, 'XGBoost', :model_version,
                         :severity, :wai, :conf, :lo, :hi)
                    ON CONFLICT (region_id, target_week_start_date, model_version)
                    DO UPDATE SET predicted_severity = EXCLUDED.predicted_severity,
                                  predicted_wai_score = EXCLUDED.predicted_wai_score,
                                  confidence = EXCLUDED.confidence,
                                  lower_bound = EXCLUDED.lower_bound,
                                  upper_bound = EXCLUDED.upper_bound
                    """
                ),
                {
                    "region_id": row["region_id"],
                    "target_date": target_date,
                    "model_version": model_version,
                    "severity": row["sev"],
                    "wai": row["wai"],
                    "conf": row["conf"],
                    "lo": row["lo"],
                    "hi": row["hi"],
                },
            )
    print(
        f"[predict_weekly] Upserted into aquavision.water_predictions_weekly "
        f"for target {target_date}"
    )


if __name__ == "__main__":
    predict_one_month_ahead()
