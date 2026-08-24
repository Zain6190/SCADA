# ml/models/flood_predictor.py
# XGBoost-based flood prediction model.
# Predicts reservoir level / discharge 7/14/30 days ahead.
#
# Phase 2B: Replaced hardcoded confidence interval with residual-based
# prediction interval using training MAE. Added model metadata.
# Phase 2D: Added HighFlowPredictor for extreme event prediction.

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
        sample_weights: Optional[np.ndarray] = None,
    ) -> Dict:
        """Train XGBoost model for a specific asset and horizon."""
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        import xgboost as xgb

        if len(X) < 5:
            logger.warning(f"Insufficient data for training: {len(X)} samples")
            return {"error": "insufficient_data"}

        # Split data (chronological — no shuffle)
        if sample_weights is not None:
            X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
                X, y, sample_weights, test_size=0.2, shuffle=False
            )
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, shuffle=False
            )
            w_train = None

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train XGBoost with early stopping to prevent overfitting
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
            "eval_set": [(X_test_scaled, y_test)],
            "verbose": False,
        }
        if w_train is not None:
            fit_kwargs["sample_weight"] = w_train

        model.fit(X_train_scaled, y_train, **fit_kwargs)

        # Evaluate
        y_pred = model.predict(X_test_scaled)
        residuals = y_test - y_pred

        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        mape = np.mean(np.abs((y_test - y_pred) / (y_test + 1e-8))) * 100

        residual_std = float(np.std(residuals))
        residual_p90 = float(np.percentile(np.abs(residuals), 90))

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
            "real_samples": int(np.sum(w_train == 1.0)) if w_train is not None else len(X_train),
            "synthetic_samples": int(np.sum(w_train < 1.0)) if w_train is not None else 0,
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
            "weighted": w_train is not None,
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
        """Make prediction for an asset."""
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

        X_scaled = scaler.transform(X)
        prediction = model.predict(X_scaled)[0]

        margin = mae if mae > 0 else prediction * 0.05
        lower_bound = prediction - margin
        upper_bound = prediction + margin

        risk_score = self._calculate_risk_score(prediction, warning_level, danger_level)
        risk_level = self._risk_level_from_score(risk_score)
        exceeds_warning = warning_level and prediction >= warning_level
        exceeds_danger = danger_level and prediction >= danger_level

        importance = dict(zip(feature_names_loaded, [float(v) for v in model.feature_importances_]))
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
            risk_score=round(float(risk_score), 1),
            risk_level=risk_level,
            exceeds_warning=bool(exceeds_warning),
            exceeds_danger=bool(exceeds_danger),
            model_version=self.model_version,
            model_status=MODEL_STATUS,
            feature_importance=top_features,
        )

    def _calculate_risk_score(self, predicted_level, warning_level, danger_level):
        if not warning_level or warning_level == 0:
            return 0.0
        if danger_level and danger_level > warning_level:
            if predicted_level >= danger_level:
                return 100.0
            elif predicted_level >= warning_level:
                pct = (predicted_level - warning_level) / (danger_level - warning_level)
                return 50.0 + pct * 50.0
            else:
                return (predicted_level / warning_level) * 50.0
        else:
            if predicted_level >= warning_level:
                return 75.0
            return (predicted_level / warning_level) * 50.0

    def _risk_level_from_score(self, score):
        if score >= 80:
            return "CRITICAL"
        elif score >= 60:
            return "WARNING"
        elif score >= 40:
            return "WATCH"
        return "NORMAL"

    def _save_model(self, key, model, scaler, feature_names, mae, residual_std, metrics):
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

    def _load_model(self, key):
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


# ─── High-Flow Specific Model ──────────────────────────────────────────────

class HighFlowPredictor:
    """XGBoost model trained specifically on high-flow observations.
    
    The standard FloodPredictor is trained on ALL data (mostly low-flow),
    which makes it biased toward normal conditions. This model:
    1. Filters training data to observations above the 75th percentile
    2. Uses heavier sample weights for extreme events
    3. Has hyperparameters tuned for high-variance data
    
    Use this model when current flow is above the 75th percentile.
    """

    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.feature_names = {}
        self.training_mae = {}
        self.training_metrics = {}
        self.model_version = "xgb-highflow-v1.0"
        self.percentile_threshold = 75
        os.makedirs(MODEL_DIR, exist_ok=True)

    def train(
        self,
        asset_id: int,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        horizon: int = 7,
        sample_weights: Optional[np.ndarray] = None,
    ) -> Dict:
        """Train high-flow specific XGBoost model."""
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        import xgboost as xgb

        if len(X) < 15:
            logger.warning(f"Insufficient high-flow data for training: {len(X)} samples")
            return {"error": "insufficient_data"}

        # Filter to high-flow observations only
        threshold = np.percentile(y, self.percentile_threshold)
        high_flow_mask = y >= threshold
        X_hf = X[high_flow_mask]
        y_hf = y[high_flow_mask]
        w_hf = sample_weights[high_flow_mask] if sample_weights is not None else None

        if len(X_hf) < 8:
            logger.warning(f"Insufficient high-flow samples after filtering: {len(X_hf)}")
            return {"error": "insufficient_high_flow_data"}

        logger.info(f"High-flow model: {len(X_hf)}/{len(X)} samples above {self.percentile_threshold}th percentile ({threshold:.2f})")

        # Split (chronological)
        if w_hf is not None:
            X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
                X_hf, y_hf, w_hf, test_size=0.2, shuffle=False
            )
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X_hf, y_hf, test_size=0.2, shuffle=False
            )
            w_train = None

        # Scale
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train with conservative hyperparameters to prevent overfitting
        model = xgb.XGBRegressor(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.5,
            reg_lambda=2.0,
            min_child_weight=5,
            gamma=0.1,
            random_state=42,
            n_jobs=-1,
            early_stopping_rounds=30,
        )

        fit_kwargs = {"eval_set": [(X_test_scaled, y_test)], "verbose": False}
        if w_train is not None:
            fit_kwargs["sample_weight"] = w_train

        model.fit(X_train_scaled, y_train, **fit_kwargs)

        # Evaluate
        y_pred = model.predict(X_test_scaled)
        residuals = y_test - y_pred

        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        mape = np.mean(np.abs((y_test - y_pred) / (y_test + 1e-8))) * 100

        residual_std = float(np.std(residuals))
        residual_p90 = float(np.percentile(np.abs(residuals), 90))

        importance = dict(zip(feature_names, model.feature_importances_))
        top_features = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10])

        # Save
        key = f"{asset_id}_{horizon}_hf"
        self.models[key] = model
        self.scalers[key] = scaler
        self.feature_names[key] = feature_names
        self.training_mae[key] = mae
        self.training_metrics[key] = {
            "asset_id": asset_id,
            "horizon": horizon,
            "model_type": "high_flow",
            "percentile_threshold": self.percentile_threshold,
            "flow_threshold": round(float(threshold), 2),
            "total_samples": len(X),
            "high_flow_samples": len(X_hf),
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

        logger.info(f"Trained high-flow model: asset={asset_id}, horizon={horizon}d, MAE={mae:.2f}, R2={r2:.4f}")
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
        """Make prediction using high-flow model."""
        key = f"{asset_id}_{horizon}_hf"

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

        X_scaled = scaler.transform(X)
        prediction = model.predict(X_scaled)[0]

        margin = mae if mae > 0 else prediction * 0.05
        lower_bound = prediction - margin
        upper_bound = prediction + margin

        risk_score = self._calculate_risk_score(prediction, warning_level, danger_level)
        risk_level = self._risk_level_from_score(risk_score)
        exceeds_warning = warning_level and prediction >= warning_level
        exceeds_danger = danger_level and prediction >= danger_level

        importance = dict(zip(feature_names_loaded, [float(v) for v in model.feature_importances_]))
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
            risk_score=round(float(risk_score), 1),
            risk_level=risk_level,
            exceeds_warning=bool(exceeds_warning),
            exceeds_danger=bool(exceeds_danger),
            model_version=self.model_version,
            model_status=MODEL_STATUS,
            feature_importance=top_features,
        )

    def _calculate_risk_score(self, predicted_level, warning_level, danger_level):
        if not warning_level or warning_level == 0:
            return 0.0
        if danger_level and danger_level > warning_level:
            if predicted_level >= danger_level:
                return 100.0
            elif predicted_level >= warning_level:
                pct = (predicted_level - warning_level) / (danger_level - warning_level)
                return 50.0 + pct * 50.0
            return (predicted_level / warning_level) * 50.0
        if predicted_level >= warning_level:
            return 75.0
        return (predicted_level / warning_level) * 50.0

    def _risk_level_from_score(self, score):
        if score >= 80:
            return "CRITICAL"
        elif score >= 60:
            return "WARNING"
        elif score >= 40:
            return "WATCH"
        return "NORMAL"

    def _save_model(self, key, model, scaler, feature_names, mae, residual_std, metrics):
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
        logger.info(f"Saved high-flow model: {path}")

    def _load_model(self, key):
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
