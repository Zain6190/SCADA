"""
Prediction Persistence Service — Loads models, runs predictions, writes to DB.
Fixes: hybrid feature gathering, inflow fallback, missingness flags.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np

logger = logging.getLogger("prediction_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_BASE_DIR = Path(os.environ.get("AQUAVISION_BASE_DIR", "/app"))
ASSET_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
HORIZONS = [7, 14, 30]
MODEL_DIR = _BASE_DIR / "models" / "flood_xgb"


def get_db():
    from infrastructure.db.engine import engine
    return engine


def load_model(asset_id: int, horizon: int):
    """Load a trained FloodPredictor model from disk."""
    path = MODEL_DIR / f"{asset_id}_{horizon}.joblib"
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception as e:
        logger.error(f"Failed to load model for asset {asset_id} horizon {horizon}d: {e}")
        return None


def get_latest_with_inflow(asset_id: int, conn):
    """Get most recent observation that has inflow data (IRSA or Kaggle)."""
    from sqlalchemy import text
    row = conn.execute(text("""
        SELECT wo.observed_at, wo.inflow_cusecs, wo.outflow_cusecs,
               wo.discharge_cusecs, wo.water_level_ft, ds.authority as source
        FROM aquavision.water_observations wo
        JOIN aquavision.water_sources ds ON ds.id = wo.source_id
        WHERE wo.asset_id = :aid
          AND wo.inflow_cusecs IS NOT NULL
        ORDER BY wo.observed_at DESC
        LIMIT 1
    """), {"aid": asset_id}).mappings().first()
    return dict(row) if row else None


def get_latest_discharge(asset_id: int, conn):
    """Get most recent observation with discharge (FFD)."""
    from sqlalchemy import text
    row = conn.execute(text("""
        SELECT wo.observed_at, wo.discharge_cusecs, wo.water_level_ft,
               ds.authority as source
        FROM aquavision.water_observations wo
        JOIN aquavision.water_sources ds ON ds.id = wo.source_id
        WHERE wo.asset_id = :aid
          AND wo.discharge_cusecs IS NOT NULL
        ORDER BY wo.observed_at DESC
        LIMIT 1
    """), {"aid": asset_id}).mappings().first()
    return dict(row) if row else None


def get_rolling_median_inflow(asset_id: int, conn, days=30):
    """Get rolling median inflow for fallback (last N days)."""
    from sqlalchemy import text
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    row = conn.execute(text("""
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY inflow_cusecs) as median_inflow
        FROM aquavision.water_observations
        WHERE asset_id = :aid
          AND inflow_cusecs IS NOT NULL
          AND observed_at >= :cutoff
    """), {"aid": asset_id, "cutoff": cutoff}).mappings().first()
    if row and row["median_inflow"]:
        return float(row["median_inflow"])
    return None


def get_rolling_median_outflow(asset_id: int, conn, days=30):
    """Get rolling median outflow for fallback."""
    from sqlalchemy import text
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    row = conn.execute(text("""
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY outflow_cusecs) as median_outflow
        FROM aquavision.water_observations
        WHERE asset_id = :aid
          AND outflow_cusecs IS NOT NULL
          AND observed_at >= :cutoff
    """), {"aid": asset_id, "cutoff": cutoff}).mappings().first()
    if row and row["median_outflow"]:
        return float(row["median_outflow"])
    return None


def get_hybrid_features(asset_id: int, conn):
    """Build hybrid feature set using the best available data.
    
    Strategy:
    1. Get latest observation WITH inflow (IRSA/Kaggle) — for inflow features
    2. Get latest observation WITH discharge (FFD) — for level/discharge if newer
    3. Merge: inflow from #1, level/discharge from #2 if newer
    4. If no inflow at all: use rolling median + inflow_missing=1
    """
    from sqlalchemy import text

    inflow_obs = get_latest_with_inflow(asset_id, conn)
    discharge_obs = get_latest_discharge(asset_id, conn)

    features = {
        "inflow": None,
        "outflow": None,
        "discharge": None,
        "level": None,
        "inflow_missing": 0,
        "source_inflow": None,
        "source_level": None,
    }

    # --- Inflow: prefer IRSA/Kaggle (has inflow) ---
    if inflow_obs and inflow_obs.get("inflow_cusecs"):
        features["inflow"] = float(inflow_obs["inflow_cusecs"])
        features["outflow"] = float(inflow_obs["outflow_cusecs"]) if inflow_obs.get("outflow_cusecs") else None
        features["source_inflow"] = inflow_obs.get("source", "UNKNOWN")
        # Use level from inflow obs as baseline
        if inflow_obs.get("water_level_ft"):
            features["level"] = float(inflow_obs["water_level_ft"])

    # --- Discharge: use FFD if it has newer level/discharge ---
    if discharge_obs and discharge_obs.get("discharge_cusecs"):
        features["discharge"] = float(discharge_obs["discharge_cusecs"])
        features["source_level"] = discharge_obs.get("source", "UNKNOWN")
        # Update level from FFD if it's newer than inflow obs
        if discharge_obs.get("water_level_ft"):
            ffd_date = discharge_obs["observed_at"]
            inf_date = inflow_obs["observed_at"] if inflow_obs else None
            if inf_date is None or (ffd_date and ffd_date > inf_date):
                features["level"] = float(discharge_obs["water_level_ft"])

    # --- Fallback: if inflow still missing, use rolling median ---
    if features["inflow"] is None:
        median_inflow = get_rolling_median_inflow(asset_id, conn)
        if median_inflow:
            features["inflow"] = median_inflow
            features["inflow_missing"] = 1
            logger.warning(f"Asset {asset_id}: inflow missing, using rolling median {median_inflow:.0f}")
        else:
            features["inflow"] = 0.0
            features["inflow_missing"] = 1
            logger.error(f"Asset {asset_id}: no inflow data and no median available")

    # --- Fallback: outflow missing ---
    if features["outflow"] is None:
        median_outflow = get_rolling_median_outflow(asset_id, conn)
        if median_outflow:
            features["outflow"] = median_outflow
        else:
            features["outflow"] = features["inflow"] * 0.95  # approximate

    # --- Fallback: level missing ---
    if features["level"] is None:
        # Use discharge as rough proxy for level (not ideal but better than 0)
        if features["discharge"]:
            features["level"] = features["discharge"] / 1000.0  # rough approximation
        else:
            features["level"] = 0.0

    # --- Fallback: discharge missing ---
    if features["discharge"] is None:
        if features["inflow"]:
            features["discharge"] = features["inflow"] * 0.98  # approximate steady state
        else:
            features["discharge"] = 0.0

    return features


def get_asset_thresholds(asset_id: int, conn):
    """Fetch warning/danger levels for an asset."""
    from sqlalchemy import text
    row = conn.execute(text("""
        SELECT warning_level_ft, critical_level_ft
        FROM aquavision.water_assets
        WHERE id = :aid
    """), {"aid": asset_id}).mappings().first()
    return dict(row) if row else None


def predict_and_persist(asset_id: int, horizon: int, model_data: dict, conn):
    """Run a single prediction and write it to water_predictions."""
    from sqlalchemy import text

    model = model_data.get("model")
    scaler = model_data.get("scaler")
    feature_names = model_data.get("feature_names", [])
    metrics = model_data.get("metrics", {})
    log_transform = model_data.get("log_transform", False)

    if not model or not scaler:
        return None

    # Get hybrid features (inflow-aware, with fallbacks)
    features = get_hybrid_features(asset_id, conn)
    if not features:
        logger.warning(f"No features for asset {asset_id}")
        return None

    thresholds = get_asset_thresholds(asset_id, conn) or {}
    if thresholds.get("warning_level_ft"):
        thresholds["warning_level_ft"] = float(thresholds["warning_level_ft"])
    if thresholds.get("critical_level_ft"):
        thresholds["critical_level_ft"] = float(thresholds["critical_level_ft"])

    # Build feature vector — fill model features from our hybrid features
    X = np.zeros((1, len(feature_names)))
    filled = []
    missing = []

    for i, fname in enumerate(feature_names):
        if fname in features and features[fname] is not None:
            X[0, i] = features[fname]
            filled.append(fname)
        elif fname == "inflow_missing":
            X[0, i] = features.get("inflow_missing", 0)
            filled.append(fname)
        else:
            missing.append(fname)

    if missing:
        logger.info(f"Asset {asset_id} horizon {horizon}d: missing features: {missing}")

    # Predict
    try:
        X_scaled = scaler.transform(X)
        pred_raw = model.predict(X_scaled)[0]

        if log_transform:
            pred_value = float(np.expm1(pred_raw))
        else:
            pred_value = float(pred_raw)

        # Prediction interval (residual-based)
        residual_std = float(metrics.get("rmse", pred_value * 0.2))
        lower = float(max(0, pred_value - 1.96 * residual_std))
        upper = float(pred_value + 1.96 * residual_std)

    except Exception as e:
        logger.error(f"Prediction failed for asset {asset_id} horizon {horizon}d: {e}")
        return None

    # Risk scoring
    warning_level = thresholds.get("warning_level_ft")
    critical_level = thresholds.get("critical_level_ft")
    risk_score = 0
    risk_category = "NORMAL"
    exceeds_warning = False
    exceeds_danger = False

    if warning_level and pred_value > 0:
        pct_of_warning = pred_value / warning_level * 100
        risk_score = min(100, int(pct_of_warning))
        exceeds_warning = pred_value >= warning_level
        exceeds_danger = critical_level and pred_value >= critical_level

        if risk_score >= 80:
            risk_category = "CRITICAL"
        elif risk_score >= 60:
            risk_category = "WARNING"
        elif risk_score >= 40:
            risk_category = "WATCH"
        else:
            risk_category = "NORMAL"

    # Compute valid_from/to
    now = datetime.now(timezone.utc)
    valid_from = now
    valid_to = now + timedelta(days=horizon)

    # Feature importance (top 5)
    fi = {}
    try:
        importances = model.feature_importances_
        top_idx = np.argsort(importances)[-5:][::-1]
        for idx in top_idx:
            if idx < len(feature_names):
                fi[feature_names[idx]] = round(float(importances[idx]), 4)
    except Exception:
        pass

    # Write to DB
    conn.execute(text("""
        INSERT INTO aquavision.water_predictions
            (asset_id, horizon, predicted_value, predicted_lower, predicted_upper,
             risk_score, risk_category, exceeds_warning, exceeds_danger,
             model_version, model_type, features_used, feature_importance,
             confidence, valid_from, valid_to, generated_at)
        VALUES
            (:asset_id, :horizon, :pred, :lower, :upper,
             :risk_score, :risk_cat, :exceeds_warn, :exceeds_danger,
             :model_ver, :model_type, :features, :fi,
             :confidence, :valid_from, :valid_to, now())
    """), {
        "asset_id": asset_id,
        "horizon": horizon,
        "pred": round(float(pred_value), 2),
        "lower": round(float(lower), 2),
        "upper": round(float(upper), 2),
        "risk_score": risk_score,
        "risk_cat": risk_category,
        "exceeds_warn": exceeds_warning,
        "exceeds_danger": exceeds_danger,
        "model_ver": "xgb-flood-v1.2",
        "model_type": "flood_predictor",
        "features": json.dumps(list(fi.keys())),
        "fi": json.dumps(fi),
        "confidence": round(float(metrics.get("r2", 0.5)), 4),
        "valid_from": valid_from,
        "valid_to": valid_to,
    })

    return {
        "asset_id": asset_id,
        "horizon": horizon,
        "predicted_value": round(pred_value, 2),
        "risk_category": risk_category,
        "risk_score": risk_score,
        "inflow_source": features.get("source_inflow", "UNKNOWN"),
        "inflow_missing": features.get("inflow_missing", 0),
    }


def run_all_predictions():
    """Load all models, run predictions, persist to DB."""
    engine = get_db()
    from sqlalchemy import text

    start = time.time()
    results = []
    errors = []
    model_versions = {}

    for asset_id in ASSET_IDS:
        for horizon in HORIZONS:
            model_data = load_model(asset_id, horizon)
            if not model_data:
                continue

            try:
                with engine.begin() as conn:
                    result = predict_and_persist(asset_id, horizon, model_data, conn)
                    if result:
                        results.append(result)
                        model_versions[f"{asset_id}_{horizon}"] = "xgb-flood-v1.2"
            except Exception as e:
                errors.append({"asset_id": asset_id, "horizon": horizon, "error": str(e)})
                logger.error(f"Failed: asset {asset_id} horizon {horizon}d: {e}")

    duration = time.time() - start

    # Log the run
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO aquavision.prediction_logs
                (run_type, assets_predicted, assets_failed, predictions_written,
                 duration_seconds, model_versions, errors, completed_at, status)
            VALUES
                (:run_type, :predicted, :failed, :written,
                 :duration, :versions, :errors, now(), :status)
        """), {
            "run_type": "SCHEDULED",
            "predicted": len(set(r["asset_id"] for r in results)),
            "failed": len(errors),
            "written": len(results),
            "duration": round(duration, 2),
            "versions": json.dumps(model_versions),
            "errors": json.dumps(errors),
            "status": "SUCCESS" if not errors else "PARTIAL",
        })

    logger.info(f"Predictions complete: {len(results)} written, {len(errors)} failed, {duration:.1f}s")
    return {"predictions": len(results), "errors": len(errors), "duration": round(duration, 2)}


def main():
    result = run_all_predictions()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
