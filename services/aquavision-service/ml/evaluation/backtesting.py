# ml/evaluation/backtesting.py
# Walk-forward backtesting for flood prediction models.
# Uses chronological splits to prevent training on future data.
#
# Phase 2B: Added walk-forward validation, persistence baseline, per-asset metrics.

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("aquavision.ml.evaluation")


@dataclass
class BacktestResult:
    """Results from a walk-forward backtest for a single asset."""
    asset_id: int
    asset_name: str
    horizon: int
    total_folds: int
    metrics: Dict[str, float]  # mae, rmse, r2, mape
    persistence_metrics: Dict[str, float]  # baseline comparison
    fold_details: List[Dict] = field(default_factory=list)
    high_flow_metrics: Optional[Dict[str, float]] = None


def walk_forward_backtest(
    asset_id: int,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
    horizon: int = 7,
    min_train_size: int = 15,
    test_size: int = 1,
) -> BacktestResult:
    """Walk-forward backtesting with chronological splits.
    
    Each fold:
    - Train on data[0:i]
    - Test on data[i+horizon]
    - Move forward by test_size
    
    This prevents training on future data.
    
    Args:
        asset_id: Asset ID
        X: Full feature matrix
        y: Full target vector
        feature_names: Feature names
        horizon: Prediction horizon
        min_train_size: Minimum training samples
        test_size: Number of test samples per fold
    
    Returns:
        BacktestResult with metrics per fold and aggregated
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    import xgboost as xgb

    n_samples = len(X)
    if n_samples < min_train_size + horizon + test_size:
        logger.warning(f"Insufficient data for backtest: {n_samples} samples")
        return BacktestResult(
            asset_id=asset_id,
            asset_name="",
            horizon=horizon,
            total_folds=0,
            metrics={"mae": 0, "rmse": 0, "r2": 0, "mape": 0},
            persistence_metrics={"mae": 0, "rmse": 0, "r2": 0, "mape": 0},
        )

    all_preds = []
    all_actuals = []
    all_persistence = []
    fold_details = []

    for i in range(min_train_size, n_samples - horizon, test_size):
        # Train on data[0:i], test on data[i+horizon]
        X_train = X[:i]
        y_train = y[:i]
        X_test = X[i:i+test_size]
        y_test = y[i+horizon:i+horizon+test_size]

        if len(y_test) == 0:
            break

        # Scale
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train
        model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train_scaled, y_train, verbose=False)

        # Predict
        y_pred = model.predict(X_test_scaled)

        # Persistence baseline: prediction = last observed value
        y_persist = np.full_like(y_test, y_train[-1])

        all_preds.extend(y_pred.tolist())
        all_actuals.extend(y_test.tolist())
        all_persistence.extend(y_persist.tolist())

        fold_details.append({
            "fold": len(fold_details) + 1,
            "train_size": i,
            "test_idx": i + horizon,
            "actual": float(y_test[0]),
            "predicted": float(y_pred[0]),
            "persistence": float(y_persist[0]),
            "error": float(abs(y_test[0] - y_pred[0])),
            "persist_error": float(abs(y_test[0] - y_persist[0])),
        })

    if not all_preds:
        return BacktestResult(
            asset_id=asset_id,
            asset_name="",
            horizon=horizon,
            total_folds=0,
            metrics={"mae": 0, "rmse": 0, "r2": 0, "mape": 0},
            persistence_metrics={"mae": 0, "rmse": 0, "r2": 0, "mape": 0},
        )

    preds = np.array(all_preds)
    actuals = np.array(all_actuals)
    persist = np.array(all_persistence)

    # Model metrics
    mae = float(mean_absolute_error(actuals, preds))
    rmse = float(np.sqrt(mean_squared_error(actuals, preds)))
    r2 = float(r2_score(actuals, preds)) if len(actuals) > 1 else 0.0
    mape = float(np.mean(np.abs((actuals - preds) / (actuals + 1e-8))) * 100)

    # Persistence metrics
    p_mae = float(mean_absolute_error(actuals, persist))
    p_rmse = float(np.sqrt(mean_squared_error(actuals, persist)))
    p_r2 = float(r2_score(actuals, persist)) if len(actuals) > 1 else 0.0
    p_mape = float(np.mean(np.abs((actuals - persist) / (actuals + 1e-8))) * 100)

    # High-flow period metrics (actuals > 75th percentile)
    threshold = np.percentile(actuals, 75)
    high_flow_mask = actuals > threshold
    if np.sum(high_flow_mask) >= 3:
        hf_actuals = actuals[high_flow_mask]
        hf_preds = preds[high_flow_mask]
        high_flow_metrics = {
            "mae": round(float(mean_absolute_error(hf_actuals, hf_preds)), 4),
            "rmse": round(float(np.sqrt(mean_squared_error(hf_actuals, hf_preds))), 4),
            "r2": round(float(r2_score(hf_actuals, hf_preds)), 4) if len(hf_actuals) > 1 else 0.0,
            "samples": int(np.sum(high_flow_mask)),
        }
    else:
        high_flow_metrics = None

    return BacktestResult(
        asset_id=asset_id,
        asset_name="",
        horizon=horizon,
        total_folds=len(fold_details),
        metrics={
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
            "mape": round(mape, 2),
        },
        persistence_metrics={
            "mae": round(p_mae, 4),
            "rmse": round(p_rmse, 4),
            "r2": round(p_r2, 4),
            "mape": round(p_mape, 2),
        },
        fold_details=fold_details,
        high_flow_metrics=high_flow_metrics,
    )


def backtest_all_assets(
    session,
    asset_ids: List[int] = None,
    horizons: List[int] = [7],
) -> List[BacktestResult]:
    """Run walk-forward backtest for all assets.
    
    Args:
        session: DB session
        asset_ids: List of asset IDs (None = all active)
        horizons: List of prediction horizons
    
    Returns:
        List of BacktestResult per asset per horizon
    """
    from infrastructure.db.models import WaterAsset
    from ml.features.feature_engineering import FloodFeatureBuilder

    if asset_ids is None:
        assets = session.query(WaterAsset).filter(WaterAsset.is_active == True).all()
        asset_ids = [a.id for a in assets]

    builder = FloodFeatureBuilder(session)
    results = []

    for asset_id in asset_ids:
        asset = session.get(WaterAsset, asset_id)
        if not asset:
            continue

        for horizon in horizons:
            try:
                X, y, feature_names = builder.build_training_table(
                    asset_id=asset_id,
                    start_date=datetime.utcnow() - timedelta(days=365),
                    end_date=datetime.utcnow(),
                    forecast_horizon=horizon,
                )

                if len(X) < 20:
                    logger.info(f"Asset {asset.canonical_name}: insufficient data for backtest ({len(X)} samples)")
                    continue

                result = walk_forward_backtest(
                    asset_id=asset_id,
                    X=X,
                    y=y,
                    feature_names=feature_names,
                    horizon=horizon,
                )
                result.asset_name = asset.canonical_name
                results.append(result)

                logger.info(
                    f"Backtest: {asset.canonical_name} {horizon}d | "
                    f"MAE={result.metrics['mae']:.2f} | "
                    f"R2={result.metrics['r2']:.4f} | "
                    f"vs persistence MAE={result.persistence_metrics['mae']:.2f}"
                )

            except Exception as e:
                logger.error(f"Backtest failed for asset {asset_id}, horizon {horizon}: {e}")

    return results
