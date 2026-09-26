"""
Backfill historical daily weather into aquavision.weather_forecasts.

Uses the Open-Meteo Archive API (free, no key, data back to 1940) and
writes one row per asset/day with horizon_days=0, which is exactly what
feature_engineering._get_weather_forecast matches on training dates
(forecast_date <= dt AND forecast_date + horizon_days >= dt).

The scheduled WeatherService.refresh_all_assets job stores forward-looking
horizon 7/14/16 rows; this script covers the historical window so TRAINING
rows finally see forecast_precip_7d / temp / humidity instead of zeros.

Usage:
    python -m scripts.backfill_weather [--start 2022-01-01] [--asset 2]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure.db.engine import SessionLocal

logger = logging.getLogger("aquavision.backfill_weather")

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = (
    "precipitation_sum,temperature_2m_max,temperature_2m_min,"
    "relative_humidity_2m_mean,wind_speed_10m_max"
)

# Archive has a ~2-5 day latency; don't request the last couple of days.
ARCHIVE_LAG_DAYS = 3


def rows_from_daily(daily: Dict, asset_id: int, horizon_days: int = 0) -> List[Dict]:
    """Map Open-Meteo daily arrays to weather_forecasts row dicts (pure)."""
    dates = daily.get("time") or []
    precip = daily.get("precipitation_sum") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    humidity = daily.get("relative_humidity_2m_mean") or []
    wind = daily.get("wind_speed_10m_max") or []

    rows = []
    for i, d in enumerate(dates):
        def at(arr):
            return arr[i] if i < len(arr) else None

        p, hi, lo, hu, wd = at(precip), at(tmax), at(tmin), at(humidity), at(wind)
        if p is None and hi is None and hu is None:
            continue  # nothing usable for this day
        rows.append(
            {
                "asset_id": asset_id,
                "forecast_date": d,
                "horizon_days": horizon_days,
                "precip_sum_mm": p,
                "temp_max_c": hi,
                "temp_min_c": lo,
                "humidity_mean_pct": hu,
                "wind_speed_kmh": wd,
            }
        )
    return rows


def fetch_archive(lat: float, lon: float, start: date, end: date,
                  client: requests.Session) -> Optional[Dict]:
    """Fetch daily archive data with light retry (rate limits / transient)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": DAILY_VARS,
        "timezone": "Asia/Karachi",
    }
    for attempt in range(3):
        try:
            r = client.get(ARCHIVE_URL, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            logger.warning("Archive HTTP %s: %s", r.status_code, r.text[:200])
            return None
        except requests.RequestException as exc:
            logger.warning("Archive fetch error (attempt %s): %s", attempt + 1, exc)
            time.sleep(3)
    return None


def _chunks(start: date, end: date, days: int = 365):
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def backfill_weather(start: Optional[date] = None, asset_id: Optional[int] = None) -> dict:
    """Backfill weather_forecasts (horizon_days=0) for all active assets."""
    db = SessionLocal()
    session = requests.Session()
    start = start or date(2022, 1, 1)
    end = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    if end < start:
        db.close()
        return {"inserted": 0, "reason": "empty_window"}

    assets = db.execute(
        text("""
            SELECT id, canonical_name, latitude, longitude
            FROM aquavision.water_assets
            WHERE is_active = true
              AND latitude IS NOT NULL AND longitude IS NOT NULL
              AND (:aid IS NULL OR id = :aid)
            ORDER BY id
        """),
        {"aid": asset_id},
    ).mappings().all()

    total = 0
    per_asset = {}
    for a in assets:
        aid = a["id"]
        inserted = 0
        for c_start, c_end in _chunks(start, end):
            data = fetch_archive(float(a["latitude"]), float(a["longitude"]),
                                 c_start, c_end, session)
            if not data or "daily" not in data:
                continue
            for row in rows_from_daily(data["daily"], aid, horizon_days=0):
                db.execute(
                    text("""
                        INSERT INTO aquavision.weather_forecasts
                            (asset_id, forecast_date, horizon_days,
                             precip_sum_mm, temp_max_c, temp_min_c,
                             humidity_mean_pct, wind_speed_kmh, fetched_at)
                        VALUES
                            (:asset_id, :forecast_date, :horizon_days,
                             :precip_sum_mm, :temp_max_c, :temp_min_c,
                             :humidity_mean_pct, :wind_speed_kmh, now())
                        ON CONFLICT (asset_id, forecast_date, horizon_days)
                        DO UPDATE SET
                            precip_sum_mm = EXCLUDED.precip_sum_mm,
                            temp_max_c = EXCLUDED.temp_max_c,
                            temp_min_c = EXCLUDED.temp_min_c,
                            humidity_mean_pct = EXCLUDED.humidity_mean_pct,
                            wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                            fetched_at = now()
                    """),
                    row,
                )
                inserted += 1
            db.commit()  # per-chunk durability
            time.sleep(0.25)  # rate-limit courtesy
        per_asset[aid] = inserted
        total += inserted
        logger.info("Backfilled %s: %s rows", a["canonical_name"], inserted)

    db.close()
    result = {"inserted": total, "assets": len(assets), "window": [str(start), str(end)]}
    logger.info("Weather backfill complete: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--asset", type=int, default=None)
    args = parser.parse_args()
    print(backfill_weather(start=date.fromisoformat(args.start), asset_id=args.asset))
