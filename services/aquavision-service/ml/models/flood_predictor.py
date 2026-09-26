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

    # Predicted values — which field is populated depends on target_field used during training
    predicted_level_ft: Optional[float] = None
    predicted_inflow: Optional[float] = None
    predicted_outflow: Optional[float] = None
    predicted_discharge: Optional[float] = None  # NEW: set when target_field="discharge"

    # Prediction interval (residual-based, NOT a statistical confidence interval)
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    # How the interval was produced: "quantile_q10_q90" (XGBoost quantile
    # regression), "residual_p90" (holdout |residual| percentile band), or
    # "r2_band" (legacy quality heuristic, last resort).
    ci_method: str = "r2_band"

    # Risk assessment
    risk_score: float = 0.0  # 0-100
    risk_level: str = "NORMAL"  # NORMAL, WATCH, WARNING, CRITICAL
    exceeds_warning: bool = False
    exceeds_danger: bool = False

    # Model info
    model_version: str = ""
    model_status: str = MODEL_STATUS
    target_field: str = "auto"  # NEW: what this model predicts
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
        self.log_transform = {}  # key -> bool (whether log1p was applied)
        self.residual_p90 = {}  # key -> 90th pct of |holdout residuals| (interval width)
        self.quantile_models = {}  # key -> {"q10": model, "q90": model} (in-memory only)
        self.model_version = "xgb-flood-v1.2"
        os.makedirs(MODEL_DIR, exist_ok=True)

    def train(
        self,
        asset_id: int,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        horizon: int = 7,
        sample_weights: Optional[np.ndarray] = None,
        target_field: str = "auto",  # NEW: what we're predicting
        persist: bool = True,
    ) -> Dict:
        """Train XGBoost model for a specific asset and horizon.

        persist=False keeps the model in memory only (holdout backtests /
        seed scripts must not overwrite production .joblib files).
        """
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        import xgboost as xgb

        if len(X) < 5:
            logger.warning(f"Insufficient data for training: {len(X)} samples")
            return {"error": "insufficient_data"}

        # Log-transform targets to reduce MAPE explosion near zero
        y_min = float(np.min(y))
        use_log_transform = y_min >= 0 and np.std(y) > 0
        if use_log_transform:
            y_train_raw = y.copy()
            y = np.log1p(y)
            logger.info(f"Log-transform applied: range [{y_min:.2f}, {np.max(y):.2f}] -> [{np.min(y):.4f}, {np.max(y):.4f}]")

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

        # Evaluate — metrics in ORIGINAL space (cusecs/ft), not log-space
        y_pred_log = model.predict(X_test_scaled)

        if use_log_transform:
            y_test_orig = np.expm1(y_test)
            y_pred_orig = np.expm1(y_pred_log)
        else:
            y_test_orig = y_test
            y_pred_orig = y_pred_log

        # Persistence baseline + single closed-form blend weight. For series
        # where the model cannot beat "hold today's value" (Mangla's outflow
        # autocorrelation dies out by lag 14), the optimal convex blend of
        # the XGB output and the current observed value minimises holdout
        # MSE — guaranteed >= the better of the two sides. alpha=1 means the
        # model already wins and the path is unchanged (Tarbela etc.).
        blend_alpha = 1.0
        p_test = None
        y_pred_xgb = y_pred_orig
        if target_field in feature_names:
            p_test = X_test[:, feature_names.index(target_field)].astype(float)
            denom = float(np.sum((y_pred_orig - p_test) ** 2))
            if denom > 0:
                blend_alpha = float(
                    np.sum((y_pred_orig - p_test) * (y_test_orig - p_test)) / denom
                )
            blend_alpha = float(np.clip(blend_alpha, 0.0, 1.0))
            if blend_alpha < 1.0:
                y_pred_xgb = y_pred_orig
                y_pred_orig = blend_alpha * y_pred_xgb + (1.0 - blend_alpha) * p_test

        # residuals/metrics below are in SERVING space (post-blend)
        residuals_orig = y_test_orig - y_pred_orig

        mae = mean_absolute_error(y_test_orig, y_pred_orig)
        rmse = np.sqrt(mean_squared_error(y_test_orig, y_pred_orig))
        r2 = r2_score(y_test_orig, y_pred_orig)
        mape = np.mean(np.abs(residuals_orig / (y_test_orig + 1e-8))) * 100
        r2_persistence = r2_score(y_test_orig, p_test) if p_test is not None else None
        mae_persistence = mean_absolute_error(y_test_orig, p_test) if p_test is not None else None

        residual_std = float(np.std(residuals_orig))
        residual_p90 = float(np.percentile(np.abs(residuals_orig), 90))
        residual_p50 = float(np.percentile(np.abs(residuals_orig), 50))

        importance = dict(zip(feature_names, model.feature_importances_))
        top_features = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10])

        # Save model
        key = f"{asset_id}_{horizon}"
        self.models[key] = model
        self.scalers[key] = scaler
        self.feature_names[key] = feature_names
        self.training_mae[key] = mae
        self.log_transform[key] = use_log_transform
        self.residual_p90[key] = residual_p90

        # Step 4: quantile q10/q90 interval models for production models with
        # enough data (>=100 samples; barrages train on ~30-60 and stay on
        # the residual band). persist=False (holdout seeds) skips them so
        # backtests stay fast and never write model files.
        # Rec 1: bands are conformal-calibrated on the holdout so measured
        # coverage reaches the 0.80 target (raw quantiles under-covered).
        ci_method = "residual_p90"
        ci_coverage_80 = None
        ci_coverage_80_raw = None
        ci_inflation = None
        if persist and len(X) >= 100:
            ci = self._train_interval_models(
                key=key,
                X_train_scaled=X_train_scaled,
                y_train=y_train,
                X_test_scaled=X_test_scaled,
                y_test=y_test,
                y_test_orig=y_test_orig,
                use_log_transform=use_log_transform,
                feature_names=feature_names,
                target_field=target_field,
                sample_weight=w_train,
                # conformal must calibrate the BLENDED band predict() serves
                persistence_test=p_test,
                blend_alpha=blend_alpha,
            )
            if ci is not None:
                ci_method = "quantile_q10_q90"
                ci_coverage_80 = ci["calibrated"]
                ci_coverage_80_raw = ci["raw"]
                ci_inflation = ci["inflation"]

        self.training_metrics[key] = {
            "asset_id": asset_id,
            "horizon": horizon,
            "samples": len(X),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "real_samples": int(np.sum(w_train == 1.0)) if w_train is not None else len(X_train),
            "synthetic_samples": int(np.sum(w_train < 1.0)) if w_train is not None else 0,
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "r2": round(r2, 4),
            "mape": round(mape, 2),
            "residual_std": round(residual_std, 2),
            "residual_p90": round(residual_p90, 2),
            "residual_p50": round(residual_p50, 2),
            "mae_log_space": round(float(mean_absolute_error(y_test, y_pred_log)), 4),
            "top_features": top_features,
            "trained_at": datetime.utcnow().isoformat(),
            "model_version": self.model_version,
            "model_status": MODEL_STATUS,
            "weighted": w_train is not None,
            "log_transform": use_log_transform,
            "target_field": target_field,  # NEW: save what we're predicting
            # persistence blend (see train()): serving prediction is
            # alpha*xgb + (1-alpha)*current_value; alpha=1 = pure model.
            # headline r2/mae/mape above are the BLENDED (served) values.
            "blend_alpha": round(blend_alpha, 4),
            "r2_xgb_raw": round(float(r2_score(y_test_orig, y_pred_xgb)), 4),
            "mae_xgb_raw": round(float(mean_absolute_error(y_test_orig, y_pred_xgb)), 2),
            "r2_persistence": round(float(r2_persistence), 4) if r2_persistence is not None else None,
            "mae_persistence": round(float(mae_persistence), 2) if mae_persistence is not None else None,
            "ci_method": ci_method,
            "ci_coverage_80": round(ci_coverage_80, 4) if ci_coverage_80 is not None else None,
            # honest record: coverage of the RAW q10-q90 band before conformal
            # inflation (typically well below 0.80), and the additive inflation
            # (original units) applied to reach the target
            "ci_coverage_80_raw": round(ci_coverage_80_raw, 4) if ci_coverage_80_raw is not None else None,
            "ci_inflation": round(ci_inflation, 2) if ci_inflation is not None else None,
            # residual_p90 is the 90th pct of |holdout residuals|, so holdout
            # coverage of ±p90 is ~0.90 by construction — recorded as metadata
            "ci_coverage_90": round(float(np.mean(np.abs(residuals_orig) <= residual_p90)), 4),
        }

        if persist:
            self._save_model(key, model, scaler, feature_names, mae, residual_p90, residual_std, self.training_metrics[key])
        else:
            logger.info(f"Model trained in-memory (not saved): asset={asset_id}, horizon={horizon}d")

        logger.info(
            f"Trained model: asset={asset_id}, horizon={horizon}d, "
            f"MAE={mae:.2f}, R2={r2:.4f}, blend_alpha={blend_alpha:.3f}"
        )
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
            model, scaler, feature_names_loaded, mae_orig, residual_p90, target_field = loaded
        else:
            model = self.models[key]
            scaler = self.scalers[key]
            feature_names_loaded = self.feature_names.get(key, feature_names)
            mae_orig = self.training_mae.get(key, 0)
            residual_p90 = self.residual_p90.get(key, 0)
            target_field = self.training_metrics.get(key, {}).get("target_field", "auto")

        X_scaled = scaler.transform(X)
        prediction_log = model.predict(X_scaled)[0]

        # Invert log-transform if model was trained with it
        use_log = self.log_transform.get(key, False)
        if use_log:
            prediction = float(np.expm1(prediction_log))
        else:
            prediction = float(prediction_log)

        # Persistence blend baked into metrics at train time (alpha=1 when
        # the raw model already beats "hold today's value" — legacy path).
        blend_alpha = float(self.training_metrics.get(key, {}).get("blend_alpha", 1.0) or 1.0)
        current_val = None
        if blend_alpha < 1.0 and target_field in feature_names_loaded:
            col = feature_names_loaded.index(target_field)
            if col < X.shape[1]:
                current_val = float(X[0, col])
                prediction = blend_alpha * prediction + (1.0 - blend_alpha) * current_val

        # Step 4: confidence interval chain — use the tightest calibrated
        # method available, worst case falls back to the legacy R² band.
        interval = self._load_interval_models(key)
        if interval is not None:
            q10_model, q90_model, inflation = interval
            q10_pred = float(q10_model.predict(X_scaled)[0])
            q90_pred = float(q90_model.predict(X_scaled)[0])
            if use_log:
                q10_pred = float(np.expm1(q10_pred))
                q90_pred = float(np.expm1(q90_pred))
            if current_val is not None:
                q10_pred = blend_alpha * q10_pred + (1.0 - blend_alpha) * current_val
                q90_pred = blend_alpha * q90_pred + (1.0 - blend_alpha) * current_val
            lo = min(q10_pred, q90_pred) - inflation
            hi = max(q10_pred, q90_pred) + inflation
            lower_bound = max(0.0, lo)
            upper_bound = hi
            ci_method = "quantile_q10_q90"
        elif residual_p90 and residual_p90 > 0:
            lower_bound = max(0.0, prediction - residual_p90)
            upper_bound = prediction + residual_p90
            ci_method = "residual_p90"
        else:
            # Legacy heuristic: better R² = tighter CI (last resort only)
            metrics = self.training_metrics.get(key, {})
            r2 = metrics.get("r2", 0.5)
            if r2 >= 0.7:
                ci_pct = 0.12  # Excellent model: ±12%
            elif r2 >= 0.5:
                ci_pct = 0.18  # Good model: ±18%
            elif r2 >= 0.3:
                ci_pct = 0.28  # Fair model: ±28%
            else:
                ci_pct = 0.45  # Poor model: ±45%
            horizon_factor = 1.0 + max(0, horizon - 3) * 0.03
            margin = prediction * ci_pct * horizon_factor
            lower_bound = max(0, prediction - margin)
            upper_bound = prediction + margin
            ci_method = "r2_band"

        risk_score = self._calculate_risk_score(prediction, warning_level, danger_level)
        risk_level = self._risk_level_from_score(risk_score)
        exceeds_warning = warning_level and prediction >= warning_level
        exceeds_danger = danger_level and prediction >= danger_level

        importance = dict(zip(feature_names_loaded, [float(v) for v in model.feature_importances_]))
        top_features = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5])

        # Set the correct output field based on what the model was trained to predict
        predicted_level_ft = None
        predicted_inflow = None
        predicted_outflow = None
        predicted_discharge = None

        if target_field == "discharge":
            predicted_discharge = round(float(prediction), 2)
        elif target_field == "inflow":
            predicted_inflow = round(float(prediction), 2)
        elif target_field == "outflow":
            predicted_outflow = round(float(prediction), 2)
        elif target_field == "level":
            predicted_level_ft = round(float(prediction), 2)
        else:
            # auto — default to level for backwards compatibility
            predicted_level_ft = round(float(prediction), 2)

        return FloodPrediction(
            asset_id=asset_id,
            asset_name=asset_name,
            prediction_date=datetime.utcnow().isoformat(),
            horizon_days=horizon,
            predicted_level_ft=predicted_level_ft,
            predicted_inflow=predicted_inflow,
            predicted_outflow=predicted_outflow,
            predicted_discharge=predicted_discharge,
            lower_bound=round(float(lower_bound), 2),
            upper_bound=round(float(upper_bound), 2),
            ci_method=ci_method,
            risk_score=round(float(risk_score), 1),
            risk_level=risk_level,
            exceeds_warning=bool(exceeds_warning),
            exceeds_danger=bool(exceeds_danger),
            model_version=self.model_version,
            model_status=MODEL_STATUS,
            target_field=target_field,
            feature_importance=top_features,
        )

    def _train_interval_models(
        self,
        key: str,
        X_train_scaled: np.ndarray,
        y_train: np.ndarray,
        X_test_scaled: np.ndarray,
        y_test: np.ndarray,
        y_test_orig: np.ndarray,
        use_log_transform: bool,
        feature_names: List[str],
        target_field: str,
        sample_weight: Optional[np.ndarray] = None,
        persistence_test: Optional[np.ndarray] = None,
        blend_alpha: float = 1.0,
    ) -> Optional[float]:
        """Train q10/q90 XGBoost quantile models for prediction intervals.

        Returns {"raw", "calibrated", "inflation"} holdout coverage figures
        (calibrated targets ~0.80), or None if training failed (caller then
        keeps the residual_p90 band).

        persistence_test/blend_alpha: when predict() serves a blended point
        forecast, the quantiles are blended the same way BEFORE coverage and
        conformal calibration so the stored inflation matches runtime.
        """
        import xgboost as xgb

        fitted = {}
        try:
            for alpha, name in ((0.1, "q10"), (0.9, "q90")):
                q_model = xgb.XGBRegressor(
                    objective="reg:quantileerror",
                    quantile_alpha=alpha,
                    n_estimators=300,
                    max_depth=4,
                    learning_rate=0.03,
                    subsample=0.8,
                    colsample_bytree=0.7,
                    reg_alpha=0.5,
                    reg_lambda=2.0,
                    min_child_weight=5,
                    random_state=42,
                    n_jobs=-1,
                )
                # Fixed rounds (no early stopping): avoids eval-metric
                # differences for reg:quantileerror across XGBoost versions.
                if sample_weight is not None:
                    q_model.fit(X_train_scaled, y_train, sample_weight=sample_weight)
                else:
                    q_model.fit(X_train_scaled, y_train)
                fitted[name] = q_model
        except Exception as exc:  # noqa: BLE001 — quantile must never break main model
            logger.warning(f"Quantile interval training failed for {key}: {exc}")
            return None

        q10_pred = fitted["q10"].predict(X_test_scaled)
        q90_pred = fitted["q90"].predict(X_test_scaled)
        if use_log_transform:
            q10_pred = np.expm1(q10_pred)
            q90_pred = np.expm1(q90_pred)
        if persistence_test is not None and blend_alpha < 1.0:
            # same blend predict() applies to the quantiles
            q10_pred = blend_alpha * q10_pred + (1.0 - blend_alpha) * persistence_test
            q90_pred = blend_alpha * q90_pred + (1.0 - blend_alpha) * persistence_test
        coverage_raw = float(np.mean((y_test_orig >= q10_pred) & (y_test_orig <= q90_pred)))

        # Split-conformal calibration on the holdout (quantile models never
        # saw it — no early stopping). Nonconformity score = distance outside
        # the raw band; inflate by the 80th percentile so holdout coverage
        # reaches the 0.80 target. Additive, original units — a fixed offset,
        # so coverage under flow-regime shift is not guaranteed (standard
        # conformal caveat, documented rather than hidden).
        scores = np.maximum(q10_pred - y_test_orig, y_test_orig - q90_pred)
        inflation = max(0.0, float(np.percentile(scores, 80)))
        coverage_cal = float(np.mean(
            (y_test_orig >= q10_pred - inflation) & (y_test_orig <= q90_pred + inflation)
        ))

        path = os.path.join(MODEL_DIR, f"{key}_interval.joblib")
        joblib.dump({
            "q10": fitted["q10"],
            "q90": fitted["q90"],
            "feature_names": feature_names,
            "log_transform": use_log_transform,
            "target_field": target_field,
            "coverage_80_holdout": coverage_raw,
            "coverage_80_calibrated": coverage_cal,
            "conformal_inflation": inflation,
            "saved_at": datetime.utcnow().isoformat(),
        }, path)
        self.quantile_models[key] = {**fitted, "inflation": inflation}
        logger.info(
            f"Saved interval models: {path} (holdout coverage raw={coverage_raw:.3f} "
            f"-> calibrated={coverage_cal:.3f}, inflation={inflation:.1f}, target=0.80)"
        )
        return {"raw": coverage_raw, "calibrated": coverage_cal, "inflation": inflation}

    def _load_interval_models(self, key: str):
        """Return (q10_model, q90_model, conformal_inflation) for key.

        Inflation defaults to 0.0 for legacy interval files saved before
        conformal calibration existed.
        """
        if key in self.quantile_models:
            m = self.quantile_models[key]
            return m["q10"], m["q90"], m.get("inflation", 0.0)
        path = os.path.join(MODEL_DIR, f"{key}_interval.joblib")
        if os.path.exists(path):
            data = joblib.load(path)
            inflation = float(data.get("conformal_inflation", 0.0))
            self.quantile_models[key] = {
                "q10": data["q10"], "q90": data["q90"], "inflation": inflation,
            }
            return data["q10"], data["q90"], inflation
        return None

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

    def _save_model(self, key, model, scaler, feature_names, mae, residual_p90, residual_std, metrics):
        path = os.path.join(MODEL_DIR, f"{key}.joblib")
        joblib.dump({
            "model": model,
            "scaler": scaler,
            "feature_names": feature_names,
            "version": self.model_version,
            "model_status": MODEL_STATUS,
            "training_mae": mae,
            "training_mae_original": mae,
            "residual_p90_original": residual_p90,
            "residual_std_original": residual_std,
            "metrics": metrics,
            "log_transform": self.log_transform.get(key, False),
            "target_field": metrics.get("target_field", "auto"),  # NEW
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
            self.training_mae[key] = data.get("training_mae_original", data.get("training_mae", 0))
            self.residual_p90[key] = data.get("residual_p90_original", data.get("residual_std", 0))
            self.training_metrics[key] = data.get("metrics", {})
            self.log_transform[key] = data.get("log_transform", False)
            # Store target_field in metrics so predict() can access it
            if "target_field" not in self.training_metrics[key]:
                self.training_metrics[key]["target_field"] = data.get("target_field", "auto")
            return (
                data["model"],
                data["scaler"],
                data["feature_names"],
                data.get("training_mae_original", data.get("training_mae", 0)),
                data.get("residual_p90_original", data.get("residual_std", 0)),
                data.get("target_field", "auto"),  # NEW
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
        self.residual_p90 = {}
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
        target_field: str = "discharge",
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

        # Evaluate — metrics in ORIGINAL space
        y_pred = model.predict(X_test_scaled)
        residuals = y_test - y_pred

        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        mape = np.mean(np.abs((y_test - y_pred) / (y_test + 1e-8))) * 100

        residual_std = float(np.std(residuals))
        residual_p90 = float(np.percentile(np.abs(residuals), 90))
        residual_p50 = float(np.percentile(np.abs(residuals), 50))

        importance = dict(zip(feature_names, model.feature_importances_))
        top_features = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10])

        # Save
        key = f"{asset_id}_{horizon}_hf"
        self.models[key] = model
        self.scalers[key] = scaler
        self.feature_names[key] = feature_names
        self.training_mae[key] = mae
        self.residual_p90[key] = residual_p90
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
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "r2": round(r2, 4),
            "mape": round(mape, 2),
            "residual_std": round(residual_std, 2),
            "residual_p90": round(residual_p90, 2),
            "residual_p50": round(residual_p50, 2),
            "top_features": top_features,
            "trained_at": datetime.utcnow().isoformat(),
            "model_version": self.model_version,
            "model_status": MODEL_STATUS,
            "target_field": target_field,
        }

        self._save_model(key, model, scaler, feature_names, mae, residual_p90, residual_std, self.training_metrics[key])

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
            model, scaler, feature_names_loaded, mae_orig, residual_p90 = loaded
        else:
            model = self.models[key]
            scaler = self.scalers[key]
            feature_names_loaded = self.feature_names.get(key, feature_names)
            mae_orig = self.training_mae.get(key, 0)
            residual_p90 = self.residual_p90.get(key, 0)

        X_scaled = scaler.transform(X)
        # HighFlowPredictor trains in original space (no log transform)
        prediction = float(model.predict(X_scaled)[0])

        if residual_p90 and residual_p90 > 0:
            margin = residual_p90
            ci_method = "residual_p90"
        elif mae_orig and mae_orig > 0:
            margin = mae_orig
            ci_method = "residual_p90"
        else:
            margin = prediction * 0.05
            ci_method = "r2_band"
        lower_bound = prediction - margin
        upper_bound = prediction + margin

        risk_score = self._calculate_risk_score(prediction, warning_level, danger_level)
        risk_level = self._risk_level_from_score(risk_score)
        exceeds_warning = warning_level and prediction >= warning_level
        exceeds_danger = danger_level and prediction >= danger_level

        importance = dict(zip(feature_names_loaded, [float(v) for v in model.feature_importances_]))
        top_features = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5])

        target_field = self.training_metrics.get(key, {}).get("target_field", "discharge")
        predicted_level_ft = None
        predicted_inflow = None
        predicted_outflow = None
        predicted_discharge = None
        if target_field == "level":
            predicted_level_ft = round(float(prediction), 2)
        elif target_field == "inflow":
            predicted_inflow = round(float(prediction), 2)
        elif target_field == "outflow":
            predicted_outflow = round(float(prediction), 2)
        else:
            predicted_discharge = round(float(prediction), 2)

        return FloodPrediction(
            asset_id=asset_id,
            asset_name=asset_name,
            prediction_date=datetime.utcnow().isoformat(),
            horizon_days=horizon,
            predicted_level_ft=predicted_level_ft,
            predicted_inflow=predicted_inflow,
            predicted_outflow=predicted_outflow,
            predicted_discharge=predicted_discharge,
            lower_bound=round(float(lower_bound), 2),
            upper_bound=round(float(upper_bound), 2),
            ci_method=ci_method,
            risk_score=round(float(risk_score), 1),
            risk_level=risk_level,
            exceeds_warning=bool(exceeds_warning),
            exceeds_danger=bool(exceeds_danger),
            model_version=self.model_version,
            model_status=MODEL_STATUS,
            target_field=target_field,
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

    def _save_model(self, key, model, scaler, feature_names, mae, residual_p90, residual_std, metrics):
        path = os.path.join(MODEL_DIR, f"{key}.joblib")
        joblib.dump({
            "model": model,
            "scaler": scaler,
            "feature_names": feature_names,
            "version": self.model_version,
            "model_status": MODEL_STATUS,
            "training_mae": mae,
            "training_mae_original": mae,
            "residual_p90_original": residual_p90,
            "residual_std_original": residual_std,
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
            self.training_mae[key] = data.get("training_mae_original", data.get("training_mae", 0))
            self.residual_p90[key] = data.get("residual_p90_original", data.get("residual_std", 0))
            self.training_metrics[key] = data.get("metrics", {})
            return (
                data["model"],
                data["scaler"],
                data["feature_names"],
                data.get("training_mae_original", data.get("training_mae", 0)),
                data.get("residual_p90_original", data.get("residual_std", 0)),
            )
        return None
