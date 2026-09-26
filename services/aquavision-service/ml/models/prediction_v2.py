"""
AquaVision Prediction Model v2.0
=================================
Production forecasting service that outputs:
1. Water Stress Level (0-100) with categories
2. Flood Risk Score (0-100) with categories
3. Expected Discharge (m3/s) with 95% CI
4. Rainfall Alert (mm) with probability

Lead times: 3-day, 7-day, 14-day

Wraps existing ML models (FloodPredictor, FloodClassifier) and physics
routing, transforming outputs to the structured format required by the
AquaVision dashboard.

WARNING: This model is EXPERIMENTAL. Predictions are advisory only.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("aquavision.prediction_v2")


# ─── Constants ───────────────────────────────────────────────────────────────

# Unit conversion: 1 m3/s = 35.3147 cusecs
CUSECS_TO_M3S = 1.0 / 35.3147

# Water Stress categories (0-100 scale)
WATER_STRESS_CATEGORIES = {
    (80, 101): "Abundant",
    (60, 80): "Moderate",
    (40, 60): "Stressed",
    (20, 40): "Critical",
    (0, 20): "Severe",
}

# Flood Risk categories (0-100 scale)
FLOOD_RISK_CATEGORIES = {
    (70, 101): "Critical",
    (50, 70): "High",
    (30, 50): "Moderate",
    (0, 30): "No Risk",
}

# Minimum prediction_errors rows before a horizon is considered validated
ACCURACY_MIN_SAMPLES = 5

# Assets whose discharge path is upstream physics routing (not the ML target)
PHYSICS_ASSETS = frozenset({3, 4, 5, 6, 7, 8, 11})

# WAI severity thresholds (from domain/water_classifier.py)
WAI_THRESHOLDS = {
    "critical_min": 25.0,
    "severe_min": 40.0,
    "stressed_min": 55.0,
    "moderate_min": 70.0,
}


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class DischargePrediction:
    """Expected discharge with confidence interval."""
    value_m3s: float
    confidence_lower_m3s: float
    confidence_upper_m3s: float
    value_cusecs: float
    confidence_lower_cusecs: float
    confidence_upper_cusecs: float
    unit: str = "m3/s"
    # How the interval was produced: "quantile_q10_q90" | "residual_p90" |
    # "r2_band" | "physics_band" | "pct_heuristic"
    ci_method: Optional[str] = None


@dataclass
class WaterStressPrediction:
    """Water availability index prediction."""
    value: int  # 0-100
    category: str
    trend: int  # Change from previous period (+/-)
    components: Dict[str, int] = field(default_factory=dict)


@dataclass
class FloodRiskPrediction:
    """Flood risk score prediction."""
    value: int  # 0-100
    category: str
    confidence: Optional[float]  # 0-1, or None until validated
    drivers: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class RainfallPrediction:
    """Rainfall forecast with probability."""
    value_mm: float
    probability: float  # Probability of exceeding normal
    unit: str = "mm"


@dataclass
class LeadTimeForecast:
    """Complete forecast for a single lead time."""
    lead_time_days: int
    water_stress: WaterStressPrediction
    flood_risk: FloodRiskPrediction
    discharge: DischargePrediction
    rainfall: RainfallPrediction
    confidence: Optional[float]  # None until walk-forward validation fills it


@dataclass
class AssetPrediction:
    """Complete prediction for an asset across all lead times."""
    asset_id: int
    asset_name: str
    asset_type: str
    timestamp: str
    predictions: Dict[str, LeadTimeForecast]  # "3_day", "7_day", "14_day"
    alerts: List[Dict[str, str]]
    model_metadata: Dict[str, object]


# ─── Helper Functions ────────────────────────────────────────────────────────

def _classify_water_stress(wai: float) -> str:
    """Map WAI score (0-100) to category."""
    for (low, high), category in WATER_STRESS_CATEGORIES.items():
        if low <= wai < high:
            return category
    return "Severe"


def _classify_flood_risk(score: float) -> str:
    """Map flood risk score (0-100) to category."""
    for (low, high), category in FLOOD_RISK_CATEGORIES.items():
        if low <= score < high:
            return category
    return "No Risk"


def _cusecs_to_m3s(cusecs: float) -> float:
    """Convert cusecs to m3/s."""
    return cusecs * CUSECS_TO_M3S


def _compute_water_stress_from_wai(
    wai_score: Optional[float],
    rainfall_anomaly: Optional[float] = None,
    et_anomaly: Optional[float] = None,
    discharge_trend: Optional[float] = None,
) -> WaterStressPrediction:
    """Compute water stress prediction from WAI and contributing factors."""
    if wai_score is None:
        # No real-time or weekly WAI available — leave stress unscored
        # rather than inventing a moderate default.
        return WaterStressPrediction(
            value=0,
            category="No Data",
            trend=0,
            components={},
        )

    value = int(round(wai_score))
    category = _classify_water_stress(value)

    # Compute trend from discharge change
    trend = 0
    if discharge_trend is not None:
        trend = int(round(discharge_trend))

    # Component breakdown
    components = {}
    if rainfall_anomaly is not None:
        # Map rainfall anomaly to 0-100 scale
        # Positive anomaly = more water = higher score
        components["rainfall"] = int(min(100, max(0, 50 + rainfall_anomaly * 2)))
    if et_anomaly is not None:
        # ET anomaly: high ET = more water loss = lower score
        components["et_anomaly"] = int(min(100, max(0, 50 - et_anomaly)))
    if discharge_trend is not None:
        components["surface_water"] = int(min(100, max(0, 50 + discharge_trend)))

    return WaterStressPrediction(
        value=value,
        category=category,
        trend=trend,
        components=components,
    )


def _compute_flood_risk(
    flood_probability: Optional[float],
    predicted_discharge_m3s: float,
    warning_threshold_m3s: Optional[float],
    danger_threshold_m3s: Optional[float],
    rainfall_mm: Optional[float] = None,
    discharge_trend: Optional[float] = None,
) -> FloodRiskPrediction:
    """Compute flood risk score from classifier probability and discharge."""

    # Base score from classifier probability (0-1 -> 0-100)
    if flood_probability is not None:
        base_score = int(round(flood_probability * 100))
    else:
        base_score = 0

    # Adjust based on discharge proximity to thresholds
    threshold_factor = 0
    if warning_threshold_m3s and warning_threshold_m3s > 0:
        ratio = predicted_discharge_m3s / warning_threshold_m3s
        if ratio >= 1.0:
            threshold_factor = min(30, int((ratio - 1.0) * 50))
        elif ratio >= 0.8:
            threshold_factor = int((ratio - 0.8) * 50)

    # Adjust for rainfall
    rainfall_factor = 0
    if rainfall_mm is not None and rainfall_mm > 50:
        rainfall_factor = min(15, int((rainfall_mm - 50) / 10))

    # Adjust for discharge trend
    trend_factor = 0
    if discharge_trend is not None and discharge_trend > 10:
        trend_factor = min(10, int((discharge_trend - 10) / 5))

    # Combine factors (cap at 100)
    score = min(100, base_score + threshold_factor + rainfall_factor + trend_factor)
    score = max(0, score)

    category = _classify_flood_risk(score)

    # Flood-risk confidence stays None unless a caller supplies validated accuracy.
    confidence: Optional[float] = None

    # Risk drivers
    drivers = []
    if flood_probability is not None:
        drivers.append({
            "name": "Flood classifier",
            "value": f"{flood_probability:.1%} probability",
            "impact": "high" if flood_probability > 0.6 else "medium" if flood_probability > 0.3 else "low",
        })
    if discharge_trend is not None:
        direction = "increasing" if discharge_trend > 0 else "decreasing"
        drivers.append({
            "name": "Discharge trend",
            "value": f"{abs(discharge_trend):.1f}% {direction}",
            "impact": "high" if abs(discharge_trend) > 15 else "medium",
        })
    if rainfall_mm is not None:
        drivers.append({
            "name": "Rainfall forecast",
            "value": f"{rainfall_mm:.0f}mm expected",
            "impact": "high" if rainfall_mm > 80 else "medium" if rainfall_mm > 40 else "low",
        })

    return FloodRiskPrediction(
        value=score,
        category=category,
        confidence=confidence,
        drivers=drivers,
    )


def _compute_discharge_prediction(
    predicted_cusecs: float,
    lower_cusecs: float,
    upper_cusecs: float,
    ci_method: Optional[str] = None,
) -> DischargePrediction:
    """Convert discharge prediction from cusecs to m3/s with CI."""
    return DischargePrediction(
        value_m3s=round(_cusecs_to_m3s(predicted_cusecs), 1),
        confidence_lower_m3s=round(_cusecs_to_m3s(lower_cusecs), 1),
        confidence_upper_m3s=round(_cusecs_to_m3s(upper_cusecs), 1),
        value_cusecs=round(predicted_cusecs, 0),
        confidence_lower_cusecs=round(lower_cusecs, 0),
        confidence_upper_cusecs=round(upper_cusecs, 0),
        ci_method=ci_method,
    )


def _compute_rainfall_alert(
    precip_mm: Optional[float],
    normal_precip_mm: float = 30.0,  # Sep average for Pakistan
) -> RainfallPrediction:
    """Compute rainfall prediction with probability of exceeding normal."""
    if precip_mm is None:
        precip_mm = 0.0

    # Probability of exceeding normal (simple z-score-like)
    if normal_precip_mm > 0:
        ratio = precip_mm / normal_precip_mm
        probability = min(1.0, max(0.0, ratio * 0.7))
    else:
        probability = 0.5

    return RainfallPrediction(
        value_mm=round(precip_mm, 1),
        probability=round(probability, 2),
    )


# ─── Main Prediction Model ──────────────────────────────────────────────────

class AquaVisionPredictionModel:
    """
    Production forecasting model that wraps existing ML/physics models
    and outputs structured predictions for the AquaVision dashboard.

    Outputs per lead time:
    1. Water Stress Level (0-100)
    2. Flood Risk Score (0-100)
    3. Expected Discharge (m3/s) with 95% CI
    4. Rainfall Alert (mm) with probability
    """

    def __init__(self, session=None):
        self.session = session
        # asset_id -> target_field seen from its loaded ML model(s)
        self._ml_target_fields: Dict[int, str] = {}
        # asset_id -> {horizon: holdout ci_coverage_80 from training metadata}
        self._ml_ci_coverage: Dict[int, Dict[int, Optional[float]]] = {}

    def predict(
        self,
        asset_id: int,
        asset_name: str = "",
        asset_type: str = "barrage",
        lead_times: List[int] = [3, 7, 14],
    ) -> AssetPrediction:
        """
        Generate complete prediction for an asset.

        Args:
            asset_id: Database asset ID
            asset_name: Human-readable name
            asset_type: "reservoir" or "barrage"
            lead_times: List of forecast horizons in days

        Returns:
            AssetPrediction with all metrics for each lead time
        """
        from sqlalchemy import text as sql_text

        now = datetime.utcnow()
        predictions = {}
        alerts = []

        # Get current observation
        current_obs = self._get_current_observation(asset_id)
        if current_obs is None:
            logger.warning(f"No observation data for asset {asset_id}")
            return self._empty_prediction(asset_id, asset_name, asset_type, now)

        # Get WAI score for the asset's region
        wai_score, rainfall_anomaly, et_anomaly = self._get_wai_data(asset_id)

        # Get weather forecast
        weather = self._get_weather_forecast(asset_id)

        # Get flood classifier probability
        flood_prob = self._get_flood_probability(asset_id)

        # Get threshold levels
        warn_level, danger_level = self._get_thresholds(asset_id)

        # Get ML predictions from existing model
        ml_predictions = self._get_ml_predictions(asset_id)

        # Get upstream discharge for physics routing
        upstream_discharge = self._get_upstream_discharge(asset_id)

        # Real accuracy from prediction_errors (holdout seed + daily scorer)
        accuracy_by_lead = self._get_accuracy_by_lead(asset_id)

        for lead_time in lead_times:
            forecast = self._build_lead_time_forecast(
                asset_id=asset_id,
                asset_type=asset_type,
                lead_time=lead_time,
                current_obs=current_obs,
                wai_score=wai_score,
                rainfall_anomaly=rainfall_anomaly,
                et_anomaly=et_anomaly,
                weather=weather,
                flood_prob=flood_prob,
                warn_level=warn_level,
                danger_level=danger_level,
                ml_predictions=ml_predictions,
                upstream_discharge=upstream_discharge,
                confidence=accuracy_by_lead.get(lead_time),
            )
            predictions[f"{lead_time}_day"] = forecast

            # Generate alerts for this lead time
            lead_alerts = self._generate_alerts(
                asset_id=asset_id,
                asset_name=asset_name,
                lead_time=lead_time,
                forecast=forecast,
            )
            alerts.extend(lead_alerts)

        acc3 = accuracy_by_lead.get(3)
        acc7 = accuracy_by_lead.get(7)
        acc14 = accuracy_by_lead.get(14)
        validated = any(v is not None for v in (acc3, acc7, acc14))
        metadata = {
            "model_version": "2.0",
            "last_training": None,
            "accuracy_3day": acc3,
            "accuracy_7day": acc7,
            "accuracy_14day": acc14,
            "features_used": None,
            "prediction_method": self._get_prediction_method(asset_id),
            "accuracy_status": "VALIDATED" if validated else "NOT_VALIDATED",
            # Holdout coverage of the q10-q90 interval (honest, measured;
            # None for physics assets / models without quantile intervals)
            "ci_coverage_80": self._ml_ci_coverage.get(asset_id),
        }

        return AssetPrediction(
            asset_id=asset_id,
            asset_name=asset_name or f"Asset_{asset_id}",
            asset_type=asset_type,
            timestamp=now.isoformat(),
            predictions=predictions,
            alerts=alerts,
            model_metadata=metadata,
        )

    def _get_accuracy_by_lead(self, asset_id: int) -> Dict[int, Optional[float]]:
        """Accuracy 0-1 per lead time from prediction_errors (REAL, n>=ACCURACY_MIN_SAMPLES).

        accuracy = max(0, 1 - MAPE/100). Horizons with fewer samples return None
        so the UI shows "Not validated" instead of a fake score.
        """
        if self.session is None:
            return {}

        from sqlalchemy import text as sql_text

        try:
            rows = self.session.execute(
                sql_text("""
                    SELECT horizon, COUNT(*) AS n, AVG(error_pct) AS mape
                    FROM aquavision.prediction_errors
                    WHERE asset_id = :aid
                      AND data_origin = 'REAL'
                      AND horizon IN (3, 7, 14)
                    GROUP BY horizon
                """),
                {"aid": asset_id},
            ).mappings().all()
        except Exception as e:
            logger.debug("prediction_errors unavailable for asset %s: %s", asset_id, e)
            return {}

        out: Dict[int, Optional[float]] = {}
        for row in rows:
            n = int(row["n"] or 0)
            if n < ACCURACY_MIN_SAMPLES:
                out[int(row["horizon"])] = None
                continue
            mape = float(row["mape"] or 0.0)
            out[int(row["horizon"])] = max(0.0, min(1.0, 1.0 - mape / 100.0))
        return out

    def _get_current_observation(self, asset_id: int) -> Optional[Dict]:
        """Get latest observation for an asset."""
        if self.session is None:
            return None

        from sqlalchemy import text as sql_text

        row = self.session.execute(
            sql_text("""
                SELECT observed_at, water_level_ft, inflow_cusecs,
                       outflow_cusecs, discharge_cusecs
                FROM aquavision.water_observations
                WHERE asset_id = :aid
                ORDER BY observed_at DESC
                LIMIT 1
            """),
            {"aid": asset_id},
        ).mappings().first()

        if row is None:
            return None

        return {
            "observed_at": row["observed_at"],
            "water_level_ft": float(row["water_level_ft"]) if row["water_level_ft"] else None,
            "inflow_cusecs": float(row["inflow_cusecs"]) if row["inflow_cusecs"] else None,
            "outflow_cusecs": float(row["outflow_cusecs"]) if row["outflow_cusecs"] else None,
            "discharge_cusecs": float(row["discharge_cusecs"]) if row["discharge_cusecs"] else None,
        }

    def _get_wai_data(self, asset_id: int) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """WAI + anomalies for the asset.

        Prefer real-time composite from REAL observations (ml/models/wai_computer).
        Fall back to the latest weekly indicator only when real-time scoring is
        impossible (empty history). Never invent a default score.
        """
        if self.session is None:
            return None, None, None

        from ml.models.wai_computer import get_wai_for_prediction

        # Stale weekly indicator (GEE sync) — last resort only
        stale_wai = stale_rain = stale_et = None
        from sqlalchemy import text as sql_text

        asset_row = self.session.execute(
            sql_text("SELECT province FROM aquavision.water_assets WHERE id = :aid"),
            {"aid": asset_id},
        ).mappings().first()
        if asset_row is not None and asset_row["province"]:
            PROVINCE_TO_REGION = {
                "KPK": "Khyber Pakhtunkhwa",
                "Punjab": "Punjab",
                "Sindh": "Sindh",
                "Balochistan": "Balochistan",
                "AJK": "Azad Jammu and Kashmir",
            }
            region_name = PROVINCE_TO_REGION.get(asset_row["province"], asset_row["province"])
            region_row = self.session.execute(
                sql_text("SELECT id FROM shared.regions WHERE name = :name LIMIT 1"),
                {"name": region_name},
            ).mappings().first()
            if region_row is not None:
                wai_row = self.session.execute(
                    sql_text(
                        """
                        SELECT wai_score, rainfall_anomaly, et_anomaly
                        FROM aquavision.water_indicators_weekly
                        WHERE region_id = :rid
                        ORDER BY week_start_date DESC
                        LIMIT 1
                        """
                    ),
                    {"rid": region_row["id"]},
                ).mappings().first()
                if wai_row is not None:
                    stale_wai = float(wai_row["wai_score"]) if wai_row["wai_score"] else None
                    stale_rain = float(wai_row["rainfall_anomaly"]) if wai_row["rainfall_anomaly"] else None
                    stale_et = float(wai_row["et_anomaly"]) if wai_row["et_anomaly"] else None

        wai, rain, et = get_wai_for_prediction(self.session, asset_id, stale_indicator_wai=stale_wai)
        if rain is None:
            rain = stale_rain
        if et is None:
            et = stale_et
        return wai, rain, et

    def _get_weather_forecast(self, asset_id: int) -> Optional[Dict]:
        """Get weather forecast for an asset."""
        if self.session is None:
            return None

        from sqlalchemy import text as sql_text
        from datetime import date

        today = date.today()

        row = self.session.execute(
            sql_text("""
                SELECT precip_sum_mm, temp_max_c, temp_min_c,
                       humidity_mean_pct
                FROM aquavision.weather_forecasts
                WHERE asset_id = :aid
                  AND forecast_date >= :today
                ORDER BY forecast_date ASC
                LIMIT 7
            """),
            {"aid": asset_id, "today": today},
        ).mappings().first()

        if row is None:
            return None

        return {
            "precip_sum_mm": float(row["precip_sum_mm"]) if row["precip_sum_mm"] else 0.0,
            "temp_max_c": float(row["temp_max_c"]) if row["temp_max_c"] else None,
            "temp_min_c": float(row["temp_min_c"]) if row["temp_min_c"] else None,
            "humidity_mean_pct": float(row["humidity_mean_pct"]) if row["humidity_mean_pct"] else None,
        }

    def _get_flood_probability(self, asset_id: int) -> Optional[float]:
        """Get flood classifier probability."""
        try:
            from pathlib import Path
            from ml.models.flood_classifier import FloodClassifier

            model_path = Path(__file__).parent.parent / "data" / "models" / f"flood_classifier_asset_{asset_id}.pkl"
            if not model_path.exists():
                return None

            clf = FloodClassifier.load(asset_id, model_path)

            # Get recent observations for classifier
            from sqlalchemy import text as sql_text

            rows = self.session.execute(
                sql_text("""
                    SELECT observed_at, inflow_cusecs, outflow_cusecs,
                           water_level_ft, discharge_cusecs
                    FROM aquavision.water_observations
                    WHERE asset_id = :aid
                    ORDER BY observed_at DESC
                    LIMIT 60
                """),
                {"aid": asset_id},
            ).mappings().all()

            if not rows:
                return None

            import pandas as pd
            from decimal import Decimal

            df = pd.DataFrame(list(reversed(rows)))
            for col in df.columns:
                if df[col].dtype == object:
                    try:
                        df[col] = df[col].apply(lambda x: float(x) if isinstance(x, (Decimal, int)) else x)
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    except Exception:
                        pass

            result = clf.predict(df)
            if "error" in result:
                return None

            return result.get("flood_probability")

        except Exception as e:
            logger.debug(f"Flood classifier not available for asset {asset_id}: {e}")
            return None

    def _get_thresholds(self, asset_id: int) -> Tuple[Optional[float], Optional[float]]:
        """Discharge warning/danger thresholds in m3/s (or None if unknown).

        water_assets.warning_level_ft / critical_level_ft are ELEVATION in feet,
        not discharge. Comparing them to predicted m3/s is a unit bug. Without a
        rating curve we return None so flood risk never mixes ft with m3/s.
        """
        return None, None

    def _get_ml_predictions(self, asset_id: int) -> Dict[int, Dict]:
        """Get ML predictions from existing FloodPredictor."""
        predictions = {}

        try:
            from ml.models.flood_predictor import FloodPredictor
            from ml.features.feature_engineering import FloodFeatureBuilder

            predictor = FloodPredictor()
            builder = FloodFeatureBuilder(self.session)

            for horizon in [3, 7, 14]:
                X, feature_names = builder.build_prediction_features(
                    asset_id=asset_id,
                    as_of_date=datetime.utcnow(),
                )

                if X is None:
                    continue

                pred = predictor.predict(
                    asset_id=asset_id,
                    asset_name="",
                    X=X,
                    feature_names=feature_names,
                    horizon=horizon,
                )

                if pred:
                    # Map the model's actual target to a flow value in cusecs.
                    # A level-target value is FEET — never treat it as cusecs
                    # (that was a unit bug); such models simply don't contribute
                    # to the discharge forecast and the caller falls back.
                    if pred.predicted_discharge is not None:
                        predicted_cusecs = pred.predicted_discharge
                    elif pred.predicted_outflow is not None:
                        predicted_cusecs = pred.predicted_outflow
                    elif pred.predicted_inflow is not None:
                        predicted_cusecs = pred.predicted_inflow
                    else:
                        logger.debug(
                            "asset %s horizon %ds: target_field=%s has no flow "
                            "output — skipping discharge contribution",
                            asset_id, horizon, pred.target_field,
                        )
                        continue

                    self._ml_target_fields[asset_id] = pred.target_field
                    cov = predictor.training_metrics.get(
                        f"{asset_id}_{horizon}", {}
                    ).get("ci_coverage_80")
                    if cov is not None:
                        self._ml_ci_coverage.setdefault(asset_id, {})[horizon] = cov
                    predictions[horizon] = {
                        "predicted_cusecs": predicted_cusecs,
                        "lower_bound": pred.lower_bound,
                        "upper_bound": pred.upper_bound,
                        "risk_score": pred.risk_score,
                        "risk_level": pred.risk_level,
                        "target_field": pred.target_field,
                        "ci_method": pred.ci_method,
                    }

        except Exception as e:
            logger.debug(f"ML predictions not available for asset {asset_id}: {e}")

        return predictions

    def _get_upstream_discharge(self, asset_id: int) -> Optional[float]:
        """Get upstream discharge for physics routing assets."""
        if self.session is None:
            return None

        from sqlalchemy import text as sql_text

        # Get upstream asset IDs
        UPSTREAM_MAP = {
            3: [1, 9],   # Chashma: Tarbela + Kabul
            4: [1, 9],   # Kalabagh: Tarbela + Kabul
            5: [4],      # Taunsa: Kalabagh
            6: [5],      # Guddu: Taunsa
            7: [6],      # Sukkur: Guddu
            8: [7],      # Kotri: Sukkur
            11: [10, 2], # Panjnad: Chenab + Mangla
        }

        upstream_ids = UPSTREAM_MAP.get(asset_id, [])
        if not upstream_ids:
            return None

        placeholders = ", ".join([f":a{i}" for i in range(len(upstream_ids))])
        params = {f"a{i}": aid for i, aid in enumerate(upstream_ids)}

        rows = self.session.execute(
            sql_text(f"""
                SELECT asset_id, discharge_cusecs, inflow_cusecs
                FROM aquavision.water_observations
                WHERE asset_id IN ({placeholders})
                ORDER BY observed_at DESC
            """),
            params,
        ).mappings().all()

        # Get latest per asset
        latest = {}
        for row in rows:
            aid = row["asset_id"]
            if aid not in latest:
                discharge = row["discharge_cusecs"] or row["inflow_cusecs"]
                latest[aid] = float(discharge) if discharge else 0

        if not latest:
            return None

        return sum(latest.values())

    def _get_prediction_method(self, asset_id: int) -> str:
        """Human-readable prediction method for metadata (honest provenance)."""
        if asset_id in PHYSICS_ASSETS:
            return "physics_routing"
        target = self._ml_target_fields.get(asset_id)
        if target in ("discharge", "outflow", "inflow"):
            return f"ml_xgboost_{target}"
        return "ml_xgboost"

    def _get_discharge_trend(self, asset_id: int) -> Optional[float]:
        """Get daily discharge trend (% change per day) over the last 7 days.

        Uses whatever flow series the asset actually has — discharge, outflow
        (reservoir release), or inflow — in that priority order. Reservoirs
        rarely populate discharge_cusecs, so COALESCE matters here.

        Returns average daily % change. Positive = increasing, negative = decreasing.
        Returns None if insufficient data.
        """
        if self.session is None:
            return None

        from sqlalchemy import text as sql_text

        rows = self.session.execute(
            sql_text("""
                SELECT observed_at,
                       COALESCE(discharge_cusecs, outflow_cusecs, inflow_cusecs) AS flow_cusecs
                FROM aquavision.water_observations
                WHERE asset_id = :aid
                  AND COALESCE(discharge_cusecs, outflow_cusecs, inflow_cusecs) IS NOT NULL
                  AND COALESCE(discharge_cusecs, outflow_cusecs, inflow_cusecs) > 0
                ORDER BY observed_at DESC
                LIMIT 14
            """),
            {"aid": asset_id},
        ).mappings().all()

        if len(rows) < 7:
            return None

        # Split into recent (last 7 days) and prior (7 days before that)
        recent = [float(r["flow_cusecs"]) for r in rows[:7]]
        prior = [float(r["flow_cusecs"]) for r in rows[7:14]] if len(rows) >= 14 else None

        if prior and sum(prior) > 0:
            recent_avg = sum(recent) / len(recent)
            prior_avg = sum(prior) / len(prior)
            # Daily % change (over 7-day gap)
            total_change_pct = ((recent_avg - prior_avg) / prior_avg) * 100
            return total_change_pct / 7  # daily rate
        elif len(recent) >= 2:
            # Use linear slope of recent data
            import statistics
            n = len(recent)
            x_mean = (n - 1) / 2
            y_mean = statistics.mean(recent)
            numerator = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            if denominator > 0:
                slope = numerator / denominator
                # Convert to daily % change
                return (slope / y_mean) * 100 if y_mean > 0 else None
        return None

    def _build_lead_time_forecast(
        self,
        asset_id: int,
        asset_type: str,
        lead_time: int,
        current_obs: Dict,
        wai_score: Optional[float],
        rainfall_anomaly: Optional[float],
        et_anomaly: Optional[float],
        weather: Optional[Dict],
        flood_prob: Optional[float],
        warn_level: Optional[float],
        danger_level: Optional[float],
        ml_predictions: Dict,
        upstream_discharge: Optional[float],
        confidence: Optional[float] = None,
    ) -> LeadTimeForecast:
        """Build complete forecast for a single lead time."""

        # 1. Water Stress
        discharge_trend = None
        if lead_time in ml_predictions:
            # Estimate trend from ML prediction vs current — baseline must match
            # the model's target (an outflow model compares against outflow, not
            # inflow, or the trend sign/magnitude is nonsense).
            from ml.targets import flow_baseline_cusecs

            pred = ml_predictions[lead_time]
            current_discharge = flow_baseline_cusecs(
                current_obs, pred.get("target_field")
            )
            predicted_cusecs = pred.get("predicted_cusecs", 0)
            if current_discharge > 0 and predicted_cusecs > 0:
                # Trend = percentage change
                discharge_trend = ((predicted_cusecs - current_discharge) / current_discharge) * 100
        else:
            # For physics routing assets, use discharge trend projected over lead time
            physics_trend = self._get_discharge_trend(asset_id)
            if physics_trend is not None:
                # Linear projection, capped at ±50%
                total_change = physics_trend * lead_time
                discharge_trend = max(-50, min(50, total_change))

        water_stress = _compute_water_stress_from_wai(
            wai_score=wai_score,
            rainfall_anomaly=rainfall_anomaly,
            et_anomaly=et_anomaly,
            discharge_trend=discharge_trend,
        )

        # 2. Discharge prediction
        # Baseline = current flow matching the ML target when available
        # (reservoir outflow models must be compared against outflow).
        from ml.targets import flow_baseline_cusecs as _flow_baseline

        ml_pred = ml_predictions.get(lead_time)
        current_discharge = _flow_baseline(
            current_obs, ml_pred.get("target_field") if ml_pred else None
        )

        if current_discharge <= 0:
            current_discharge = 0

        # Get discharge trend for this asset (daily % change over last 7 days)
        discharge_trend_pct = self._get_discharge_trend(asset_id)

        # For physics routing assets, project upstream discharge with trend
        if upstream_discharge and upstream_discharge > 0:
            # Project upstream discharge forward using trend
            if discharge_trend_pct is not None and current_discharge > 0:
                # Dampened projection: short-term = full trend, long-term dampened
                # 3-day: 60% of daily trend, 7-day: 25%, 14-day: 12%
                dampening = {3: 0.6, 7: 0.25, 14: 0.12}.get(lead_time, 0.2)
                effective_daily = discharge_trend_pct * dampening
                total_change = effective_daily * lead_time
                total_change = max(-40, min(40, total_change))
                predicted_cusecs = upstream_discharge * (1 + total_change / 100)
            else:
                predicted_cusecs = upstream_discharge

            # CI widens with lead time: ±10% at 3d, ±15% at 7d, ±22% at 14d
            ci_factor = 0.10 + 0.02 * lead_time
            lower_cusecs = predicted_cusecs * (1 - ci_factor)
            upper_cusecs = predicted_cusecs * (1 + ci_factor)
            ci_method = "physics_band"
        # If ML prediction available, use it directly as discharge
        elif lead_time in ml_predictions:
            pred = ml_predictions[lead_time]
            predicted_cusecs = pred.get("predicted_cusecs", current_discharge)
            # Use CI from flood_predictor (quantile / residual / r2 band)
            lower_bound = pred.get("lower_bound")
            upper_bound = pred.get("upper_bound")
            ci_method = pred.get("ci_method")
            if lower_bound is not None and upper_bound is not None:
                lower_cusecs = lower_bound
                upper_cusecs = upper_bound
                if ci_method is None:
                    ci_method = "r2_band"
            else:
                # Fallback: ±15%
                lower_cusecs = predicted_cusecs * 0.85
                upper_cusecs = predicted_cusecs * 1.15
                ci_method = "pct_heuristic"
        else:
            predicted_cusecs = current_discharge
            lower_cusecs = predicted_cusecs * 0.9
            upper_cusecs = predicted_cusecs * 1.1
            ci_method = "pct_heuristic"

        # Ensure non-negative
        lower_cusecs = max(0, lower_cusecs)

        discharge = _compute_discharge_prediction(
            predicted_cusecs=predicted_cusecs,
            lower_cusecs=lower_cusecs,
            upper_cusecs=upper_cusecs,
            ci_method=ci_method,
        )

        # 3. Flood Risk
        rainfall_mm = None
        if weather:
            rainfall_mm = weather.get("precip_sum_mm", 0) * (lead_time / 7)

        flood_risk = _compute_flood_risk(
            flood_probability=flood_prob,
            predicted_discharge_m3s=discharge.value_m3s,
            warning_threshold_m3s=warn_level,
            danger_threshold_m3s=danger_level,
            rainfall_mm=rainfall_mm,
            discharge_trend=discharge_trend,
        )

        # 4. Rainfall Alert
        rainfall = _compute_rainfall_alert(
            precip_mm=rainfall_mm,
            normal_precip_mm=30.0 * (lead_time / 7),
        )

        # Real accuracy from prediction_errors for this lead time (None until validated)
        return LeadTimeForecast(
            lead_time_days=lead_time,
            water_stress=water_stress,
            flood_risk=flood_risk,
            discharge=discharge,
            rainfall=rainfall,
            confidence=confidence,
        )

    def _generate_alerts(
        self,
        asset_id: int,
        asset_name: str,
        lead_time: int,
        forecast: LeadTimeForecast,
    ) -> List[Dict[str, str]]:
        """Generate alerts based on forecast."""
        alerts = []

        # Water stress alert
        if forecast.water_stress.value <= 40:
            alerts.append({
                "level": "CRITICAL",
                "type": "WATER_STRESS",
                "score": forecast.water_stress.value,
                "message": f"{asset_name}: Water stress at {forecast.water_stress.value}/100 ({forecast.water_stress.category}). Supply restrictions may be needed in {lead_time} days.",
                "action": "Contact IRD, prepare contingency plans",
                "lead_time": f"{lead_time}_day",
                "timestamp": datetime.utcnow().isoformat(),
            })
        elif forecast.water_stress.value <= 60:
            alerts.append({
                "level": "WARNING",
                "type": "WATER_STRESS",
                "score": forecast.water_stress.value,
                "message": f"{asset_name}: Water stress at {forecast.water_stress.value}/100 ({forecast.water_stress.category}). Monitor conditions.",
                "action": "Monitor rainfall trend",
                "lead_time": f"{lead_time}_day",
                "timestamp": datetime.utcnow().isoformat(),
            })

        # Flood risk alert
        if forecast.flood_risk.value >= 70:
            alerts.append({
                "level": "CRITICAL",
                "type": "FLOOD_RISK",
                "score": forecast.flood_risk.value,
                "message": f"{asset_name}: Flood risk at {forecast.flood_risk.value}/100 ({forecast.flood_risk.category}). Prepare evacuation plans.",
                "action": "Activate emergency protocols",
                "lead_time": f"{lead_time}_day",
                "timestamp": datetime.utcnow().isoformat(),
            })
        elif forecast.flood_risk.value >= 50:
            alerts.append({
                "level": "HIGH",
                "type": "FLOOD_RISK",
                "score": forecast.flood_risk.value,
                "message": f"{asset_name}: Flood risk at {forecast.flood_risk.value}/100 ({forecast.flood_risk.category}). Monitor weather forecasts.",
                "action": "Prepare contingency plans",
                "lead_time": f"{lead_time}_day",
                "timestamp": datetime.utcnow().isoformat(),
            })
        elif forecast.flood_risk.value >= 30:
            alerts.append({
                "level": "WARNING",
                "type": "FLOOD_RISK",
                "score": forecast.flood_risk.value,
                "message": f"{asset_name}: Flood risk at {forecast.flood_risk.value}/100 ({forecast.flood_risk.category}).",
                "action": "Monitor conditions",
                "lead_time": f"{lead_time}_day",
                "timestamp": datetime.utcnow().isoformat(),
            })

        # Rainfall alert
        if forecast.rainfall.value_mm > 80:
            alerts.append({
                "level": "WARNING",
                "type": "RAINFALL",
                "score": forecast.rainfall.value_mm,
                "message": f"{asset_name}: Heavy rainfall expected ({forecast.rainfall.value_mm:.0f}mm, {forecast.rainfall.probability:.0%} probability).",
                "action": "Monitor river levels",
                "lead_time": f"{lead_time}_day",
                "timestamp": datetime.utcnow().isoformat(),
            })

        self._persist_alerts(asset_id, lead_time, alerts)
        return alerts

    def _persist_alerts(
        self,
        asset_id: int,
        lead_time: int,
        alerts: List[Dict],
    ) -> None:
        """Persist actionable v2 alerts into water_operational_alerts so they
        enter the role-based workflow (UC-1). Dedup: one open alert per
        (asset, type) — the DB unique index enforces it, we check first.
        """
        if self.session is None or not alerts:
            return

        try:
            from datetime import timezone as _tz
            from sqlalchemy import select
            from infrastructure.alerts.workflow import OPEN_STATUSES, log_event, sla_due_at
            from infrastructure.db.models import WaterOperationalAlert

            persist_levels = {"CRITICAL", "HIGH"}
            severity_map = {"CRITICAL": "CRITICAL", "HIGH": "WARNING", "WARNING": "WARNING"}

            for a in alerts:
                level = a.get("level", "")
                atype = a.get("type", "")
                # WATER_STRESS WARNING is routine (weekly WAI) -> skip;
                # FLOOD_RISK/RAINFALL WARNING persists (UC-1 / UC-4).
                if level not in persist_levels and not (
                    level == "WARNING" and atype in ("FLOOD_RISK", "RAINFALL")
                ):
                    continue
                if level == "WARNING" and atype == "WATER_STRESS":
                    continue

                db_type = f"ML_{atype}"
                existing = self.session.execute(
                    select(WaterOperationalAlert).where(
                        WaterOperationalAlert.asset_id == asset_id,
                        WaterOperationalAlert.alert_type == db_type,
                        WaterOperationalAlert.status.in_(OPEN_STATUSES),
                    )
                ).scalar_one_or_none()
                if existing:
                    continue  # one open alert per (asset, type)

                alert = WaterOperationalAlert(
                    asset_id=asset_id,
                    alert_type=db_type,
                    severity=severity_map.get(level, "WARNING"),
                    message=a.get("message", ""),
                    status="NEW",
                    alert_source="ML_V2",
                    alert_domain="FORECAST",
                    model_version="2.0",
                    triggered_value=float(a["score"]) if a.get("score") is not None else None,
                )
                alert.sla_due_at = sla_due_at(alert.severity, datetime.now(_tz.utc))
                self.session.add(alert)
                self.session.flush()
                log_event(
                    self.session,
                    alert_id=alert.id, action="CREATED",
                    performed_by="SYSTEM", actor_role="SYSTEM",
                    old_status=None, new_status="NEW",
                    notes=alert.message,
                    payload={"lead_time": lead_time, "level": level, "score": a.get("score")},
                )
                self.session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist v2 alert for asset {asset_id}: {e}")
            try:
                self.session.rollback()
            except Exception:
                pass

    def _empty_prediction(
        self,
        asset_id: int,
        asset_name: str,
        asset_type: str,
        now: datetime,
    ) -> AssetPrediction:
        """Return empty prediction when no data available."""
        empty_stress = WaterStressPrediction(value=50, category="Moderate", trend=0)
        empty_risk = FloodRiskPrediction(value=0, category="No Risk", confidence=0)
        empty_discharge = DischargePrediction(
            value_m3s=0, confidence_lower_m3s=0, confidence_upper_m3s=0,
            value_cusecs=0, confidence_lower_cusecs=0, confidence_upper_cusecs=0,
        )
        empty_rainfall = RainfallPrediction(value_mm=0, probability=0)

        predictions = {}
        for lt in [3, 7, 14]:
            predictions[f"{lt}_day"] = LeadTimeForecast(
                lead_time_days=lt,
                water_stress=empty_stress,
                flood_risk=empty_risk,
                discharge=empty_discharge,
                rainfall=empty_rainfall,
                confidence=0,
            )

        return AssetPrediction(
            asset_id=asset_id,
            asset_name=asset_name or f"Asset_{asset_id}",
            asset_type=asset_type,
            timestamp=now.isoformat(),
            predictions=predictions,
            alerts=[],
            model_metadata={"model_version": "2.0", "status": "NO_DATA"},
        )
