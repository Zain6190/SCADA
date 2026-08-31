"""
ml/features/weather_service.py
AquaVision - Open-Meteo weather forecast fetcher.

Free, no API key required. 10k calls/day.
Provides 16-day forecasts for water asset locations.

Usage:
    from ml.features.weather_service import WeatherService
    ws = WeatherService()
    forecast = ws.get_forecast(asset_id=1, lat=34.0, lon=73.0)
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("aquavision.ml.weather")

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"

# In-memory cache: (asset_id, date) -> forecast dict, TTL 6 hours
_cache: Dict[tuple, dict] = {}
_CACHE_TTL = 6 * 3600  # seconds


class WeatherService:
    """Fetch weather forecasts from Open-Meteo for water assets."""

    def __init__(self, session: Session):
        self.session = session

    def get_forecast(self, asset_id: int, lat: float, lon: float) -> Optional[Dict]:
        """Get 16-day weather forecast for an asset location.

        Returns dict with daily arrays:
            dates, precip_sum, temp_max, temp_min, humidity_mean, wind_speed
        """
        cache_key = (asset_id, date.today().isoformat())
        if cache_key in _cache:
            cached = _cache[cache_key]
            if time.time() - cached.get("_ts", 0) < _CACHE_TTL:
                return cached

        try:
            resp = requests.get(
                OPEN_METEO_FORECAST,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,wind_speed_10m_max",
                    "forecast_days": 16,
                    "timezone": "auto",
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            daily = data.get("daily", {})

            result = {
                "dates": daily.get("time", []),
                "precip_sum": daily.get("precipitation_sum", []),
                "temp_max": daily.get("temperature_2m_max", []),
                "temp_min": daily.get("temperature_2m_min", []),
                "humidity_mean": daily.get("relative_humidity_2m_mean", []),
                "wind_speed": daily.get("wind_speed_10m_max", []),
                "_ts": time.time(),
            }
            _cache[cache_key] = result
            return result

        except Exception as e:
            logger.warning(f"Open-Meteo forecast failed for asset {asset_id}: {e}")
            return None

    def get_forecasts_for_horizon(self, asset_id: int, lat: float, lon: float, horizon_days: int) -> Dict:
        """Get aggregated forecast for a specific horizon (7d, 14d, 16d).

        Returns dict with:
            precip_sum_mm: total precipitation over horizon
            temp_max_c: max temperature over horizon
            temp_min_c: min temperature over horizon
            humidity_mean_pct: mean humidity over horizon
            wind_speed_kmh: max wind speed over horizon
        """
        forecast = self.get_forecast(asset_id, lat, lon)
        if not forecast or not forecast["dates"]:
            return {}

        # Slice to horizon
        n = min(horizon_days, len(forecast["dates"]))
        precip = forecast["precip_sum"][:n]
        tmax = forecast["temp_max"][:n]
        tmin = forecast["temp_min"][:n]
        humidity = forecast["humidity_mean"][:n]
        wind = forecast["wind_speed"][:n]

        def safe_sum(vals):
            return round(sum(v for v in vals if v is not None), 2)

        def safe_max(vals):
            vals = [v for v in vals if v is not None]
            return round(max(vals), 2) if vals else None

        def safe_min(vals):
            vals = [v for v in vals if v is not None]
            return round(min(vals), 2) if vals else None

        def safe_mean(vals):
            vals = [v for v in vals if v is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        return {
            "precip_sum_mm": safe_sum(precip),
            "temp_max_c": safe_max(tmax),
            "temp_min_c": safe_min(tmin),
            "humidity_mean_pct": safe_mean(humidity),
            "wind_speed_kmh": safe_max(wind),
        }

    def store_forecast(self, asset_id: int, forecast_date: date, horizon_days: int, data: Dict) -> None:
        """Store forecast in DB (upsert)."""
        if not data:
            return

        self.session.execute(
            text("""
                INSERT INTO aquavision.weather_forecasts
                    (asset_id, forecast_date, horizon_days,
                     precip_sum_mm, temp_max_c, temp_min_c,
                     humidity_mean_pct, wind_speed_kmh, fetched_at)
                VALUES
                    (:asset_id, :forecast_date, :horizon_days,
                     :precip, :tmax, :tmin, :humidity, :wind, now())
                ON CONFLICT (asset_id, forecast_date, horizon_days)
                DO UPDATE SET
                    precip_sum_mm = EXCLUDED.precip_sum_mm,
                    temp_max_c = EXCLUDED.temp_max_c,
                    temp_min_c = EXCLUDED.temp_min_c,
                    humidity_mean_pct = EXCLUDED.humidity_mean_pct,
                    wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                    fetched_at = now()
            """),
            {
                "asset_id": asset_id,
                "forecast_date": forecast_date,
                "horizon_days": horizon_days,
                "precip": data.get("precip_sum_mm"),
                "tmax": data.get("temp_max_c"),
                "tmin": data.get("temp_min_c"),
                "humidity": data.get("humidity_mean_pct"),
                "wind": data.get("wind_speed_kmh"),
            },
        )
        self.session.commit()

    def get_stored_forecast(self, asset_id: int, forecast_date: date, horizon_days: int) -> Optional[Dict]:
        """Get stored forecast from DB."""
        row = self.session.execute(
            text("""
                SELECT precip_sum_mm, temp_max_c, temp_min_c,
                       humidity_mean_pct, wind_speed_kmh, fetched_at
                FROM aquavision.weather_forecasts
                WHERE asset_id = :asset_id
                AND forecast_date = :forecast_date
                AND horizon_days = :horizon_days
            """),
            {"asset_id": asset_id, "forecast_date": forecast_date, "horizon_days": horizon_days},
        ).mappings().first()

        if row:
            return dict(row)
        return None

    def refresh_all_assets(self) -> int:
        """Fetch forecasts for all active assets with coordinates.

        Returns number of assets updated.
        """
        assets = self.session.execute(
            text("""
                SELECT id, latitude, longitude
                FROM aquavision.water_assets
                WHERE is_active = true
                AND latitude IS NOT NULL
                AND longitude IS NOT NULL
                ORDER BY id
            """)
        ).mappings().all()

        today = date.today()
        count = 0
        for asset in assets:
            aid = asset["id"]
            lat = float(asset["latitude"])
            lon = float(asset["longitude"])

            for horizon in [7, 14, 16]:
                data = self.get_forecasts_for_horizon(aid, lat, lon, horizon)
                if data:
                    self.store_forecast(aid, today, horizon, data)
                    count += 1

            time.sleep(0.3)  # rate-limit courtesy

        logger.info(f"Refreshed forecasts for {len(assets)} assets ({count} forecast rows)")
        return count
