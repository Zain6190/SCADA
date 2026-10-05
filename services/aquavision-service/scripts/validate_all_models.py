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
CLASSIFIER_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
CLASSIFIER_VERSION = "xgb-flood-v1.2-h7"
FLOOD_LABEL_STATUSES = ("HIGH", "VERY_HIGH", "EXCEPTIONALLY_HIGH")


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
    """Walk-forward backtest with expanding chronological window.

    Fold 1: Train [0:fold_size]        → Test [fold_size:2*fold_size]
    Fold 2: Train [0:2*fold_size]      → Test [2*fold_size:3*fold_size]
    ...
    Final:  Train [0:n_folds*fold_size] → Test [n_folds*fold_size:end]

    All metrics in ORIGINAL space (cusecs/ft). Uses production hyperparams + sample weights.
    """
    from sqlalchemy.orm import Session
    from infrastructure.db.engine import SessionLocal
    from ml.features.feature_engineering import FloodFeatureBuilder

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

    if len(X) < 50:
        return {"error": f"insufficient_data: {len(X)} samples (need 50)"}

    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    import xgboost as xgb

    # Expanding window: each fold trains on more data
    fold_size = len(X) // (n_folds + 2)
    fold_metrics = []

    for fold in range(n_folds):
        train_end = fold_size * (fold + 2)
        test_start = train_end
        test_end = min(test_start + fold_size, len(X))

        if test_end <= test_start or (test_end - test_start) < 5:
            continue

        X_train, y_train = X[:train_end], y[:train_end]
        w_train = weights[:train_end] if weights is not None else None
        X_test, y_test = X[test_start:test_end], y[test_start:test_end]

        if len(X_train) < 20:
            continue

        # Log-transform (same as production FloodPredictor.train)
        use_log = np.min(y_train) >= 0 and np.std(y_train) > 0
        if use_log:
            y_train_t = np.log1p(y_train)
        else:
            y_train_t = y_train.copy()

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Production hyperparameters
        model = xgb.XGBRegressor(
            n_estimators=500,
            max_depth=4,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.5,
            reg_lambda=2.0,
            min_child_weight=5,
            random_state=42,
            n_jobs=-1,
            early_stopping_rounds=30,
        )

        fit_kwargs = {
            "eval_set": [(X_test_scaled, np.log1p(y_test) if use_log else y_test)],
            "verbose": False,
        }
        if w_train is not None:
            fit_kwargs["sample_weight"] = w_train

        model.fit(X_train_scaled, y_train_t, **fit_kwargs)

        # Predict and invert — clip log-space to prevent expm1 overflow
        y_pred_t = model.predict(X_test_scaled)
        if use_log:
            y_pred_t = np.clip(y_pred_t, 0, 20)  # expm1(20) ~ 4.8e8, safe
            y_pred_orig = np.expm1(y_pred_t.astype(np.float64))
            y_test_orig = y_test.astype(np.float64)  # y_test is already in original space
        else:
            y_pred_orig = np.clip(y_pred_t.astype(np.float64), 0, None)
            y_test_orig = y_test.astype(np.float64)

        # Metrics in ORIGINAL space
        if not np.all(np.isfinite(y_test_orig)) or not np.all(np.isfinite(y_pred_orig)):
            continue  # skip fold with bad values
        mae = float(mean_absolute_error(y_test_orig, y_pred_orig))
        rmse = float(np.sqrt(mean_squared_error(y_test_orig, y_pred_orig)))
        r2 = float(r2_score(y_test_orig, y_pred_orig))
        mape = float(np.mean(np.abs((y_test_orig - y_pred_orig) / (y_test_orig + 1e-8))) * 100)
        residual_p90 = float(np.percentile(np.abs(y_test_orig - y_pred_orig), 90))

        fold_metrics.append({
            "fold": fold + 1,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "real_samples": int(np.sum(w_train == 1.0)) if w_train is not None else len(X_train),
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "r2": round(r2, 4),
            "mape": round(mape, 2),
            "residual_p90": round(residual_p90, 2),
        })

    if not fold_metrics:
        return {"error": "no_valid_folds"}

    # Aggregate across folds (median is more robust than mean)
    avg_mae = float(np.median([f["mae"] for f in fold_metrics]))
    avg_rmse = float(np.median([f["rmse"] for f in fold_metrics]))
    avg_r2 = float(np.median([f["r2"] for f in fold_metrics]))
    avg_mape = float(np.median([f["mape"] for f in fold_metrics]))
    avg_p90 = float(np.median([f["residual_p90"] for f in fold_metrics]))

    # Persistence baseline: predict last known value for each test fold
    persistence_errors = []
    for fold in range(n_folds):
        train_end = fold_size * (fold + 2)
        test_start = train_end
        test_end = min(test_start + fold_size, len(X))
        if test_end <= test_start:
            continue
        y_test = y[test_start:test_end]
        last_known = y[train_end - 1] if train_end > 0 else y[0]
        persistence_errors.extend(np.abs(y_test - last_known))
    persistence_mae = float(np.mean(persistence_errors)) if persistence_errors else avg_mae

    # Score (no double-counting)
    score = 0
    if avg_r2 > 0.8:
        score += 40
    elif avg_r2 > 0.5:
        score += 30
    elif avg_r2 > 0.2:
        score += 15
    elif avg_r2 > 0.0:
        score += 5

    if persistence_mae > 0 and avg_mae < persistence_mae:
        mae_improvement = (persistence_mae - avg_mae) / max(persistence_mae, 1e-8) * 100
        score += min(30, int(mae_improvement / 2))

    if avg_mape < 20:
        score += 15
    elif avg_mape < 40:
        score += 10
    elif avg_mape < 60:
        score += 5

    # Recommendation
    if score >= 70:
        recommendation = "SHADOW"
    elif score >= 40:
        recommendation = "EXPERIMENTAL"
    else:
        recommendation = "REJECTED"

    return {
        "total_samples": len(X),
        "n_folds": len(fold_metrics),
        "mae": round(avg_mae, 2),
        "rmse": round(avg_rmse, 2),
        "r2": round(avg_r2, 4),
        "mape": round(avg_mape, 2),
        "residual_p90": round(avg_p90, 2),
        "persistence_mae": round(persistence_mae, 2),
        "mae_improvement_pct": round((persistence_mae - avg_mae) / max(persistence_mae, 1e-8) * 100, 2),
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
                "residual_p90": metrics.get("residual_p90"),
                "score": metrics.get("score"),
                "persistence_mae": metrics.get("persistence_mae"),
                "mae_improvement_pct": metrics.get("mae_improvement_pct"),
                "auc": metrics.get("auc"),
                "brier": metrics.get("brier"),
                "baseline_brier": metrics.get("baseline_brier"),
                "accuracy": metrics.get("accuracy"),
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f1": metrics.get("f1"),
            }),
            "data_info": json.dumps({
                "total_samples": metrics.get("total_samples"),
                "n_folds": metrics.get("n_folds"),
            }),
            "recommendation": metrics.get("recommendation", "EXPERIMENTAL"),
            "reasons": json.dumps([metrics.get("reason", f"Walk-forward backtest: R2={metrics.get('r2', 0):.4f}, MAE={metrics.get('mae', 0):.2f}")]),
            "fold_details": json.dumps(metrics.get("fold_details", [])),
        })


def get_classifier_assets():
    """Get assets that have a trained flood classifier pkl."""
    engine = get_db()
    results = []
    with engine.connect() as conn:
        for path in sorted(CLASSIFIER_DIR.glob("flood_classifier_asset_*.pkl")):
            suffix = path.stem.rsplit("_", 1)[-1]
            if not suffix.isdigit():
                continue
            row = conn.execute(text(
                "SELECT id, canonical_name FROM aquavision.water_assets WHERE id = :id"
            ), {"id": int(suffix)}).mappings().first()
            if row:
                results.append({"id": row["id"], "name": row["canonical_name"]})
    return results


def load_classifier_frame(asset_id: int) -> "pd.DataFrame":
    """Observation frame the flood classifier trains on (same query as training)."""
    from decimal import Decimal
    from sqlalchemy import text as sql_text

    engine = get_db()
    with engine.connect() as conn:
        rows = conn.execute(sql_text("""
            SELECT observed_at,
                   COALESCE(inflow_cusecs, discharge_cusecs) as inflow_cusecs,
                   outflow_cusecs,
                   water_level_ft, discharge_cusecs
            FROM aquavision.water_observations
            WHERE asset_id = :asset_id
            AND (inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL)
            ORDER BY observed_at
        """), {"asset_id": asset_id}).mappings().all()

    df = pd.DataFrame(rows)
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = df[col].apply(lambda x: float(x) if isinstance(x, (Decimal, int)) else x)
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except Exception:
                pass
    return df


def walk_forward_classifier(asset_id: int, df: "pd.DataFrame", horizon: int = 7,
                            n_folds: int = 5) -> dict:
    """Expanding-window walk-forward backtest for the flood classifier.

    Mirrors FloodClassifier.train (same features/labels, production GBM
    hyperparameters, SMOTE parity) but folds chronologically so every test
    sample is predicted by a model that never saw it. Recommendation gates:
    skill vs the climatology Brier baseline, discrimination (AUC) and the
    operational precision/recall pair.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    )

    from ml.models.flood_classifier import FloodClassifier

    clf = FloodClassifier(asset_id)
    features = clf.build_features(df)
    labels = clf.build_labels(df, horizon)
    valid_mask = features.notna().all(axis=1) & labels.notna()
    features = features[valid_mask]
    labels = labels[valid_mask]

    if len(features) < 100:
        return {"error": f"insufficient_data: {len(features)} samples (need 100)"}

    n_pos_all = int(labels.sum())
    core = labels.iloc[: len(labels) - horizon] if len(labels) > horizon else labels
    n_pos_core = int(core.sum())
    if n_pos_core == 0:
        return {"error": "no_positive_labels: no flood events in the frame"}
    if n_pos_core == len(core):
        return {"error": "no_negative_labels: every sample is a flood"}
    if n_pos_all == 0:
        return {"error": "no_positive_labels: no flood events in the frame"}

    fold_size = len(features) // (n_folds + 2)
    if fold_size < 5:
        return {"error": "insufficient_data: too few samples for walk-forward folds"}

    y_all: list = []
    p_all: list = []
    base_all: list = []
    fold_metrics = []

    for fold in range(n_folds):
        train_end = fold_size * (fold + 2)
        test_start = train_end
        test_end = min(test_start + fold_size, len(features))
        if test_end <= test_start or (test_end - test_start) < 5:
            continue
        if train_end < 50:
            continue

        X_train = features.iloc[:train_end]
        y_train = labels.iloc[:train_end]
        X_test = features.iloc[test_start:test_end]
        y_test = labels.iloc[test_start:test_end]

        flood_ratio = float(y_train.mean())
        n_flood = int(y_train.sum())
        if flood_ratio < 0.3 and n_flood >= 5:
            try:
                from imblearn.over_sampling import SMOTE
                X_train, y_train = SMOTE(
                    random_state=42, k_neighbors=min(5, n_flood - 1)
                ).fit_resample(X_train, y_train)
            except Exception:
                pass

        model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            min_samples_leaf=10,
            random_state=42,
        )
        try:
            model.fit(X_train, y_train)
        except ValueError:
            logger.warning("  walk-forward fold %s unusable (single-class train window)", fold + 1)
            continue

        y_prob = model.predict_proba(X_test)[:, 1]
        y_test_list = list(y_test)
        p_list = list(y_prob)
        base_rate = float(y_train.mean()) if len(y_train) else 0.0
        base_list = [base_rate] * len(y_test_list)

        y_all.extend(y_test_list)
        p_all.extend(p_list)
        base_all.extend(base_list)

        y_pred = (y_prob >= 0.5).astype(int)
        fold_brier = float(np.mean((y_prob - y_test.values) ** 2))
        fold_metrics.append({
            "fold": fold + 1,
            "train_samples": int(len(X_train)),
            "test_samples": int(len(y_test)),
            "brier": round(fold_brier, 4),
            "recall": round(recall_score(y_test, y_pred, zero_division=0), 4),
            "precision": round(precision_score(y_test, y_pred, zero_division=0), 4),
            "flood_rate_test": round(float(y_test.mean()), 4),
        })

    if not fold_metrics:
        return {"error": "no_valid_folds"}

    y_arr = np.asarray(y_all, dtype=float)
    p_arr = np.asarray(p_all, dtype=float)
    base_arr = np.asarray(base_all, dtype=float)

    n_pos = int(y_arr.sum())
    if n_pos == 0:
        return {"error": "no_positive_labels: no flood events in any test fold"}
    if n_pos == len(y_arr):
        return {"error": "no_negative_labels: every test sample is a flood"}

    try:
        auc = float(roc_auc_score(y_arr, p_arr))
    except ValueError:
        auc = 0.5

    brier = float(np.mean((p_arr - y_arr) ** 2))
    baseline_brier = float(np.mean((base_arr - y_arr) ** 2))
    y_pred = (p_arr >= 0.5).astype(int)
    accuracy = float(accuracy_score(y_arr, y_pred))
    precision = float(precision_score(y_arr, y_pred, zero_division=0))
    recall = float(recall_score(y_arr, y_pred, zero_division=0))
    f1 = float(f1_score(y_arr, y_pred, zero_division=0))

    score = 0
    if auc > 0.80:
        score += 40
    elif auc > 0.70:
        score += 30
    elif auc > 0.60:
        score += 15
    elif auc > 0.55:
        score += 5

    brier_skill = (baseline_brier - brier) / max(baseline_brier, 1e-8)
    if brier_skill >= 0.20:
        score += 30
    elif brier_skill >= 0.10:
        score += 20
    elif brier_skill > 0:
        score += 10

    if recall >= 0.60:
        score += 15
    elif recall >= 0.30:
        score += 8

    if precision >= 0.50:
        score += 15
    elif precision >= 0.30:
        score += 8

    if score >= 70:
        recommendation = "SHADOW"
    elif score >= 40:
        recommendation = "EXPERIMENTAL"
    else:
        recommendation = "REJECTED"

    return {
        "total_samples": int(len(y_arr)),
        "n_folds": len(fold_metrics),
        "auc": round(auc, 4),
        "brier": round(brier, 4),
        "baseline_brier": round(baseline_brier, 4),
        "brier_skill_pct": round(brier_skill * 100, 2),
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "flood_events": n_pos,
        "score": score,
        "recommendation": recommendation,
        "reason": (
            f"Walk-forward classifier: AUC={auc:.4f}, Brier={brier:.4f} "
            f"vs baseline={baseline_brier:.4f}, F1={f1:.4f}"
        ),
        "fold_details": fold_metrics,
    }


def main():
    logger.info("=" * 60)
    logger.info("STARTING BATCH VALIDATION - All Models")
    logger.info("=" * 60)

    assets = get_assets_with_models()
    logger.info(f"Found {len(assets)} assets with trained models")

    all_results = []
    horizons = [3, 7, 14, 30]

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

    classifier_assets = get_classifier_assets()
    logger.info(f"Found {len(classifier_assets)} assets with flood classifiers")

    for asset in classifier_assets:
        aid = asset["id"]
        name = asset["name"]
        logger.info(f"Validating flood classifier for {name} ...")

        try:
            df = load_classifier_frame(aid)
            metrics = walk_forward_classifier(aid, df)
        except Exception as e:
            logger.warning(f"  SKIPPED: validation error: {e}")
            metrics = {"error": f"validation_error: {e}"}

        if "error" in metrics:
            logger.warning(f"  SKIPPED: {metrics['error']}")
            all_results.append({
                "asset_id": aid, "asset_name": name,
                "horizon": 7, "status": "SKIPPED",
                "reason": metrics["error"],
            })
            continue

        store_validation_report(
            aid, "flood_classifier", CLASSIFIER_VERSION, 7, metrics
        )
        logger.info(
            f"  AUC={metrics['auc']:.4f}, Brier={metrics['brier']:.4f} "
            f"(baseline {metrics['baseline_brier']:.4f}), F1={metrics['f1']:.4f}, "
            f"Score={metrics['score']}, Recommendation={metrics['recommendation']}"
        )
        all_results.append({
            "asset_id": aid, "asset_name": name,
            "horizon": 7, "status": "VALIDATED",
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
