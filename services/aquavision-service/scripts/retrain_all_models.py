"""
scripts/retrain_all_models.py
AquaVision - Batch retrain all FloodPredictor + FloodClassifier models.

Retrains for all active water assets with sufficient observations.
Uses enriched features (weather forecasts, log-transform, SMOTE).

Usage:
    python -m scripts.retrain_all_models   (run from services/aquavision-service)
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
logger = logging.getLogger("retrain_all")

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "flood_xgb"
CLASSIFIER_DIR = Path(__file__).resolve().parent.parent / "data" / "models"


def get_db():
    from infrastructure.db.engine import engine
    return engine


def get_active_assets():
    """Get all active assets with observations."""
    engine = get_db()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT wa.id, wa.canonical_name, wa.asset_type,
                   COUNT(wo.id) as obs_count
            FROM aquavision.water_assets wa
            LEFT JOIN aquavision.water_observations wo ON wo.asset_id = wa.id
            WHERE wa.is_active = true
            GROUP BY wa.id, wa.canonical_name, wa.asset_type
            HAVING COUNT(wo.id) >= 30
            ORDER BY wa.id
        """)).mappings().all()
    return [dict(r) for r in rows]


def train_flood_predictor(asset_id: int, asset_name: str, horizons=[7, 14, 30]):
    """Train FloodPredictor for an asset across all horizons."""
    from sqlalchemy.orm import Session
    from infrastructure.db.engine import SessionLocal
    from ml.features.feature_engineering import FloodFeatureBuilder
    from ml.models.flood_predictor import FloodPredictor

    results = []
    predictor = FloodPredictor()

    with SessionLocal() as session:
        builder = FloodFeatureBuilder(session)

        for horizon in horizons:
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

            if len(X) < 10:
                logger.warning(f"Asset {asset_name} horizon {horizon}d: insufficient data ({len(X)} samples)")
                results.append({
                    "asset_id": asset_id, "asset_name": asset_name,
                    "horizon": horizon, "status": "SKIPPED", "reason": "insufficient_data"
                })
                continue

            metrics = predictor.train(
                asset_id=asset_id, X=X, y=y,
                feature_names=feature_names, horizon=horizon,
                sample_weights=weights,
            )

            if "error" not in metrics:
                logger.info(f"Asset {asset_name} horizon {horizon}d: MAE={metrics.get('mae', 0):.2f}, R2={metrics.get('r2', 0):.4f}")
                results.append({
                    "asset_id": asset_id, "asset_name": asset_name,
                    "horizon": horizon, "status": "SUCCESS", **metrics
                })
            else:
                logger.warning(f"Asset {asset_name} horizon {horizon}d: {metrics['error']}")
                results.append({
                    "asset_id": asset_id, "asset_name": asset_name,
                    "horizon": horizon, "status": "FAILED", **metrics
                })

    return results


def train_highflow_predictor(asset_id: int, asset_name: str, horizons=[7, 14, 30]):
    """Train HighFlowPredictor for an asset across all horizons."""
    from sqlalchemy.orm import Session
    from infrastructure.db.engine import SessionLocal
    from ml.features.feature_engineering import FloodFeatureBuilder
    from ml.models.flood_predictor import HighFlowPredictor

    results = []
    predictor = HighFlowPredictor()

    with SessionLocal() as session:
        builder = FloodFeatureBuilder(session)

        for horizon in horizons:
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

            if len(X) < 15:
                results.append({
                    "asset_id": asset_id, "asset_name": asset_name,
                    "horizon": horizon, "status": "SKIPPED", "reason": "insufficient_data"
                })
                continue

            metrics = predictor.train(
                asset_id=asset_id, X=X, y=y,
                feature_names=feature_names, horizon=horizon,
                sample_weights=weights,
            )

            if "error" not in metrics:
                logger.info(f"Asset {asset_name} horizon {horizon}d HIGH-FLOW: MAE={metrics.get('mae', 0):.2f}, R2={metrics.get('r2', 0):.4f}")
                results.append({
                    "asset_id": asset_id, "asset_name": asset_name,
                    "horizon": horizon, "model_type": "high_flow",
                    "status": "SUCCESS", **metrics
                })
            else:
                results.append({
                    "asset_id": asset_id, "asset_name": asset_name,
                    "horizon": horizon, "model_type": "high_flow",
                    "status": "SKIPPED", **metrics
                })

    return results


def train_flood_classifier(asset_id: int, asset_name: str):
    """Train FloodClassifier for an asset."""
    from sqlalchemy.orm import Session
    from infrastructure.db.engine import SessionLocal
    from ml.models.flood_classifier import FloodClassifier

    with SessionLocal() as session:
        rows = session.execute(text("""
            SELECT observed_at,
                   COALESCE(inflow_cusecs, discharge_cusecs) as inflow_cusecs,
                   outflow_cusecs, water_level_ft, discharge_cusecs
            FROM aquavision.water_observations
            WHERE asset_id = :asset_id
            AND (inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL)
            ORDER BY observed_at
        """), {"asset_id": asset_id}).mappings().all()

        if len(rows) < 200:
            return {"asset": asset_name, "status": "SKIPPED", "reason": "insufficient_data"}

        df = pd.DataFrame(rows)
        from decimal import Decimal
        for col in df.columns:
            if df[col].dtype == object:
                try:
                    df[col] = df[col].apply(lambda x: float(x) if isinstance(x, (Decimal, int)) else x)
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                except Exception:
                    pass

        clf = FloodClassifier(asset_id, asset_name)
        metrics = clf.train(df, horizon=7)

        if "error" not in metrics:
            clf.save()
            logger.info(f"Classifier {asset_name}: accuracy={metrics.get('accuracy', 0):.3f}, f1={metrics.get('f1', 0):.3f}")
            return {"asset": asset_name, "status": "SUCCESS", **metrics}
        else:
            return {"asset": asset_name, "status": "FAILED", **metrics}


def generate_model_metadata(all_results: list) -> dict:
    """Generate consolidated model metadata."""
    metadata = {
        "generated_at": datetime.utcnow().isoformat(),
        "model_version": "xgb-flood-v1.2",
        "features_enriched": True,
        "weather_features": True,
        "log_transform": True,
        "smote_classifier": True,
        "assets": {},
    }

    for r in all_results:
        aid = r.get("asset_id")
        if aid not in metadata["assets"]:
            metadata["assets"][aid] = {
                "asset_id": aid,
                "asset_name": r.get("asset_name", ""),
                "models": {},
            }

        model_type = r.get("model_type", "flood_predictor")
        horizon = r.get("horizon")
        key = f"{model_type}_{horizon}" if horizon else model_type

        metadata["assets"][aid]["models"][key] = {
            "status": r.get("status", "UNKNOWN"),
            "horizon": horizon,
            "model_type": model_type,
            "mae": r.get("mae"),
            "rmse": r.get("rmse"),
            "r2": r.get("r2"),
            "mape": r.get("mape"),
            "train_samples": r.get("train_samples"),
            "test_samples": r.get("test_samples"),
            "top_features": r.get("top_features"),
            "trained_at": r.get("trained_at"),
        }

    return metadata


def main():
    logger.info("=" * 60)
    logger.info("STARTING BATCH RETRAIN - All Assets")
    logger.info("=" * 60)

    assets = get_active_assets()
    logger.info(f"Found {len(assets)} active assets with sufficient data")

    all_results = []

    for asset in assets:
        aid = asset["id"]
        name = asset["canonical_name"]
        obs_count = asset["obs_count"]

        logger.info(f"\n--- Training {name} (ID={aid}, observations={obs_count}) ---")

        # FloodPredictor (7d, 14d, 30d)
        results = train_flood_predictor(aid, name)
        all_results.extend(results)

        # HighFlowPredictor (7d, 14d, 30d)
        hf_results = train_highflow_predictor(aid, name)
        all_results.extend(hf_results)

        # FloodClassifier (7d)
        clf_result = train_flood_classifier(aid, name)
        all_results.append(clf_result)

    # Generate metadata
    metadata = generate_model_metadata(all_results)
    metadata_path = CLASSIFIER_DIR / "model_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    logger.info(f"\nModel metadata written to {metadata_path}")

    # Summary
    success = sum(1 for r in all_results if r.get("status") == "SUCCESS")
    skipped = sum(1 for r in all_results if r.get("status") == "SKIPPED")
    failed = sum(1 for r in all_results if r.get("status") == "FAILED")

    logger.info(f"\n{'=' * 60}")
    logger.info(f"RETRAIN COMPLETE: {success} success, {skipped} skipped, {failed} failed")
    logger.info(f"{'=' * 60}")

    return all_results


if __name__ == "__main__":
    main()
