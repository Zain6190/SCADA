# ml/features/feature_engineering.py
# Feature engineering for flood prediction models.
# Builds ML training table from IRSA observations + FFD data.

import logging
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Tuple

import numpy as np
from sqlalchemy import select, desc, and_, func, or_, text
from sqlalchemy.orm import Session

from infrastructure.db.models import (
    WaterAsset, WaterObservation, WaterFFDObservation,
    WaterAssetThreshold, WaterWeatherForecast,
)

logger = logging.getLogger("aquavision.ml.features")

_OT_ORIGINS = {"SCENARIO", "OFFICIAL_REPLAY", "SYNTHETIC", "SYNTHETIC_HISTORICAL"}


def usable_for_training(data_origin: Optional[str], source_authority: Optional[str]) -> bool:
    """Soft OT replay and scenario rows never train the flood model.

    REAL observations and REANALYSIS (GloFAS) rows do: reanalysis is a
    labelled model product, not an observation, so sample weights keep it
    below REAL everywhere it is used.
    """
    if source_authority == "SOFT_OT":
        return False
    origin = (data_origin or "REAL").upper()
    if origin in _OT_ORIGINS:
        return False
    return origin in {"REAL", "REANALYSIS"}


def keep_training_row(data_origin: Optional[str], source_authority: Optional[str], real_only: bool) -> bool:
    """Always drop Soft OT. Other synthetic rows remain only when real_only is off."""
    if source_authority == "SOFT_OT":
        return False
    origin = (data_origin or "").upper()
    if origin in {"SCENARIO", "OFFICIAL_REPLAY"}:
        return False
    if real_only:
        return usable_for_training(data_origin, source_authority)
    return True


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
        self._threshold_cache: Dict[int, Optional[WaterAssetThreshold]] = {}
        self._ffd_status_cache: Dict[tuple, Optional[str]] = {}
        self._ffd_span: Optional[tuple] = None
        self._weather_cache: Dict[tuple, Optional[Dict]] = {}
        self._weather_span: Optional[tuple] = None
    
    def build_training_table(
        self,
        asset_id: int,
        start_date: datetime,
        end_date: datetime,
        forecast_horizon: int = 7,
        real_only: bool = False,
        target_field: str = "auto",
        source_priority: bool = False,
        return_dates: bool = False,
    ):
        """Build training table for a specific asset.

        Args:
            asset_id: Water asset ID
            start_date: Training data start
            end_date: Training data end
            forecast_horizon: Days ahead to predict (7, 14, or 30)
            real_only: If True, only use REAL observations (no synthetic)
            target_field: "auto" (inflow preferred), "level", "inflow", "outflow", "discharge"
            source_priority: If True, use best value per date (IRSA > FFD > Kaggle)
            return_dates: If True, also return (prediction_date, target_date) per row

        Returns:
            X: Feature matrix (n_samples, n_features)
            y: Target vector (n_samples,)
            feature_names: List of feature names
            weights: Sample weights (1.0 for REAL, 0.2 for SYNTHETIC)
            dates: Optional list of (prediction_date, target_date) when return_dates=True
        """
        # Get all observations for this asset
        observations = self._get_observations(
            asset_id, start_date, end_date, 
            real_only=real_only, source_priority=source_priority
        )
        
        if len(observations) < 12:
            logger.warning(f"Insufficient data for asset {asset_id}: {len(observations)} observations (need 12+)")
            empty = (np.array([]), np.array([]), [], np.array([]), [])
            return empty if return_dates else empty[:4]

        self.prefetch_asset_features(
            asset_id,
            start_date,
            end_date,
            {row.get("date") for row in observations if row.get("date")},
        )

        # Build feature matrix
        features_list = []
        targets = []
        weights = []
        dates = []
        feature_names = None
        
        # Adaptive min_history: need enough for lag features, but don't block data-poor assets
        # For 30 obs → min_history=10, for 1688 obs → min_history=30
        min_history = min(30, max(5, len(observations) // 3))
        
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
                # Sample weight: based on BOTH current AND target data quality
                current_real = row_obs.get("data_origin") == "REAL"
                target_real = target_obs.get("data_origin") == "REAL"
                if current_real and target_real:
                    w = 1.0    # both real — full weight
                elif current_real or target_real:
                    w = 0.5    # one real — medium weight
                else:
                    w = 0.1    # both synthetic — minimal weight
                weights.append(w)
                pred_at = row_obs.get("observed_at") or row_obs.get("date")
                tgt_at = target_obs.get("observed_at") or target_obs.get("date")
                if pred_at is not None and tgt_at is not None:
                    dates.append((pred_at, tgt_at))

        if not features_list:
            empty = (np.array([]), np.array([]), [], np.array([]), [])
            return empty if return_dates else empty[:4]

        X = np.array(features_list, dtype=np.float32)
        y = np.array(targets, dtype=np.float32)
        w = np.array(weights, dtype=np.float32)
        
        # Replace NaN with column median (not zero — zero corrupts features like level)
        for col in range(X.shape[1]):
            col_vals = X[:, col]
            nan_mask = np.isnan(col_vals)
            if nan_mask.any():
                median = np.nanmedian(col_vals)
                X[nan_mask, col] = median if not np.isnan(median) else 0.0
        
        # Randomly mask inflow for 15% of training samples (so model learns to handle missing inflow)
        inflow_cols = [i for i, name in enumerate(feature_names) if "inflow" in name]
        if inflow_cols:
            n_mask = int(len(X) * 0.15)
            mask_idx = np.random.choice(len(X), size=n_mask, replace=False)
            for row_idx in mask_idx:
                for c in inflow_cols:
                    X[row_idx, c] = 0.0
                # Also mask inflow lag/roll/roc features
                for fi, fname in enumerate(feature_names):
                    if "inflow_lag" in fname or "inflow_roll" in fname or "inflow_roc" in fname:
                        X[row_idx, fi] = 0.0
        
        real_count = int(np.sum(w == 1.0))
        synth_count = int(np.sum(w < 1.0))
        logger.info(f"Built training table: {X.shape[0]} samples ({real_count} real, {synth_count} synthetic), {X.shape[1]} features for asset {asset_id}")
        if return_dates:
            return X, y, feature_names, w, dates
        return X, y, feature_names, w
    
    def build_prediction_features(
        self,
        asset_id: int,
        as_of_date: datetime,
        real_only: bool = True,
        source_priority: bool = True,
    ) -> Tuple[Optional[np.ndarray], List[str]]:
        """Build feature vector for prediction (latest state).

        Defaults mirror the training policy (REAL observations only, best
        source per date) so serving features match the distribution the
        models were trained on. When the best-source view has masked most
        REAL rows with Soft-OT winners (fewer than 10 kept), it retries on
        the raw observation table so recently-reported REAL data (Kaggle,
        IRSA) is not lost.

        Returns:
            X: Feature vector (1, n_features) or None if insufficient data
            feature_names: List of feature names
        """
        observations = self._get_observations(
            asset_id,
            as_of_date - timedelta(days=60),
            as_of_date,
            real_only=real_only,
            source_priority=source_priority,
        )
        if len(observations) < 10 and source_priority:
            observations = self._get_observations(
                asset_id,
                as_of_date - timedelta(days=60),
                as_of_date,
                real_only=real_only,
                source_priority=False,
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
    
    @staticmethod
    def _as_date(value):
        return value.date() if hasattr(value, "date") else value

    def prefetch_asset_features(
        self,
        asset_id: int,
        start_date: datetime,
        end_date: datetime,
        dates,
    ) -> None:
        """Batch-load per-row feature lookups for one training build.

        build_training_table extracts features for thousands of samples and
        each sample used to issue its own threshold/FFD/weather SELECTs —
        roughly ten thousand round trips per horizon against a remote
        database, which dominated training time. Three range queries fill
        these caches instead; _get_threshold, _get_ffd_status and
        _get_weather_forecast read them and fall back to a per-call query
        only for dates outside the prefetched span.
        """
        span_start = self._as_date(start_date)
        span_end = self._as_date(end_date)

        self._get_threshold(asset_id)

        self._ffd_status_cache = {}
        day_floor = datetime.combine(span_start, time.min)
        day_ceil = datetime.combine(span_end + timedelta(days=1), time.min)
        ffd_rows = self.session.execute(
            select(
                WaterFFDObservation.observed_at,
                WaterFFDObservation.flood_status,
            )
            .where(
                WaterFFDObservation.asset_id == asset_id,
                WaterFFDObservation.observed_at >= day_floor,
                WaterFFDObservation.observed_at < day_ceil,
            )
            .order_by(WaterFFDObservation.observed_at)
        ).all()
        for observed_at, flood_status in ffd_rows:
            key = (asset_id, self._as_date(observed_at))
            if key not in self._ffd_status_cache:
                self._ffd_status_cache[key] = flood_status
        self._ffd_span = (span_start, span_end)

        self._weather_cache = {}
        weather_rows = self.session.execute(
            select(WaterWeatherForecast)
            .where(
                WaterWeatherForecast.asset_id == asset_id,
                WaterWeatherForecast.forecast_date >= span_start - timedelta(days=31),
                WaterWeatherForecast.forecast_date <= span_end,
            )
            .order_by(
                WaterWeatherForecast.horizon_days.asc(),
                WaterWeatherForecast.fetched_at.desc(),
            )
        ).scalars().all()
        for value in dates:
            day = self._as_date(value)
            picked = None
            for row in weather_rows:
                forecast_day = self._as_date(row.forecast_date)
                if forecast_day <= day <= forecast_day + timedelta(days=int(row.horizon_days)):
                    picked = {
                        "precip_sum_mm": row.precip_sum_mm,
                        "temp_max_c": row.temp_max_c,
                        "humidity_mean_pct": row.humidity_mean_pct,
                    }
                    break
            self._weather_cache[(asset_id, day)] = picked
        self._weather_span = (span_start, span_end)

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
            return [
                row for row in by_date.values()
                if keep_training_row(row.get("data_origin"), row.get("source"), real_only)
            ]
        
        # Original query (all sources merged)
        q = select(WaterObservation).where(
            WaterObservation.asset_id == asset_id,
            WaterObservation.observed_at >= start_date,
            WaterObservation.observed_at <= end_date,
        )
        if real_only:
            # data_origin is the canonical REAL/SYNTHETIC marker; filtering on a
            # single data_status value let other synthetic sources through -
            # historical_backfill writes SYNTHETIC_HISTORICAL, but the sensor
            # replay adapters write SIMULATED, and both must be excluded.
            # SOFT_OT / SCENARIO / OFFICIAL_REPLAY are never training rows.
            q = q.where(
                WaterObservation.data_origin.in_(("REAL", "REANALYSIS")),
                WaterObservation.data_status != "SYNTHETIC_HISTORICAL",
                or_(
                    WaterObservation.source_authority.is_(None),
                    WaterObservation.source_authority != "SOFT_OT",
                ),
            )
        
        rows = self.session.execute(q.order_by(WaterObservation.observed_at)).scalars().all()
        
        built = [
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
        return [
            row for row in built
            if keep_training_row(row["data_origin"], row["source"], real_only)
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

        # Weather forecast features (Open-Meteo)
        weather = self._get_weather_forecast(asset_id, current["date"])
        if weather:
            features["forecast_precip_7d"] = weather.get("precip_sum_mm") or 0.0
            features["forecast_temp_max"] = weather.get("temp_max_c") or 0.0
            features["forecast_humidity_mean"] = weather.get("humidity_mean_pct") or 0.0
        else:
            features["forecast_precip_7d"] = 0.0
            features["forecast_temp_max"] = 0.0
            features["forecast_humidity_mean"] = 0.0

        return features
    
    def _get_threshold(self, asset_id: int):
        """Get asset threshold configuration."""
        if asset_id in self._threshold_cache:
            return self._threshold_cache[asset_id]
        threshold = self.session.execute(
            select(WaterAssetThreshold).where(
                WaterAssetThreshold.asset_id == asset_id,
                WaterAssetThreshold.is_active == True,
            )
        ).scalar_one_or_none()
        self._threshold_cache[asset_id] = threshold
        return threshold
    
    def _get_ffd_status(self, asset_id: int, date) -> Optional[str]:
        """Get FFD flood status for asset on date."""
        if date is None:
            return None
        d = date.date() if hasattr(date, 'date') else date
        key = (asset_id, d)
        if key in self._ffd_status_cache:
            return self._ffd_status_cache[key]
        if self._ffd_span is not None and self._ffd_span[0] <= d <= self._ffd_span[1]:
            self._ffd_status_cache[key] = None
            return None
        obs = self.session.execute(
            select(WaterFFDObservation.flood_status).where(
                WaterFFDObservation.asset_id == asset_id,
                func.date(WaterFFDObservation.observed_at) == d,
            ).limit(1)
        ).scalar_one_or_none()
        self._ffd_status_cache[key] = obs
        return obs

    def _get_weather_forecast(self, asset_id: int, dt) -> Optional[Dict]:
        """Get weather forecast for asset on date (7-day horizon)."""
        if dt is None:
            return None
        d = dt.date() if hasattr(dt, 'date') else dt
        key = (asset_id, d)
        if key in self._weather_cache:
            return self._weather_cache[key]
        if self._weather_span is not None and self._weather_span[0] <= d <= self._weather_span[1]:
            self._weather_cache[key] = None
            return None
        row = self.session.execute(
            text("""
                SELECT precip_sum_mm, temp_max_c, humidity_mean_pct
                FROM aquavision.weather_forecasts
                WHERE asset_id = :asset_id
                AND forecast_date <= :dt
                AND forecast_date + (horizon_days || ' days')::interval >= :dt
                -- horizon 0 = daily actual (backfill) beats a covering
                -- multi-day aggregate; newest fetch wins within a horizon
                ORDER BY horizon_days ASC, fetched_at DESC
                LIMIT 1
            """),
            {"asset_id": asset_id, "dt": d},
        ).mappings().first()
        result = dict(row) if row else None
        self._weather_cache[key] = result
        return result
    
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
