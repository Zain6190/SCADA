"""
scripts/validate_all_models.py
AquaVision - Batch validate all trained FloodPredictor models.

Runs walk-forward backtesting for each asset, stores validation reports,
and auto-promotes best models to SHADOW status.

Usage:
    python -m scripts.validate_all_models   (run from services/aquavision-service)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate_all")

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "flood_xgb"


def get_db():
    from infrastructure.db.engine import engine
    return engine


def get_assets_with_models():
    """Get assets that have trained FloodPredictor models."""
    model_files = list(MODEL_DIR.glob("[0-9]*_[0-9]*.joblib"))
    model_files = [f for f in model_files if "_hf" not in f.name]

    asset_ids = set()
    for f in model_files:
        parts = f.stem.split("_")
        if len(parts) >= 2:
            asset_ids.add(int(parts[0]))

    engine = get_db()
    results = []
    with engine.connect() as conn:
        for aid in sorted(asset_ids):
            row = conn.execute(text(
                "SELECT id, canonical_name FROM aquavision.water_assets WHERE id = :id"
            ), {"id": aid}).mappings().first()
            if row:
                results.append({"id": row["id"], "name": row["canonical_name"]})
    return results


def walk_forward_backtest(asset_id: int, horizon: int = 7, n_folds: int = 5) -> dict:
    """Run walk-forward backtest for an asset.

    Each fold: train on data[0:i], test on data[i+horizon].
    Returns aggregated metrics across folds.
    """
    from sqlalchemy.orm import Session
    from infrastructure.db.engine import SessionLocal
    from ml.features.feature_engineering import FloodFeatureBuilder
    from ml.models.flood_predictor import FloodPredictor

    with SessionLocal() as session:
        builder = FloodFeatureBuilder(session)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=365 * 3)

        X, y, feature_names, weights = builder.build_training_table(
            asset_id=asset_id,
            start_date=start_date,
            end_date=end_date,
            forecast_horizon=horizon,
            real_only=False,
            target_field="auto",
            source_priority=True,
        )

    if len(X) < 30:
        return {"error": f"insufficient_data: {len(X)} samples"}

    # Walk-forward splits
    fold_size = len(X) // (n_folds + 1)
    fold_metrics = []

    for fold in range(n_folds):
        train_end = fold_size * (fold + 1)
        test_start = train_end
        test_end = min(test_start + fold_size, len(X))

        if test_end <= test_start:
            continue

        X_train, y_train = X[:train_end], y[:train_end]
        X_test, y_test = X[test_start:test_end], y[test_start:test_end]

        if len(X_train) < 10 or len(X_test) < 5:
            continue

        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        import xgboost as xgb

        # Apply same log1p transform as FloodPredictor.train
        use_log = np.min(y_train) >= 0 and np.std(y_train) > 0
        if use_log:
            y_train_t = np.log1p(y_train)
            y_test_t = np.log1p(y_test)
        else:
            y_train_t = y_train
            y_test_t = y_test

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        model = xgb.XGBRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7, random_state=42,
            n_jobs=-1, early_stopping_rounds=20,
        )
        model.fit(X_train_scaled, y_train_t, eval_set=[(X_test_scaled, y_test_t)], verbose=False)

        y_pred_t = model.predict(X_test_scaled)

        # Invert log-transform for metrics (use float64 to avoid expm1 overflow)
        if use_log:
            y_test_orig = np.expm1(y_test_t.astype(np.float64))
            y_pred_orig = np.clip(np.expm1(y_pred_t.astype(np.float64)), 0, None)
        else:
            y_test_orig = y_test.astype(np.float64)
            y_pred_orig = np.clip(y_pred_t.astype(np.float64), 0, None)

        mae = float(mean_absolute_error(y_test_orig, y_pred_orig))
        rmse = float(np.sqrt(mean_squared_error(y_test_orig, y_pred_orig)))
        r2 = float(r2_score(y_test_orig, y_pred_orig))
        mape = float(np.mean(np.abs((y_test_orig - y_pred_orig) / (y_test_orig + 1e-8))) * 100)

        fold_metrics.append({
            "fold": fold + 1,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
            "mape": round(mape, 2),
        })

    if not fold_metrics:
        return {"error": "no_valid_folds"}

    # Aggregate
    avg_mae = np.mean([f["mae"] for f in fold_metrics])
    avg_rmse = np.mean([f["rmse"] for f in fold_metrics])
    avg_r2 = np.mean([f["r2"] for f in fold_metrics])
    avg_mape = np.mean([f["mape"] for f in fold_metrics])

    # Persistence baseline (predict last known value)
    persistence_mae = float(np.mean(np.abs(np.diff(y[-len(y)//4:]))))

    # Score
    score = 0
    if avg_r2 > 0.8:
        score += 45
    elif avg_r2 > 0.5:
        score += 35
    elif avg_r2 > 0.0:
        score += 15

    if persistence_mae > 0 and avg_mae < persistence_mae:
        score += 15

    mae_improvement = (persistence_mae - avg_mae) / max(persistence_mae, 1e-8) * 100
    if mae_improvement > 50:
        score += 20

    if avg_r2 > 0.5:
        score += 15

    # Recommendation
    if score >= 70:
        recommendation = "SHADOW"
    elif score >= 35:
        recommendation = "EXPERIMENTAL"
    else:
        recommendation = "REJECTED"

    return {
        "total_samples": len(X),
        "n_folds": len(fold_metrics),
        "mae": round(float(avg_mae), 4),
        "rmse": round(float(avg_rmse), 4),
        "r2": round(float(avg_r2), 4),
        "mape": round(float(avg_mape), 2),
        "persistence_mae": round(persistence_mae, 4),
        "mae_improvement_pct": round(mae_improvement, 2),
        "score": score,
        "recommendation": recommendation,
        "fold_details": fold_metrics,
    }


def store_validation_report(asset_id: int, model_type: str, model_version: str,
                            horizon: int, metrics: dict) -> None:
    """Store validation report in DB."""
    engine = get_db()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO aquavision.validation_reports
                (asset_id, model_type, model_version, horizon, metrics, data_info,
                 recommendation, reasons, fold_details, validated_at)
            VALUES
                (:asset_id, :model_type, :model_version, :horizon, :metrics,
                 :data_info, :recommendation, :reasons, :fold_details, now())
        """), {
            "asset_id": asset_id,
            "model_type": model_type,
            "model_version": model_version,
            "horizon": horizon,
            "metrics": json.dumps({
                "mae": metrics.get("mae"),
                "rmse": metrics.get("rmse"),
                "r2": metrics.get("r2"),
                "mape": metrics.get("mape"),
                "score": metrics.get("score"),
                "persistence_mae": metrics.get("persistence_mae"),
                "mae_improvement_pct": metrics.get("mae_improvement_pct"),
            }),
            "data_info": json.dumps({
                "total_samples": metrics.get("total_samples"),
                "n_folds": metrics.get("n_folds"),
            }),
            "recommendation": metrics.get("recommendation", "EXPERIMENTAL"),
            "reasons": json.dumps([f"Walk-forward backtest: R2={metrics.get('r2', 0):.4f}, MAE={metrics.get('mae', 0):.2f}"]),
            "fold_details": json.dumps(metrics.get("fold_details", [])),
        })


def main():
    logger.info("=" * 60)
    logger.info("STARTING BATCH VALIDATION - All Models")
    logger.info("=" * 60)

    assets = get_assets_with_models()
    logger.info(f"Found {len(assets)} assets with trained models")

    all_results = []
    horizons = [7, 14, 30]

    for asset in assets:
        aid = asset["id"]
        name = asset["name"]

        for horizon in horizons:
            model_key = f"{aid}_{horizon}"
            model_path = MODEL_DIR / f"{model_key}.joblib"

            if not model_path.exists():
                continue

            logger.info(f"Validating {name} horizon {horizon}d ...")

            metrics = walk_forward_backtest(aid, horizon)

            if "error" in metrics:
                logger.warning(f"  SKIPPED: {metrics['error']}")
                all_results.append({
                    "asset_id": aid, "asset_name": name,
                    "horizon": horizon, "status": "SKIPPED",
                    "reason": metrics["error"],
                })
                continue

            # Store in DB
            store_validation_report(
                aid, "flood_predictor", "xgb-flood-v1.2", horizon, metrics
            )

            logger.info(
                f"  R2={metrics['r2']:.4f}, MAE={metrics['mae']:.2f}, "
                f"MAPE={metrics['mape']:.1f}%, Score={metrics['score']}, "
                f"Recommendation={metrics['recommendation']}"
            )

            all_results.append({
                "asset_id": aid, "asset_name": name,
                "horizon": horizon, "status": "VALIDATED",
                **metrics,
            })

    # Summary
    validated = sum(1 for r in all_results if r.get("status") == "VALIDATED")
    shadow = sum(1 for r in all_results if r.get("recommendation") == "SHADOW")
    experimental = sum(1 for r in all_results if r.get("recommendation") == "EXPERIMENTAL")
    rejected = sum(1 for r in all_results if r.get("recommendation") == "REJECTED")
    skipped = sum(1 for r in all_results if r.get("status") == "SKIPPED")

    logger.info(f"\n{'=' * 60}")
    logger.info(f"VALIDATION COMPLETE:")
    logger.info(f"  Validated: {validated}")
    logger.info(f"  SHADOW (promote): {shadow}")
    logger.info(f"  EXPERIMENTAL: {experimental}")
    logger.info(f"  REJECTED: {rejected}")
    logger.info(f"  SKIPPED: {skipped}")
    logger.info(f"{'=' * 60}")

    return all_results


if __name__ == "__main__":
    main()
