# ml/models/flood_predictor.py
# XGBoost-based flood prediction model.
# Predicts reservoir level / discharge 7/14/30 days ahead.
#
# Phase 2B: Replaced hardcoded confidence interval with residual-based
# prediction interval using training MAE. Added model metadata.

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import numpy as np
import joblib

logger = logging.getLogger("aquavision.ml.flood_predictor")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models", "flood_xgb")

# Model status label — displayed in all ML outputs
MODEL_STATUS = "EXPERIMENTAL"


@dataclass
class FloodPrediction:
    """Prediction result for a single asset.

    NOTE: This model is EXPERIMENTAL. Predictions are advisory only.
    Do not use for operational decisions without human review.
    """
    asset_id: int
    asset_name: str
    prediction_date: str
    horizon_days: int

    # Predicted values
    predicted_level_ft: Optional[float]
    predicted_inflow: Optional[float]
    predicted_outflow: Optional[float]

    # Prediction interval (residual-based, NOT a statistical confidence interval)
    lower_bound: Optional[float]
    upper_bound: Optional[float]

    # Risk assessment
    risk_score: float  # 0-100
    risk_level: str  # NORMAL, WATCH, WARNING, CRITICAL
    exceeds_warning: bool
    exceeds_danger: bool

    # Model info
    model_version: str
    model_status: str = MODEL_STATUS
    feature_importance: Dict[str, float] = field(default_factory=dict)


class FloodPredictor:
    """XGBoost-based flood level/discharge predictor.

    Predicts reservoir level at t+7, t+14, t+30 days.
    Uses lag features, rolling stats, seasonal encoding, FFD status.

    Status: EXPERIMENTAL — shadow mode, not for operational use.
    """

    def __init__(self):
        self.models = {}  # key -> model
        self.scalers = {}  # key -> scaler
        self.feature_names = {}
        self.training_mae = {}  # key -> MAE from training (for prediction interval)
        self.training_metrics = {}  # key -> full metrics dict
        self.model_version = "xgb-flood-v1.1"
        os.makedirs(MODEL_DIR, exist_ok=True)

    def train(
        self,
        asset_id: int,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        horizon: int = 7,
    ) -> Dict:
        """Train XGBoost model for a specific asset and horizon.

        Args:
            asset_id: Asset ID
            X: Feature matrix
            y: Target vector (levels)
            feature_names: Feature names
            horizon: Prediction horizon (7, 14, or 30 days)

        Returns:
            Training metrics dict
        """
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        import xgboost as xgb

        if len(X) < 5:
            logger.warning(f"Insufficient data for training: {len(X)} samples")
            return {"error": "insufficient_data"}

        # Split data (chronological — no shuffle)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train XGBoost
        model = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=-1,
        )

        model.fit(
            X_train_scaled, y_train,
            eval_set=[(X_test_scaled, y_test)],
            verbose=False,
        )

        # Evaluate
        y_pred = model.predict(X_test_scaled)
        residuals = y_test - y_pred

        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        mape = np.mean(np.abs((y_test - y_pred) / (y_test + 1e-8))) * 100

        # Residual statistics for prediction intervals
        residual_std = float(np.std(residuals))
        residual_p90 = float(np.percentile(np.abs(residuals), 90))

        # Feature importance
        importance = dict(zip(feature_names, model.feature_importances_))
        top_features = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10])

        # Save model
        key = f"{asset_id}_{horizon}"
        self.models[key] = model
        self.scalers[key] = scaler
        self.feature_names[key] = feature_names
        self.training_mae[key] = mae
        self.training_metrics[key] = {
            "asset_id": asset_id,
            "horizon": horizon,
            "samples": len(X),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
            "mape": round(mape, 2),
            "residual_std": round(residual_std, 4),
            "residual_p90": round(residual_p90, 4),
            "top_features": top_features,
            "trained_at": datetime.utcnow().isoformat(),
            "model_version": self.model_version,
            "model_status": MODEL_STATUS,
        }

        self._save_model(key, model, scaler, feature_names, mae, residual_std, self.training_metrics[key])

        logger.info(f"Trained model: asset={asset_id}, horizon={horizon}d, MAE={mae:.2f}, R2={r2:.4f}")
        return self.training_metrics[key]

    def predict(
        self,
        asset_id: int,
        asset_name: str,
        X: np.ndarray,
        feature_names: List[str],
        horizon: int = 7,
        warning_level: Optional[float] = None,
        danger_level: Optional[float] = None,
    ) -> Optional[FloodPrediction]:
        """Make prediction for an asset.

        Args:
            asset_id: Asset ID
            asset_name: Asset name
            X: Feature vector (1, n_features)
            feature_names: Feature names
            horizon: Prediction horizon
            warning_level: Warning threshold
            danger_level: Danger threshold

        Returns:
            FloodPrediction or None if model not available

        NOTE: This model is EXPERIMENTAL. Prediction intervals are
        residual-based (MAE), not statistically validated confidence intervals.
        """
        key = f"{asset_id}_{horizon}"

        if key not in self.models:
            loaded = self._load_model(key)
            if not loaded:
                return None
            model, scaler, feature_names_loaded, mae, _ = loaded
        else:
            model = self.models[key]
            scaler = self.scalers[key]
            feature_names_loaded = self.feature_names.get(key, feature_names)
            mae = self.training_mae.get(key, 0)

        # Scale and predict
        X_scaled = scaler.transform(X)
        prediction = model.predict(X_scaled)[0]

        # Prediction interval based on training MAE (residual-based)
        # This is NOT a statistical confidence interval — it's an estimate
        # of typical prediction error from the training set.
        margin = mae if mae > 0 else prediction * 0.05
        lower_bound = prediction - margin
        upper_bound = prediction + margin

        # Risk assessment
        risk_score = self._calculate_risk_score(
            prediction, warning_level, danger_level
        )
        risk_level = self._risk_level_from_score(risk_score)
        exceeds_warning = warning_level and prediction >= warning_level
        exceeds_danger = danger_level and prediction >= danger_level

        # Feature importance
        importance = dict(zip(feature_names_loaded, model.feature_importances_))
        top_features = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5])

        return FloodPrediction(
            asset_id=asset_id,
            asset_name=asset_name,
            prediction_date=datetime.utcnow().isoformat(),
            horizon_days=horizon,
            predicted_level_ft=round(float(prediction), 2),
            predicted_inflow=None,
            predicted_outflow=None,
            lower_bound=round(float(lower_bound), 2),
            upper_bound=round(float(upper_bound), 2),
            risk_score=round(risk_score, 1),
            risk_level=risk_level,
            exceeds_warning=bool(exceeds_warning),
            exceeds_danger=bool(exceeds_danger),
            model_version=self.model_version,
            model_status=MODEL_STATUS,
            feature_importance=top_features,
        )

    def _calculate_risk_score(
        self,
        predicted_level: float,
        warning_level: Optional[float],
        danger_level: Optional[float],
    ) -> float:
        """Calculate risk score 0-100 based on predicted level."""
        if not warning_level or warning_level == 0:
            return 0.0

        if danger_level and danger_level > warning_level:
            if predicted_level >= danger_level:
                return 100.0
            elif predicted_level >= warning_level:
                pct = (predicted_level - warning_level) / (danger_level - warning_level)
                return 50.0 + pct * 50.0
            else:
                pct = predicted_level / warning_level
                return pct * 50.0
        else:
            if predicted_level >= warning_level:
                return 75.0
            else:
                pct = predicted_level / warning_level
                return pct * 50.0

    def _risk_level_from_score(self, score: float) -> str:
        """Convert risk score to risk level."""
        if score >= 80:
            return "CRITICAL"
        elif score >= 60:
            return "WARNING"
        elif score >= 40:
            return "WATCH"
        else:
            return "NORMAL"

    def _save_model(self, key: str, model, scaler, feature_names, mae, residual_std, metrics):
        """Save model to disk with full metadata."""
        path = os.path.join(MODEL_DIR, f"{key}.joblib")
        joblib.dump({
            "model": model,
            "scaler": scaler,
            "feature_names": feature_names,
            "version": self.model_version,
            "model_status": MODEL_STATUS,
            "training_mae": mae,
            "residual_std": residual_std,
            "metrics": metrics,
            "saved_at": datetime.utcnow().isoformat(),
        }, path)
        logger.info(f"Saved model: {path}")

    def _load_model(self, key: str):
        """Load model from disk with metadata."""
        path = os.path.join(MODEL_DIR, f"{key}.joblib")
        if os.path.exists(path):
            data = joblib.load(path)
            self.models[key] = data["model"]
            self.scalers[key] = data["scaler"]
            self.feature_names[key] = data["feature_names"]
            self.training_mae[key] = data.get("training_mae", 0)
            self.training_metrics[key] = data.get("metrics", {})
            return (
                data["model"],
                data["scaler"],
                data["feature_names"],
                data.get("training_mae", 0),
                data.get("residual_std", 0),
            )
        return None
