# ml/models/anomaly_detector.py
# Isolation Forest anomaly detector for water observations.
# Detects unusual level/inflow/outflow patterns per asset.
# Unsupervised — no labeled anomaly data needed.
#
# Phase 2B: Added model_version and model_status to artifacts and output.

import logging
import os
from datetime import datetime, timedelta, timezone
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

_ARTIFACT_CACHE: Dict[str, Tuple[float, int, Dict]] = {}

_SERIES_CACHE: Dict[int, Tuple[tuple, Dict]] = {}


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

    @staticmethod
    def _severity_for(score: float) -> str:
        """Severity band for a decision_function score (negative = anomalous)."""
        if score < -0.3:
            return "HIGH"
        if score < -0.15:
            return "MODERATE"
        return "LOW"

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
                severity = self._severity_for(float(score))

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

    def _load_artifact(self, asset_id: int) -> Optional[Dict]:
        """Load the trained artifact, cached by file (mtime, size).

        Returns None when no artifact has been trained for the asset.
        """
        model_path = os.path.join(MODEL_DIR, f"anomaly_{asset_id}.joblib")
        if not os.path.exists(model_path):
            return None
        stat = os.stat(model_path)
        key = os.path.abspath(model_path)
        cached = _ARTIFACT_CACHE.get(key)
        if cached is not None and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return cached[2]
        artifact = joblib.load(model_path)
        _ARTIFACT_CACHE[key] = (stat.st_mtime, stat.st_size, artifact)
        return artifact

    def _load_series(
        self,
        session: Session,
        asset_ids: Optional[List[int]] = None,
    ) -> Dict[int, List[tuple]]:
        """Load observation series (column-level, no ORM entity hydration)."""
        from infrastructure.db.models import WaterObservation

        query = session.query(
            WaterObservation.asset_id,
            WaterObservation.observed_at,
            WaterObservation.water_level_ft,
            WaterObservation.inflow_cusecs,
            WaterObservation.outflow_cusecs,
        ).order_by(WaterObservation.observed_at.asc())
        if asset_ids is not None:
            query = query.filter(WaterObservation.asset_id.in_(asset_ids))

        series: Dict[int, List[tuple]] = {}
        for row in query.all():
            series.setdefault(row[0], []).append(row)
        return series

    def _score_series(
        self,
        artifact: Dict,
        rows: List[tuple],
        days: Optional[int],
    ) -> Optional[Dict]:
        """Score pre-loaded observation rows for one asset (real inference).

        Features are built over the FULL series (lags and rolling stats need
        history); points are then filtered to the window when days is given,
        so scores match predict() exactly. Returns None when there is too
        little data.
        """
        if len(rows) < 5:
            return None

        model = artifact["model"]
        scaler = artifact["scaler"]

        timestamps = np.array([r[1] for r in rows])
        levels = np.array([float(r[2] or 0) for r in rows])
        inflows = np.array([float(r[3] or 0) for r in rows])
        outflows = np.array([float(r[4] or 0) for r in rows])

        X, feature_names = self._build_features(levels, inflows, outflows, timestamps)
        X_scaled = scaler.transform(X)
        predictions = model.predict(X_scaled)
        scores = model.decision_function(X_scaled)

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
            if days is not None
            else None
        )
        points = []
        for i, row in enumerate(rows):
            ts = row[1]
            if ts is None:
                continue
            if cutoff is not None:
                ts_utc = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
                if ts_utc < cutoff:
                    continue

            is_anomaly = predictions[i] == -1
            anomaly_features: List[str] = []
            if is_anomaly:
                scaled_row = np.abs(X_scaled[i])
                top = np.argsort(scaled_row)[::-1][:3]
                anomaly_features = [feature_names[j] for j in top if scaled_row[j] > 1.0]

            score = scores[i]
            points.append({
                "observed_at": ts.isoformat(),
                "anomaly_score": round(float(score), 4),
                "is_anomaly": bool(is_anomaly),
                "severity": self._severity_for(float(score)),
                "anomaly_features": anomaly_features,
                "level_ft": float(row[2] or 0),
                "inflow_cusecs": float(row[3] or 0),
                "outflow_cusecs": float(row[4] or 0),
            })

        return {
            "artifact": {
                "model_version": artifact.get("model_version", MODEL_VERSION),
                "model_status": artifact.get("model_status", MODEL_STATUS),
                "trained_at": artifact.get("trained_at"),
                "training_samples": artifact.get("training_samples"),
                "contamination": artifact.get("contamination"),
            },
            "points": points,
            "anomaly_count": sum(1 for p in points if p["is_anomaly"]),
        }

    def _series_fingerprints(
        self,
        session: Session,
        asset_ids: List[int],
    ) -> Dict[int, tuple]:
        """Cheap per-asset data fingerprint (row count, latest timestamp)."""
        from sqlalchemy import func
        from infrastructure.db.models import WaterObservation

        if not asset_ids:
            return {}
        rows = (
            session.query(
                WaterObservation.asset_id,
                func.count(WaterObservation.id),
                func.max(WaterObservation.observed_at),
            )
            .filter(WaterObservation.asset_id.in_(asset_ids))
            .group_by(WaterObservation.asset_id)
            .all()
        )
        return {
            r[0]: (int(r[1]), r[2].isoformat() if r[2] else None)
            for r in rows
        }

    @staticmethod
    def _trim_history(history: Dict, keep_days: int = 370) -> Dict:
        """Keep only points that can appear in a legal window (max 365 days)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        points = []
        for p in history["points"]:
            ts = datetime.fromisoformat(p["observed_at"])
            ts_utc = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
            if ts_utc >= cutoff:
                points.append(p)
        return {
            "artifact": history["artifact"],
            "points": points,
            "anomaly_count": sum(1 for p in points if p["is_anomaly"]),
        }

    @staticmethod
    def _window_history(history: Dict, days: int) -> Dict:
        """Slice a cached full history to a trailing window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        points = []
        for p in history["points"]:
            ts = datetime.fromisoformat(p["observed_at"])
            ts_utc = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
            if ts_utc >= cutoff:
                points.append(p)
        return {
            "artifact": history["artifact"],
            "points": points,
            "anomaly_count": sum(1 for p in points if p["is_anomaly"]),
        }

    def score_history(
        self,
        asset_id: int,
        session: Session,
        days: int = 90,
    ) -> Optional[Dict]:
        """Score every observation for one asset over a trailing window.

        Returns None when no trained artifact exists or there is too little
        data to score.
        """
        return self.score_many(session, [asset_id], days=days).get(asset_id)

    def score_many(
        self,
        session: Session,
        asset_ids: List[int],
        days: int = 90,
    ) -> Dict[int, Optional[Dict]]:
        """Score many assets with one bulk series query and cached artifacts.

        Full scored series are cached per asset and invalidated by a cheap
        fingerprint (row count, latest observation, artifact file), so repeat
        calls only re-slice the window. Assets without a trained artifact (or
        that fail to score) map to None.
        """
        artifacts: Dict[int, Optional[Dict]] = {}
        for aid in asset_ids:
            try:
                artifacts[aid] = self._load_artifact(aid)
            except Exception as exc:
                logger.warning(f"Anomaly artifact load failed for asset {aid}: {exc}")
                artifacts[aid] = None

        wanted = [aid for aid in asset_ids if artifacts[aid] is not None]
        fingerprints = self._series_fingerprints(session, wanted) if wanted else {}

        scored: Dict[int, Optional[Dict]] = {}
        pending: Dict[int, Tuple[tuple, Dict]] = {}

        for aid in wanted:
            artifact = artifacts[aid]
            try:
                stat = os.stat(os.path.abspath(os.path.join(MODEL_DIR, f"anomaly_{aid}.joblib")))
                count, latest = fingerprints.get(aid, (0, None))
                fingerprint = (stat.st_mtime, stat.st_size, count, latest)
            except OSError as exc:
                logger.warning(f"Anomaly artifact stat failed for asset {aid}: {exc}")
                scored[aid] = None
                continue

            cached = _SERIES_CACHE.get(aid)
            if cached is not None and cached[0] == fingerprint:
                scored[aid] = self._window_history(cached[1], days)
            else:
                pending[aid] = (fingerprint, artifact)

        if pending:
            series = self._load_series(session, list(pending))
            for aid, (fingerprint, artifact) in pending.items():
                try:
                    full = self._score_series(artifact, series.get(aid, []), None)
                except Exception as exc:
                    logger.warning(f"Anomaly scoring failed for asset {aid}: {exc}")
                    full = None
                if full is None:
                    scored[aid] = None
                    continue
                trimmed = self._trim_history(full)
                _SERIES_CACHE[aid] = (fingerprint, trimmed)
                scored[aid] = self._window_history(trimmed, days)

        return {aid: scored.get(aid) for aid in asset_ids}

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
