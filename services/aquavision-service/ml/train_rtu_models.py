# ml/train_rtu_models.py
# Train on REAL RTU telemetry exported from USGS NWIS.
#
# Why this exists: AquaVision's Pakistani sources are too thin to train on.
# IRSA publishes a ~12-day rolling window (verified: dates before it 404), and
# the local archive holds 29 days - fewer than the 30-day lag the feature
# builder needs. USGS NWIS instantaneous values are genuine remote-terminal-unit
# output at 15-minute cadence with a decade of history, freely available.
#
# Nothing here is simulated. Every row carries data_origin=REAL and the site
# that produced it. These models learn RTU signal BEHAVIOUR - diurnal cycles,
# rise/fall dynamics, sensor dropout - not Indus hydrology. That distinction
# belongs in the write-up.
#
# Input:  data/raw/real/usgs/*.csv  (see infrastructure/ingestion/usgs_nwis.py --export-csv)
# Output: ml/artifacts/rtu_*.joblib + rtu_metrics.json
#
# Usage:
#   python -m infrastructure.ingestion.usgs_nwis --export-csv data/raw/real/usgs/rtu.csv \
#          --start 2022-01-01 --require-both
#   python -m ml.train_rtu_models --csv data/raw/real/usgs/rtu.csv

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("aquavision.ml.rtu")

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"

# Lags in SAMPLES, not days: at 15-minute cadence 4 samples = 1 hour.
LAG_STEPS = [1, 4, 24, 96]          # 15 min, 1 h, 6 h, 24 h
ROLL_WINDOWS = [4, 24, 96]          # 1 h, 6 h, 24 h
HORIZON_STEPS = 24                  # predict 6 hours ahead
RESAMPLE = "15min"
CONTAMINATION = 0.02


def load_corpus(csv_path: Path) -> pd.DataFrame:
    """Load the exported real-telemetry CSV and assert its provenance."""
    # site_no MUST be read as text: USGS site numbers carry leading zeros
    # (05331000), and letting pandas infer int silently renames every site.
    df = pd.read_csv(csv_path, dtype={"site_no": str})
    if "data_origin" in df.columns:
        origins = set(df["data_origin"].dropna().unique())
        if origins != {"REAL"}:
            raise ValueError(
                f"Refusing to train: corpus contains non-REAL rows {origins - {'REAL'}}. "
                "This trainer is for real telemetry only."
            )
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True, format="ISO8601")
    df = df.sort_values(["site_no", "observed_at"])
    logger.info("Loaded %d real readings from %d sites (%s .. %s)",
                len(df), df["site_no"].nunique(),
                df["observed_at"].min(), df["observed_at"].max())
    return df


def build_features(site_df: pd.DataFrame) -> pd.DataFrame:
    """Lag / rolling / rate-of-change features on a regular 15-minute grid.

    Resampling first matters: raw NWIS series contain gaps (sensor outages,
    ice-affected periods), and lagging an irregular index silently mislabels
    "1 hour ago" as whatever the previous surviving row happened to be.
    """
    s = (site_df.set_index("observed_at")[["water_level_ft", "discharge_cusecs"]]
         .resample(RESAMPLE).mean())

    out = pd.DataFrame(index=s.index)
    out["level"] = s["water_level_ft"]
    out["discharge"] = s["discharge_cusecs"]

    for col in ("level", "discharge"):
        for lag in LAG_STEPS:
            out[f"{col}_lag_{lag}"] = out[col].shift(lag)
        for win in ROLL_WINDOWS:
            out[f"{col}_mean_{win}"] = out[col].rolling(win).mean()
            out[f"{col}_std_{win}"] = out[col].rolling(win).std()
        # Rate of change is the signal the 6-hour threshold rule is built on.
        out[f"{col}_roc_1h"] = out[col].diff(4)
        out[f"{col}_roc_6h"] = out[col].diff(24)

    idx = out.index
    out["hour_sin"] = np.sin(2 * np.pi * idx.hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * idx.hour / 24)
    out["doy_sin"] = np.sin(2 * np.pi * idx.dayofyear / 365)
    out["doy_cos"] = np.cos(2 * np.pi * idx.dayofyear / 365)

    # Forecast target: level HORIZON_STEPS ahead (6 h at 15-minute cadence).
    out["target_level"] = out["level"].shift(-HORIZON_STEPS)
    return out


def chronological_split(df: pd.DataFrame, test_fraction: float = 0.2):
    """Split by time, never randomly - a random split leaks the future."""
    cut = int(len(df) * (1 - test_fraction))
    return df.iloc[:cut], df.iloc[cut:]


def train_forecaster(feats: pd.DataFrame, site_no: str) -> dict:
    """Gradient-boosted 6-hour-ahead level forecast, evaluated out-of-time."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, r2_score

    data = feats.dropna(subset=["target_level"])
    feature_cols = [c for c in data.columns if c != "target_level"]
    data = data.dropna(subset=feature_cols, thresh=len(feature_cols) - 4)
    if len(data) < 5000:
        logger.warning("  %s: only %d usable rows - skipping forecaster", site_no, len(data))
        return {}

    train, test = chronological_split(data)
    X_tr, y_tr = train[feature_cols], train["target_level"]
    X_te, y_te = test[feature_cols], test["target_level"]

    model = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.08, max_depth=8, random_state=42
    )
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)

    # Persistence baseline: assume the level 6 h from now equals the level now.
    # A model that cannot beat this has learned nothing about the dynamics.
    baseline_mae = mean_absolute_error(y_te, test["level"])
    mae = mean_absolute_error(y_te, pred)

    metrics = {
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "mae_ft": round(float(mae), 4),
        "rmse_ft": round(float(np.sqrt(np.mean((y_te - pred) ** 2))), 4),
        "r2": round(float(r2_score(y_te, pred)), 4),
        "persistence_mae_ft": round(float(baseline_mae), 4),
        "skill_vs_persistence": round(float(1 - mae / baseline_mae), 4),
        "horizon_hours": HORIZON_STEPS / 4,
    }
    logger.info("  %s forecast: MAE %.3f ft vs persistence %.3f (skill %+.1f%%)",
                site_no, mae, baseline_mae, 100 * metrics["skill_vs_persistence"])

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump({"model": model, "features": feature_cols},
                ARTIFACT_DIR / f"rtu_forecast_{site_no}.joblib")
    return metrics


def train_anomaly(feats: pd.DataFrame, site_no: str) -> dict:
    """IsolationForest over real telemetry dynamics."""
    from sklearn.ensemble import IsolationForest

    cols = ["level", "discharge", "level_roc_1h", "level_roc_6h",
            "discharge_roc_1h", "discharge_roc_6h",
            "level_std_24", "discharge_std_24"]
    cols = [c for c in cols if c in feats.columns]
    data = feats[cols].dropna()
    if len(data) < 5000:
        logger.warning("  %s: only %d usable rows - skipping anomaly model", site_no, len(data))
        return {}

    train, _ = chronological_split(data)
    model = IsolationForest(n_estimators=200, contamination=CONTAMINATION,
                            random_state=42, n_jobs=-1)
    model.fit(train)
    flags = model.predict(data)
    rate = float((flags == -1).mean())

    logger.info("  %s anomaly: %d/%d flagged (%.2f%%)",
                site_no, int((flags == -1).sum()), len(data), 100 * rate)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump({"model": model, "features": cols},
                ARTIFACT_DIR / f"rtu_anomaly_{site_no}.joblib")
    return {"n_train": int(len(train)), "n_scored": int(len(data)),
            "anomaly_rate": round(rate, 4), "contamination": CONTAMINATION}


def main(csv_path: Path) -> dict:
    df = load_corpus(csv_path)
    report = {"source": str(csv_path), "data_origin": "REAL",
              "cadence": RESAMPLE, "sites": {}}

    for site_no, site_df in df.groupby("site_no"):
        logger.info("Site %s: %d readings", site_no, len(site_df))
        feats = build_features(site_df)
        report["sites"][str(site_no)] = {
            "readings": int(len(site_df)),
            "grid_rows": int(len(feats)),
            "forecast": train_forecaster(feats, str(site_no)),
            "anomaly": train_anomaly(feats, str(site_no)),
        }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / "rtu_metrics.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Wrote metrics -> %s", out)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train models on real USGS RTU telemetry")
    parser.add_argument("--csv", required=True, help="Exported real-telemetry CSV")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"CSV not found: {path}")
    main(path)
