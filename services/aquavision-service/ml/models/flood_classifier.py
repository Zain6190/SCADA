"""
Flood Classification Model

Predicts flood probability (YES/NO) for 7-day horizon.
More operationally useful than regression — operators need "flood or not".

Training data:
  - Features: same as regression (lags, rolling stats, seasonal)
  - Label: flood_status in ['HIGH', 'VERY_HIGH', 'EXCEPTIONALLY_HIGH'] = 1 (FLOOD)
  - Label: flood_status in ['NORMAL', 'LOW', 'MODERATE'] = 0 (NO FLOOD)

Output:
  - flood_probability: 0.0-1.0
  - flood_severity: NONE / LOW / MODERATE / HIGH / EXTREME
  - confidence: HIGH / MEDIUM / LOW
  - recommendation: string
"""

from __future__ import annotations

import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report,
)
from sklearn.model_selection import TimeSeriesSplit

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent.parent / "data" / "models"


class FloodClassifier:
    """Binary classifier: flood / no-flood for 7-day horizon."""

    def __init__(self, asset_id: int, asset_name: str = ""):
        self.asset_id = asset_id
        self.asset_name = asset_name
        self.model: Optional[GradientBoostingClassifier] = None
        self.feature_names: list[str] = []
        self.threshold: float = 0.5
        self.metrics: dict = {}

    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build classification features from observation data."""
        features = pd.DataFrame(index=df.index)

        # Target variable: inflow
        target_col = "inflow_cusecs"
        if target_col not in df.columns:
            return features

        # Lags
        for lag in [1, 2, 3, 5, 7, 14, 21]:
            features[f"inflow_lag_{lag}"] = df[target_col].shift(lag)

        # Rolling statistics
        for window in [3, 7, 14, 21]:
            features[f"inflow_roll_mean_{window}"] = df[target_col].rolling(window).mean()
            features[f"inflow_roll_std_{window}"] = df[target_col].rolling(window).std()
            features[f"inflow_roll_max_{window}"] = df[target_col].rolling(window).max()
            features[f"inflow_roll_min_{window}"] = df[target_col].rolling(window).min()

        # Rate of change
        features["inflow_diff_1d"] = df[target_col].diff(1)
        features["inflow_diff_3d"] = df[target_col].diff(3)
        features["inflow_diff_7d"] = df[target_col].diff(7)

        # Percentage change
        features["inflow_pct_change_1d"] = df[target_col].pct_change(1)
        features["inflow_pct_change_7d"] = df[target_col].pct_change(7)

        # Seasonal features
        if "observed_at" in df.columns:
            dt = pd.to_datetime(df["observed_at"])
            features["month"] = dt.dt.month
            features["day_of_year"] = dt.dt.dayofyear
            features["is_monsoon"] = dt.dt.month.isin([6, 7, 8, 9]).astype(int)
            features["is_post_monsoon"] = dt.dt.month.isin([10, 11]).astype(int)
            features["is_winter"] = dt.dt.month.isin([12, 1, 2]).astype(int)
            features["is_pre_monsoon"] = dt.dt.month.isin([3, 4, 5]).astype(int)

        # Cross features
        features["inflow_x_month"] = features.get("inflow_lag_1", df[target_col]) * features.get("month", 1)

        return features

    def build_labels(self, df: pd.DataFrame, horizon: int = 7) -> pd.Series:
        """Build binary flood labels.

        Label = 1 if flood_status in future is HIGH/VERY_HIGH/EXCEPTIONALLY_HIGH
        Label = 0 otherwise.
        """
        target_col = "inflow_cusecs"
        
        # Use flood_status if available, otherwise use flow thresholds
        if "flood_status" in df.columns:
            future_status = df["flood_status"].shift(-horizon)
            flood_statuses = ["HIGH", "VERY_HIGH", "EXCEPTIONALLY_HIGH"]
            labels = future_status.isin(flood_statuses).astype(int)
        else:
            # Fallback: use flow percentile thresholds
            future_flow = df[target_col].shift(-horizon)
            # Flood if future flow is above 90th percentile
            threshold = df[target_col].quantile(0.90)
            labels = (future_flow > threshold).astype(int)

        return labels

    def train(
        self,
        df: pd.DataFrame,
        horizon: int = 7,
        test_ratio: float = 0.2,
    ) -> dict:
        """Train the flood classifier.

        Returns metrics dict.
        """
        logger.info(f"Training flood classifier for {self.asset_name} (horizon={horizon}d)")

        # Build features and labels
        features = self.build_features(df)
        labels = self.build_labels(df, horizon)

        # Align and drop NaN
        valid_mask = features.notna().all(axis=1) & labels.notna()
        features = features[valid_mask]
        labels = labels[valid_mask]

        if len(features) < 100:
            return {"error": f"Insufficient data: {len(features)} samples (need 100+)"}

        self.feature_names = list(features.columns)

        # Chronological split
        split_idx = int(len(features) * (1 - test_ratio))
        X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
        y_train, y_test = labels.iloc[:split_idx], labels.iloc[split_idx:]

        # Handle class imbalance
        n_flood = y_train.sum()
        n_total = len(y_train)
        scale_pos_weight = (n_total - n_flood) / max(n_flood, 1)

        # Train model
        self.model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            min_samples_leaf=10,
            random_state=42,
        )
        self.model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test)
        y_prob = self.model.predict_proba(X_test)[:, 1]

        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        try:
            auc = roc_auc_score(y_test, y_prob)
        except ValueError:
            auc = 0.5

        cm = confusion_matrix(y_test, y_pred)
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)

        # Feature importance
        importances = dict(zip(self.feature_names, self.model.feature_importances_))
        top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]

        self.metrics = {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "auc": round(auc, 4),
            "true_positives": int(tp),
            "false_positives": int(fp),
            "true_negatives": int(tn),
            "false_negatives": int(fn),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "flood_ratio_train": round(float(y_train.mean()), 4),
            "flood_ratio_test": round(float(y_test.mean()), 4),
            "top_features": top_features,
        }

        logger.info(
            f"Classifier trained: accuracy={accuracy:.3f}, "
            f"precision={precision:.3f}, recall={recall:.3f}, "
            f"f1={f1:.3f}, auc={auc:.3f}"
        )

        return self.metrics

    def predict(self, df: pd.DataFrame) -> dict:
        """Predict flood probability for latest observation."""
        if self.model is None:
            return {"error": "Model not trained"}

        features = self.build_features(df)
        last_row = features.iloc[[-1]]

        if last_row.isna().any().any():
            return {"error": "Insufficient data for prediction"}

        prob = float(self.model.predict_proba(last_row)[0][1])
        pred = int(self.model.predict(last_row)[0])

        # Determine severity
        if prob < 0.2:
            severity = "NONE"
            recommendation = "Normal operations"
        elif prob < 0.4:
            severity = "LOW"
            recommendation = "Monitor conditions"
        elif prob < 0.6:
            severity = "MODERATE"
            recommendation = "Alert downstream operators"
        elif prob < 0.8:
            severity = "HIGH"
            recommendation = "Prepare flood response teams"
        else:
            severity = "EXTREME"
            recommendation = "Activate emergency protocols"

        # Confidence based on probability distance from 0.5
        confidence_score = abs(prob - 0.5) * 2
        if confidence_score > 0.6:
            confidence = "HIGH"
        elif confidence_score > 0.3:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return {
            "flood_probability": round(prob, 4),
            "flood_predicted": bool(pred),
            "flood_severity": severity,
            "confidence": confidence,
            "recommendation": recommendation,
        }

    def save(self, path: Optional[Path] = None):
        """Save model to disk."""
        if path is None:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            path = MODEL_DIR / f"flood_classifier_asset_{self.asset_id}.pkl"

        data = {
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "model": self.model,
            "feature_names": self.feature_names,
            "threshold": self.threshold,
            "metrics": self.metrics,
            "saved_at": datetime.utcnow().isoformat(),
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        logger.info(f"Classifier saved to {path}")

    @classmethod
    def load(cls, asset_id: int, path: Optional[Path] = None) -> "FloodClassifier":
        """Load model from disk."""
        if path is None:
            path = MODEL_DIR / f"flood_classifier_asset_{asset_id}.pkl"

        with open(path, "rb") as f:
            data = pickle.load(f)

        clf = cls(asset_id=data["asset_id"], asset_name=data["asset_name"])
        clf.model = data["model"]
        clf.feature_names = data["feature_names"]
        clf.threshold = data["threshold"]
        clf.metrics = data["metrics"]
        return clf


def train_all_classifiers(horizon: int = 7) -> list[dict]:
    """Train flood classifiers for all assets with sufficient data."""
    from sqlalchemy import text
    from infrastructure.db.engine import engine as sa_engine

    results = []

    with sa_engine.connect() as conn:
        assets = conn.execute(
            text("""
                SELECT id, canonical_name 
                FROM aquavision.water_assets 
                WHERE id IN (
                    SELECT DISTINCT asset_id 
                    FROM aquavision.water_observations 
                    WHERE inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL
                    GROUP BY asset_id 
                    HAVING COUNT(*) > 200
                )
                ORDER BY id
            """)
        ).mappings().all()

    for asset in assets:
        asset_id = asset["id"]
        asset_name = asset["canonical_name"]

        logger.info(f"Training classifier for {asset_name}...")

        # Load observations
        with sa_engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT observed_at, 
                           COALESCE(inflow_cusecs, discharge_cusecs) as inflow_cusecs,
                           outflow_cusecs,
                           water_level_ft, discharge_cusecs
                    FROM aquavision.water_observations
                    WHERE asset_id = :asset_id 
                    AND (inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL)
                    ORDER BY observed_at
                """),
                {"asset_id": asset_id},
            ).mappings().all()

        if len(rows) < 200:
            results.append({"asset": asset_name, "error": "insufficient data"})
            continue

        df = pd.DataFrame(rows)
        # Convert Decimal/object columns to float
        from decimal import Decimal
        for col in df.columns:
            if df[col].dtype == object:
                try:
                    df[col] = df[col].apply(lambda x: float(x) if isinstance(x, (Decimal, int)) else x)
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                except Exception:
                    pass

        clf = FloodClassifier(asset_id, asset_name)
        metrics = clf.train(df, horizon=horizon)

        if "error" not in metrics:
            clf.save()
            results.append({"asset": asset_name, **metrics})
        else:
            results.append({"asset": asset_name, **metrics})

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = train_all_classifiers()
    for r in results:
        print(f"\n{r.get('asset', '?')}:")
        if "error" in r:
            print(f"  Error: {r['error']}")
        else:
            print(f"  Accuracy: {r.get('accuracy', 'N/A')}")
            print(f"  Precision: {r.get('precision', 'N/A')}")
            print(f"  Recall: {r.get('recall', 'N/A')}")
            print(f"  F1: {r.get('f1', 'N/A')}")
            print(f"  AUC: {r.get('auc', 'N/A')}")
