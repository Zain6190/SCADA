# ml/features/feature_engineering.py
# Feature engineering for flood prediction models.
# Builds ML training table from IRSA observations + FFD data.

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import numpy as np
from sqlalchemy import select, desc, and_, func, text
from sqlalchemy.orm import Session

from infrastructure.db.models import (
    WaterAsset, WaterObservation, WaterFFDObservation,
    WaterAssetThreshold,
)

logger = logging.getLogger("aquavision.ml.features")


class FloodFeatureBuilder:
    """Build ML features from IRSA + FFD observations.
    
    Features per asset per day:
    - Lag features (t-1, t-3, t-7, t-30)
    - Rolling statistics (7d, 30d mean/std)
    - Rate of change (1d, 3d, 7d)
    - Seasonal encoding (sin/cos of day-of-year)
    - Threshold proximity (how close to warning/danger)
    - FFD status encoding
    - Upstream features (if available)
    """
    
    LAG_DAYS = [1, 3, 7, 14, 30]
    ROLLING_WINDOWS = [7, 14, 30]
    
    def __init__(self, session: Session):
        self.session = session
    
    def build_training_table(
        self,
        asset_id: int,
        start_date: datetime,
        end_date: datetime,
        forecast_horizon: int = 7,
        real_only: bool = False,
        target_field: str = "auto",
        source_priority: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray]:
        """Build training table for a specific asset.
        
        Args:
            asset_id: Water asset ID
            start_date: Training data start
            end_date: Training data end
            forecast_horizon: Days ahead to predict (7, 14, or 30)
            real_only: If True, only use REAL observations (no synthetic)
            target_field: "auto" (inflow preferred), "level", "inflow", "outflow", "discharge"
            source_priority: If True, use best value per date (IRSA > FFD > Kaggle)
        
        Returns:
            X: Feature matrix (n_samples, n_features)
            y: Target vector (n_samples,)
            feature_names: List of feature names
            weights: Sample weights (1.0 for REAL, 0.2 for SYNTHETIC)
        """
        # Get all observations for this asset
        observations = self._get_observations(
            asset_id, start_date, end_date, 
            real_only=real_only, source_priority=source_priority
        )
        
        if len(observations) < 20:
            logger.warning(f"Insufficient data for asset {asset_id}: {len(observations)} observations")
            return np.array([]), np.array([]), [], np.array([])
        
        # Build feature matrix
        features_list = []
        targets = []
        weights = []
        feature_names = None
        
        min_history = min(10, len(observations) - 1)  # Need at least 10 for lag features
        
        for i in range(min_history, len(observations) - forecast_horizon):
            row_obs = observations[i]
            hist_obs = observations[max(0, i-30):i+1]
            
            features = self._extract_features(row_obs, hist_obs, asset_id)
            
            if feature_names is None:
                feature_names = list(features.keys())
            
            # Target: value at t+horizon
            target_obs = observations[i + forecast_horizon]
            target = self._get_target_value(target_obs, target_field)
            
            if target is not None and not np.isnan(target):
                features_list.append([features[k] for k in feature_names])
                targets.append(target)
                # Sample weight: REAL=1.0, SYNTHETIC=0.2
                w = 1.0 if row_obs.get("data_origin") == "REAL" else 0.2
                weights.append(w)
        
        if not features_list:
            return np.array([]), np.array([]), [], np.array([])
        
        X = np.array(features_list, dtype=np.float32)
        y = np.array(targets, dtype=np.float32)
        w = np.array(weights, dtype=np.float32)
        
        # Replace NaN with 0 for training
        X = np.nan_to_num(X, nan=0.0)
        
        real_count = int(np.sum(w == 1.0))
        synth_count = int(np.sum(w < 1.0))
        logger.info(f"Built training table: {X.shape[0]} samples ({real_count} real, {synth_count} synthetic), {X.shape[1]} features for asset {asset_id}")
        return X, y, feature_names, w
    
    def build_prediction_features(
        self,
        asset_id: int,
        as_of_date: datetime,
    ) -> Tuple[Optional[np.ndarray], List[str]]:
        """Build feature vector for prediction (latest state).
        
        Returns:
            X: Feature vector (1, n_features) or None if insufficient data
            feature_names: List of feature names
        """
        observations = self._get_observations(
            asset_id,
            as_of_date - timedelta(days=60),
            as_of_date,
        )
        
        if len(observations) < 10:
            return None, []
        
        row_obs = observations[-1]
        hist_obs = observations
        
        features = self._extract_features(row_obs, hist_obs, asset_id)
        feature_names = list(features.keys())
        X = np.array([[features[k] for k in feature_names]], dtype=np.float32)
        X = np.nan_to_num(X, nan=0.0)
        
        return X, feature_names
    
    def _get_observations(
        self,
        asset_id: int,
        start_date: datetime,
        end_date: datetime,
        real_only: bool = False,
        source_priority: bool = False,
    ) -> List[Dict]:
        """Get observations as list of dicts.
        
        Args:
            asset_id: Asset ID
            start_date: Start date
            end_date: End date
            real_only: If True, exclude synthetic observations
            source_priority: If True, use best value per date (IRSA > FFD > Kaggle)
        """
        if source_priority:
            # Use the v_best_observations view for source-aware queries
            from sqlalchemy import text
            q = text("""
                SELECT asset_id, observed_at, parameter, value, source, priority, data_origin
                FROM aquavision.v_best_observations
                WHERE asset_id = :asset_id
                AND observed_at >= :start_date
                AND observed_at <= :end_date
                ORDER BY observed_at, parameter
            """)
            rows = self.session.execute(q, {
                "asset_id": asset_id,
                "start_date": start_date,
                "end_date": end_date,
            }).fetchall()
            
            # Group by date
            by_date = {}
            for row in rows:
                dt = row.observed_at
                if dt not in by_date:
                    by_date[dt] = {
                        "date": dt,
                        "level": None, "inflow": None, "outflow": None, 
                        "discharge": None, "data_origin": "REAL", "source": None,
                    }
                if row.parameter == "level":
                    by_date[dt]["level"] = float(row.value)
                elif row.parameter == "inflow":
                    by_date[dt]["inflow"] = float(row.value)
                elif row.parameter == "outflow":
                    by_date[dt]["outflow"] = float(row.value)
                elif row.parameter == "discharge":
                    by_date[dt]["discharge"] = float(row.value)
                by_date[dt]["source"] = row.source
                by_date[dt]["data_origin"] = row.data_origin or "REAL"
            
            return list(by_date.values())
        
        # Original query (all sources merged)
        q = select(WaterObservation).where(
            WaterObservation.asset_id == asset_id,
            WaterObservation.observed_at >= start_date,
            WaterObservation.observed_at <= end_date,
        )
        if real_only:
            q = q.where(WaterObservation.data_status != "SYNTHETIC_HISTORICAL")
        
        rows = self.session.execute(q.order_by(WaterObservation.observed_at)).scalars().all()
        
        return [
            {
                "date": r.observed_at,
                "level": float(r.water_level_ft) if r.water_level_ft else None,
                "inflow": float(r.inflow_cusecs) if r.inflow_cusecs else None,
                "outflow": float(r.outflow_cusecs) if r.outflow_cusecs else None,
                "discharge": float(r.discharge_cusecs) if r.discharge_cusecs else None,
                "data_origin": getattr(r, "data_origin", "REAL"),
                "source": getattr(r, "source_authority", "UNKNOWN"),
            }
            for r in rows
        ]
    
    def _extract_features(
        self,
        current: Dict,
        history: List[Dict],
        asset_id: int,
    ) -> Dict[str, float]:
        """Extract all features for a single timestep."""
        features = {}
        
        # Current values
        features["level"] = current["level"] or 0.0
        features["inflow"] = current["inflow"] or 0.0
        features["outflow"] = current["outflow"] or 0.0
        features["discharge"] = current["discharge"] or 0.0
        
        # Lag features
        levels = [h["level"] for h in history if h["level"] is not None]
        inflows = [h["inflow"] for h in history if h["inflow"] is not None]
        outflows = [h["outflow"] for h in history if h["outflow"] is not None]
        
        for lag in self.LAG_DAYS:
            if len(levels) > lag:
                features[f"level_lag_{lag}d"] = levels[-lag-1]
            else:
                features[f"level_lag_{lag}d"] = 0.0
            
            if len(inflows) > lag:
                features[f"inflow_lag_{lag}d"] = inflows[-lag-1]
            else:
                features[f"inflow_lag_{lag}d"] = 0.0
            
            if len(outflows) > lag:
                features[f"outflow_lag_{lag}d"] = outflows[-lag-1]
            else:
                features[f"outflow_lag_{lag}d"] = 0.0
        
        # Rolling statistics
        for window in self.ROLLING_WINDOWS:
            if len(levels) >= window:
                recent = levels[-window:]
                features[f"level_roll_{window}d_mean"] = np.mean(recent)
                features[f"level_roll_{window}d_std"] = np.std(recent) if len(recent) > 1 else 0.0
            else:
                features[f"level_roll_{window}d_mean"] = 0.0
                features[f"level_roll_{window}d_std"] = 0.0
            
            if len(inflows) >= window:
                recent = inflows[-window:]
                features[f"inflow_roll_{window}d_mean"] = np.mean(recent)
                features[f"inflow_roll_{window}d_std"] = np.std(recent) if len(recent) > 1 else 0.0
            else:
                features[f"inflow_roll_{window}d_mean"] = 0.0
                features[f"inflow_roll_{window}d_std"] = 0.0
        
        # Rate of change
        if len(levels) >= 2:
            features["level_roc_1d"] = levels[-1] - levels[-2]
        else:
            features["level_roc_1d"] = 0.0
        
        if len(levels) >= 4:
            features["level_roc_3d"] = levels[-1] - levels[-4]
        else:
            features["level_roc_3d"] = 0.0
        
        if len(levels) >= 8:
            features["level_roc_7d"] = levels[-1] - levels[-8]
        else:
            features["level_roc_7d"] = 0.0
        
        if len(inflows) >= 2:
            features["inflow_roc_1d"] = inflows[-1] - inflows[-2]
        else:
            features["inflow_roc_1d"] = 0.0
        
        # Seasonal encoding
        if current["date"]:
            day_of_year = current["date"].timetuple().tm_yday
            features["day_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
            features["day_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
            features["month"] = current["date"].month
            features["is_monsoon"] = 1.0 if current["date"].month in [6, 7, 8, 9] else 0.0
        else:
            features["day_sin"] = 0.0
            features["day_cos"] = 0.0
            features["month"] = 0.0
            features["is_monsoon"] = 0.0
        
        # Threshold proximity
        threshold = self._get_threshold(asset_id)
        if threshold:
            if threshold.warning_level_ft and features["level"] > 0:
                features["pct_of_warning"] = features["level"] / float(threshold.warning_level_ft)
            else:
                features["pct_of_warning"] = 0.0
            
            if threshold.danger_level_ft and features["level"] > 0:
                features["pct_of_danger"] = features["level"] / float(threshold.danger_level_ft)
            else:
                features["pct_of_danger"] = 0.0
        else:
            features["pct_of_warning"] = 0.0
            features["pct_of_danger"] = 0.0
        
        # Inflow/outflow ratio
        if features["outflow"] > 0:
            features["inflow_outflow_ratio"] = features["inflow"] / features["outflow"]
        else:
            features["inflow_outflow_ratio"] = 0.0
        
        # FFD status encoding
        ffd_status = self._get_ffd_status(asset_id, current["date"])
        features["ffd_below_low"] = 1.0 if ffd_status == "BELOW_LOW" else 0.0
        features["ffd_low"] = 1.0 if ffd_status == "LOW" else 0.0
        features["ffd_medium"] = 1.0 if ffd_status == "MEDIUM" else 0.0
        features["ffd_high"] = 1.0 if ffd_status in ("HIGH", "VERY_HIGH", "EXCEPTIONALLY_HIGH") else 0.0
        
        return features
    
    def _get_threshold(self, asset_id: int):
        """Get asset threshold configuration."""
        return self.session.execute(
            select(WaterAssetThreshold).where(
                WaterAssetThreshold.asset_id == asset_id,
                WaterAssetThreshold.is_active == True,
            )
        ).scalar_one_or_none()
    
    def _get_ffd_status(self, asset_id: int, date: datetime) -> Optional[str]:
        """Get FFD flood status for asset on date."""
        if date is None:
            return None
        obs = self.session.execute(
            select(WaterFFDObservation.flood_status).where(
                WaterFFDObservation.asset_id == asset_id,
                WaterFFDObservation.observed_at == date.date() if hasattr(date, 'date') else date,
            ).limit(1)
        ).scalar_one_or_none()
        return obs
    
    def _get_target_value(self, obs: Dict, target_field: str = "auto") -> Optional[float]:
        """Get target value for prediction.
        
        "auto": inflow if available (more variance), else level, else discharge
        "level": water_level_ft
        "inflow": inflow_cusecs  
        "outflow": outflow_cusecs
        "discharge": discharge_cusecs
        """
        if target_field == "level":
            return obs["level"]
        elif target_field == "inflow":
            return obs["inflow"]
        elif target_field == "outflow":
            return obs["outflow"]
        elif target_field == "discharge":
            return obs["discharge"]
        else:  # auto — prefer inflow (more variance, better for ML)
            if obs["inflow"] is not None:
                return obs["inflow"]
            if obs["level"] is not None:
                return obs["level"]
            if obs["outflow"] is not None:
                return obs["outflow"]
            if obs["discharge"] is not None:
                return obs["discharge"]
            return None
