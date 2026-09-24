"""Seed prediction_errors with a chronological holdout backtest.

Trains FloodPredictor on the first 80% of REAL observations and scores the
final 20% (prediction vs actual at each horizon). Writes one
prediction_errors row per holdout sample so the accuracy API has real
numbers immediately — without waiting for live forecasts to expire.

Usage (from services/aquavision-service):
    python -m scripts.seed_prediction_errors
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_prediction_errors")

HORIZONS = (3, 7, 14)
MIN_HOLDOUT = 5
MODEL_VERSION_PREFIX = "holdout"


def _detect_target_field(session, asset_id: int) -> str:
    """Concrete target for this asset — same map the production retrain uses
    (ml/targets.py) so holdout scores match what the live model predicts."""
    from ml.targets import resolve_target_field

    return resolve_target_field(session, asset_id, real_only=True)


def seed_asset_horizon(session, asset_id: int, horizon: int) -> dict:
    from ml.features.feature_engineering import FloodFeatureBuilder
    from ml.models.flood_predictor import FloodPredictor

    builder = FloodFeatureBuilder(session)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365 * 3)
    target_field = _detect_target_field(session, asset_id)

    result = builder.build_training_table(
        asset_id=asset_id,
        start_date=start_date,
        end_date=end_date,
        forecast_horizon=horizon,
        real_only=True,
        target_field=target_field,
        source_priority=True,
        return_dates=True,
    )
    X, y, feature_names, weights, dates = result

    if len(X) < MIN_HOLDOUT + 10 or len(dates) != len(X):
        return {"asset_id": asset_id, "horizon": horizon, "status": "SKIPPED", "n": int(len(X))}

    split = max(int(len(X) * 0.8), len(X) - max(MIN_HOLDOUT * 4, 30))
    split = min(split, len(X) - MIN_HOLDOUT)
    if split < 20:
        return {"asset_id": asset_id, "horizon": horizon, "status": "SKIPPED", "n": int(len(X))}

    model_version = f"{MODEL_VERSION_PREFIX}_xgb_{asset_id}_{horizon}d"
    session.execute(
        text(
            "DELETE FROM aquavision.prediction_errors "
            "WHERE asset_id = :aid AND horizon = :h AND model_version = :mv"
        ),
        {"aid": asset_id, "h": horizon, "mv": model_version},
    )

    predictor = FloodPredictor()
    metrics = predictor.train(
        asset_id=asset_id,
        X=X[:split],
        y=y[:split],
        feature_names=feature_names,
        horizon=horizon,
        sample_weights=weights[:split] if weights is not None else None,
        target_field=target_field,
        persist=False,
    )
    if "error" in metrics:
        return {"asset_id": asset_id, "horizon": horizon, "status": "FAILED", "reason": metrics["error"]}

    inserted = 0
    for i in range(split, len(X)):
        pred = predictor.predict(
            asset_id=asset_id,
            asset_name="",
            X=X[i : i + 1],
            feature_names=feature_names,
            horizon=horizon,
        )
        if pred is None:
            continue
        predicted = (
            pred.predicted_discharge
            if pred.predicted_discharge is not None
            else pred.predicted_outflow
            if pred.predicted_outflow is not None
            else pred.predicted_inflow
            if pred.predicted_inflow is not None
            else pred.predicted_level_ft
        )
        if predicted is None:
            continue
        actual = float(y[i])
        error = float(predicted) - actual
        error_pct = abs(error) / actual * 100 if actual > 0 else abs(error)
        pred_date, tgt_date = dates[i]
        session.execute(
            text(
                """
                INSERT INTO aquavision.prediction_errors
                    (asset_id, model_version, prediction_date, target_date,
                     horizon, predicted_value, actual_value, error, error_pct, data_origin)
                VALUES
                    (:asset_id, :model_version, :prediction_date, :target_date,
                     :horizon, :predicted_value, :actual_value, :error, :error_pct, 'REAL')
                """
            ),
            {
                "asset_id": asset_id,
                "model_version": model_version,
                "prediction_date": pred_date,
                "target_date": tgt_date,
                "horizon": horizon,
                "predicted_value": float(predicted),
                "actual_value": actual,
                "error": error,
                "error_pct": error_pct,
            },
        )
        inserted += 1

    session.commit()
    return {
        "asset_id": asset_id,
        "horizon": horizon,
        "status": "OK",
        "n": inserted,
        "train": split,
        "mae": metrics.get("mae"),
        "mape": metrics.get("mape"),
    }


def seed_all(asset_ids: list[int] | None = None) -> list[dict]:
    from infrastructure.db.engine import SessionLocal

    results = []
    with SessionLocal() as session:
        if asset_ids is None:
            rows = session.execute(
                text(
                    "SELECT id FROM aquavision.water_assets WHERE is_active ORDER BY id"
                )
            ).scalars().all()
            asset_ids = list(rows)

        for asset_id in asset_ids:
            for horizon in HORIZONS:
                try:
                    r = seed_asset_horizon(session, int(asset_id), horizon)
                except Exception as e:
                    logger.exception("Seed failed asset=%s horizon=%s: %s", asset_id, horizon, e)
                    r = {"asset_id": asset_id, "horizon": horizon, "status": "ERROR", "reason": str(e)}
                results.append(r)
                logger.info("%s", r)
    return results


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None
    out = seed_all()
    ok = [r for r in out if r.get("status") == "OK"]
    skipped = [r for r in out if r.get("status") == "SKIPPED"]
    failed = [r for r in out if r.get("status") not in ("OK", "SKIPPED")]
    total_rows = sum(int(r.get("n") or 0) for r in ok)
    print(f"\nSeed complete: {len(ok)} ok, {len(skipped)} skipped, {len(failed)} failed, {total_rows} rows")
    for r in failed:
        print(f"  FAIL {r}")
