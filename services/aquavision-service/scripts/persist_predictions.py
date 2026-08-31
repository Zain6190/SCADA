"""
Prediction Persistence Service — Loads models, runs predictions, writes to DB.
This is the core of the production forecasting system.
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


def get_latest_features(asset_id: int, conn):
    """Fetch the latest observation for an asset to build prediction features."""
    from sqlalchemy import text
    row = conn.execute(text("""
        SELECT wo.observed_at, wo.inflow_cusecs, wo.outflow_cusecs,
               wo.discharge_cusecs, wo.water_level_ft
        FROM aquavision.water_observations wo
        WHERE wo.asset_id = :aid
        ORDER BY wo.observed_at DESC
        LIMIT 1
    """), {"aid": asset_id}).mappings().first()
    return dict(row) if row else None


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

    # Get latest observation as feature baseline
    latest = get_latest_features(asset_id, conn)
    if not latest:
        logger.warning(f"No observations for asset {asset_id}")
        return None

    thresholds = get_asset_thresholds(asset_id, conn) or {}
    # Convert Decimal to float
    if thresholds.get("warning_level_ft"):
        thresholds["warning_level_ft"] = float(thresholds["warning_level_ft"])
    if thresholds.get("critical_level_ft"):
        thresholds["critical_level_ft"] = float(thresholds["critical_level_ft"])

    # Build a minimal feature vector from latest obs
    # Use the feature names from the model to create a zero-filled vector
    # then fill in what we know
    features = {}
    if latest.get("inflow_cusecs"):
        features["inflow"] = latest["inflow_cusecs"]
    if latest.get("outflow_cusecs"):
        features["outflow"] = latest["outflow_cusecs"]
    if latest.get("discharge_cusecs"):
        features["discharge"] = latest["discharge_cusecs"]
    if latest.get("water_level_ft"):
        features["level"] = latest["water_level_ft"]

    # Create feature vector (fill unknowns with 0)
    X = np.zeros((1, len(feature_names)))
    for i, fname in enumerate(feature_names):
        if fname in features:
            X[0, i] = features[fname]

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
        "model_ver": f"xgb-flood-v1.2",
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
