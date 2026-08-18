# ml/models/anomaly_detector.py
# Isolation Forest anomaly detector for water observations.
# Detects unusual level/inflow/outflow patterns per asset.
# Unsupervised — no labeled anomaly data needed.
#
# Phase 2B: Added model_version and model_status to artifacts and output.

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
import joblib
from sqlalchemy.orm import Session

logger = logging.getLogger("aquavision.ml.anomaly_detector")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models", "anomaly_if")
os.makedirs(MODEL_DIR, exist_ok=True)

# Model status label — displayed in all ML outputs
MODEL_STATUS = "EXPERIMENTAL"
MODEL_VERSION = "iforest-v1.0"


@dataclass
class AnomalyResult:
    """Anomaly detection result for a single observation.

    NOTE: This model is EXPERIMENTAL. Anomaly scores are advisory only.
    Do not use for operational decisions without human review.
    """
    asset_id: int
    asset_name: str
    observed_at: str
    anomaly_score: float  # -1 (anomaly) to 1 (normal)
    is_anomaly: bool
    anomaly_features: List[str]  # Which features triggered anomaly
    severity: str  # NORMAL, LOW, MODERATE, HIGH
    model_version: str = MODEL_VERSION
    model_status: str = MODEL_STATUS
    details: Dict[str, float] = field(default_factory=dict)


class AnomalyDetector:
    """Isolation Forest anomaly detector for water observations.

    Detects:
    - Unusually high/low water levels relative to recent history
    - Unusual inflow/outflow patterns
    - Seasonal anomalies (e.g., flood in dry season)
    - Rate-of-change anomalies
    """

    def __init__(self):
        os.makedirs(MODEL_DIR, exist_ok=True)

    def _build_features(
        self,
        levels: np.ndarray,
        inflows: np.ndarray,
        outflows: np.ndarray,
        timestamps: np.ndarray,
    ) -> Tuple[np.ndarray, List[str]]:
        """Build feature matrix from observation time series.

        Features:
        - Current values: level, inflow, outflow
        - Lag features: t-1, t-3, t-7
        - Rolling stats: 7d mean/std
        - Rate of change: 1d, 3d
        - Seasonal: day_of_year sin/cos
        - Derived: inflow/outflow ratio, level deviation from rolling mean
        """
        n = len(levels)
        feature_names = []
        features = []

        # Current values
        features.append(levels)
        feature_names.append("level")
        features.append(inflows)
        feature_names.append("inflow")
        features.append(outflows)
        feature_names.append("outflow")

        # Lag features (fill with rolling mean for first observations)
        for lag in [1, 3, 7]:
            lagged = np.roll(levels, lag)
            lagged[:lag] = np.nanmean(levels[:lag])
            features.append(lagged)
            feature_names.append(f"level_lag_{lag}")

            lagged = np.roll(inflows, lag)
            lagged[:lag] = np.nanmean(inflows[:lag])
            features.append(lagged)
            feature_names.append(f"inflow_lag_{lag}")

        # Rolling mean and std (window=7)
        for window in [7]:
            rm = np.full(n, np.nanmean(levels))
            rs = np.zeros(n)
            for i in range(window, n):
                rm[i] = np.mean(levels[i - window:i])
                rs[i] = np.std(levels[i - window:i]) + 1e-8
            features.append(rm)
            feature_names.append(f"level_rollmean_{window}")
            features.append(rs)
            feature_names.append(f"level_rollstd_{window}")

            rm = np.full(n, np.nanmean(inflows))
            for i in range(window, n):
                rm[i] = np.mean(inflows[i - window:i])
            features.append(rm)
            feature_names.append(f"inflow_rollmean_{window}")

        # Rate of change
        roc1 = np.zeros(n)
        roc1[1:] = (levels[1:] - levels[:-1]) / (np.abs(levels[:-1]) + 1e-8)
        features.append(roc1)
        feature_names.append("level_roc_1d")

        roc3 = np.zeros(n)
        roc3[3:] = (levels[3:] - levels[:-3]) / (np.abs(levels[:-3]) + 1e-8)
        features.append(roc3)
        feature_names.append("level_roc_3d")

        inflow_roc1 = np.zeros(n)
        inflow_roc1[1:] = (inflows[1:] - inflows[:-1]) / (np.abs(inflows[:-1]) + 1e-8)
        features.append(inflow_roc1)
        feature_names.append("inflow_roc_1d")

        # Inflow/outflow ratio
        ratio = inflows / (outflows + 1e-8)
        features.append(ratio)
        feature_names.append("inflow_outflow_ratio")

        # Level deviation from rolling mean
        deviation = levels - rm
        features.append(deviation)
        feature_names.append("level_deviation")

        # Seasonal encoding
        day_of_year = np.array([int(t.strftime("%j")) if hasattr(t, "strftime") else 1 for t in timestamps])
        features.append(np.sin(2 * np.pi * day_of_year / 365.25))
        feature_names.append("doy_sin")
        features.append(np.cos(2 * np.pi * day_of_year / 365.25))
        feature_names.append("doy_cos")

        X = np.column_stack(features)
        return X, feature_names

    def train(
        self,
        asset_id: int,
        asset_name: str,
        session: Session,
        contamination: float = 0.15,
    ) -> Optional[Dict]:
        """Train Isolation Forest model for a single asset.

        Args:
            asset_id: Asset ID
            asset_name: Human-readable name
            session: DB session
            contamination: Expected fraction of anomalies (0.05-0.20)

        Returns:
            Training metrics dict or None if insufficient data
        """
        from infrastructure.db.models import WaterObservation

        observations = (
            session.query(WaterObservation)
            .filter(WaterObservation.asset_id == asset_id)
            .order_by(WaterObservation.observed_at.asc())
            .all()
        )

        if len(observations) < 10:
            logger.warning(f"Asset {asset_name}: only {len(observations)} observations, need 10+")
            return None

        levels = np.array([float(o.water_level_ft or 0) for o in observations])
        inflows = np.array([float(o.inflow_cusecs or 0) for o in observations])
        outflows = np.array([float(o.outflow_cusecs or 0) for o in observations])
        timestamps = np.array([o.observed_at for o in observations])

        X, feature_names = self._build_features(levels, inflows, outflows, timestamps)

        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = IsolationForest(
            n_estimators=100,
            contamination=contamination,
            max_samples=min(25, len(X)),
            random_state=42,
        )
        model.fit(X_scaled)

        # Evaluate on training data
        predictions = model.predict(X_scaled)
        scores = model.decision_function(X_scaled)
        n_anomalies = int(np.sum(predictions == -1))

        # Save model
        model_path = os.path.join(MODEL_DIR, f"anomaly_{asset_id}.joblib")
        joblib.dump({
            "model": model,
            "scaler": scaler,
            "feature_names": feature_names,
            "model_version": MODEL_VERSION,
            "model_status": MODEL_STATUS,
            "trained_at": datetime.utcnow().isoformat(),
            "training_samples": len(observations),
            "contamination": contamination,
        }, model_path)

        logger.info(
            f"Asset {asset_name}: trained Isolation Forest, "
            f"{len(observations)} samples, {n_anomalies} anomalies detected"
        )

        return {
            "asset_id": asset_id,
            "asset_name": asset_name,
            "samples": len(observations),
            "features": len(feature_names),
            "anomalies_detected": n_anomalies,
            "contamination": contamination,
        }

    def predict(
        self,
        asset_id: int,
        asset_name: str,
        session: Session,
        top_n: int = 5,
    ) -> List[AnomalyResult]:
        """Run anomaly detection on recent observations.

        Returns the most anomalous observations sorted by severity.
        """
        from infrastructure.db.models import WaterObservation

        model_path = os.path.join(MODEL_DIR, f"anomaly_{asset_id}.joblib")
        if not os.path.exists(model_path):
            return []

        artifact = joblib.load(model_path)
        model = artifact["model"]
        scaler = artifact["scaler"]

        observations = (
            session.query(WaterObservation)
            .filter(WaterObservation.asset_id == asset_id)
            .order_by(WaterObservation.observed_at.asc())
            .all()
        )

        if len(observations) < 5:
            return []

        levels = np.array([float(o.water_level_ft or 0) for o in observations])
        inflows = np.array([float(o.inflow_cusecs or 0) for o in observations])
        outflows = np.array([float(o.outflow_cusecs or 0) for o in observations])
        timestamps = np.array([o.observed_at for o in observations])

        X, feature_names = self._build_features(levels, inflows, outflows, timestamps)
        X_scaled = scaler.transform(X)

        predictions = model.predict(X_scaled)
        scores = model.decision_function(X_scaled)

        # Build results for anomalous observations
        anomaly_results = []
        for i, (obs, pred, score) in enumerate(zip(observations, predictions, scores)):
            if pred == -1:
                # Determine which features are most anomalous
                feature_scores = np.abs(X_scaled[i])
                top_indices = np.argsort(feature_scores)[::-1][:3]
                anomaly_features = [feature_names[j] for j in top_indices if feature_scores[j] > 1.0]

                # Severity based on anomaly score
                if score < -0.3:
                    severity = "HIGH"
                elif score < -0.15:
                    severity = "MODERATE"
                else:
                    severity = "LOW"

                details = {
                    "level_ft": float(obs.water_level_ft or 0),
                    "inflow_cusecs": float(obs.inflow_cusecs or 0),
                    "outflow_cusecs": float(obs.outflow_cusecs or 0),
                }

                anomaly_results.append(AnomalyResult(
                    asset_id=asset_id,
                    asset_name=asset_name,
                    observed_at=obs.observed_at.isoformat() if obs.observed_at else "",
                    anomaly_score=float(score),
                    is_anomaly=True,
                    anomaly_features=anomaly_features,
                    severity=severity,
                    details=details,
                ))

        # Sort by score (most anomalous first)
        anomaly_results.sort(key=lambda r: r.anomaly_score)
        return anomaly_results[:top_n]

    def train_all(self, session: Session) -> List[Dict]:
        """Train anomaly detectors for all assets with sufficient data."""
        from infrastructure.db.models import WaterAsset

        assets = session.query(WaterAsset).all()
        results = []

        for asset in assets:
            result = self.train(
                asset_id=asset.id,
                asset_name=asset.canonical_name,
                session=session,
            )
            if result:
                results.append(result)

        return results
