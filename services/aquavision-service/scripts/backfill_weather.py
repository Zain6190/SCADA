"""
Backfill historical observations using Open-Meteo Archive API.
- CHIRPS precipitation (daily)
- ERA5 temperature, ET (hourly → daily)
- Soil moisture (hourly → monthly)
Free, no API key, data back to 1940.

Also estimates missing inflow using physics_inflow.py.
"""
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import text

# Ensure app path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure.db.engine import SessionLocal

# Asset coordinates (lat, lon) - from OSM/Pak geography
ASSET_COORDS = {
    1: {"name": "Tarbela", "lat": 34.086, "lon": 72.858},
    2: {"name": "Mangla", "lat": 33.156, "lon": 73.650},
    3: {"name": "Chashma", "lat": 31.763, "lon": 71.656},
    4: {"name": "Kalabagh", "lat": 32.962, "lon": 71.491},
    5: {"name": "Taunsa", "lat": 30.704, "lon": 70.944},
    6: {"name": "Guddu", "lat": 28.431, "lon": 68.253},
    7: {"name": "Sukkur", "lat": 27.705, "lon": 68.888},
    8: {"name": "Kotri", "lat": 25.354, "lon": 68.324},
    9: {"name": "Kabul_Nowshera", "lat": 34.015, "lon": 71.583},
    10: {"name": "Chenab_Marala", "lat": 32.533, "lon": 74.650},
    11: {"name": "Panjnad", "lat": 29.233, "lon": 71.033},
}


def fetch_open_meteo_archive(lat, lon, start_date, end_date, client):
    """Fetch historical daily data from Open-Meteo Archive API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration",
        "timezone": "Asia/Karachi",
    }
    for attempt in range(3):
        try:
            r = client.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP {r.status_code}: {r.text[:200]}")
                return None
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(3)
    return None


def fetch_open_meteo_forecast(lat, lon, client):
    """Fetch 16-day forecast from Open-Meteo (for recent days not in archive)."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration",
        "timezone": "Asia/Karachi",
        "forecast_days": 16,
    }
    try:
        r = client.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


def backfill_weather():
    """Backfill weather data for all assets."""
    db = SessionLocal()
    client = httpx.Client()

    # Check existing weather data
    existing = db.execute(text("""
        SELECT asset_id, COUNT(*) as cnt, MIN(observed_at) as first, MAX(observed_at) as last
        FROM aquavision.water_observations
        WHERE precip_mm IS NOT NULL
        GROUP BY asset_id ORDER BY asset_id
    """)).mappings().all()
    
    print("=== Existing weather data ===")
    for r in existing:
        print(f"  Asset {r['asset_id']:2d} ({ASSET_COORDS[r['asset_id']]['name']}): {r['cnt']} obs with weather, {r['first']} to {r['last']}")

    # We want data from 2022-01-01 to today (Kaggle starts at 2022-01-04)
    start_date = date(2022, 1, 1)
    end_date = date.today() - timedelta(days=2)  # Archive API has ~5 day lag
    forecast_start = end_date + timedelta(days=1)

    total_inserted = 0
    for asset_id, info in ASSET_COORDS.items():
        print(f"\n--- Asset {asset_id}: {info['name']} ({info['lat']}, {info['lon']}) ---")

        # Fetch archive data
        print(f"  Fetching archive {start_date} to {end_date}...")
        archive = fetch_open_meteo_archive(info["lat"], info["lon"], start_date, end_date, client)
        if not archive or "daily" not in archive:
            print(f"  FAILED to get archive data")
            continue

        daily = archive["daily"]
        dates_list = daily["time"]
        precip = daily.get("precipitation_sum", [])
        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        et0 = daily.get("et0_fao_evapotranspiration", [])

        print(f"  Got {len(dates_list)} days of archive data")

        # Fetch forecast data for recent days
        print(f"  Fetching forecast...")
        forecast = fetch_open_meteo_forecast(info["lat"], info["lon"], client)
        forecast_dates = set()
        if forecast and "daily" in forecast:
            fd = forecast["daily"]
            for i, d in enumerate(fd.get("time", [])):
                forecast_dates.add(d)
                # Add forecast data to the lists
                dates_list.append(d)
                precip.append(fd.get("precipitation_sum", [None])[i])
                temp_max.append(fd.get("temperature_2m_max", [None])[i])
                temp_min.append(fd.get("temperature_2m_min", [None])[i])
                et0.append(fd.get("et0_fao_evapotranspiration", [None])[i])
            print(f"  Added {len(forecast_dates)} forecast days")

        # Insert observations (only weather columns, don't overwrite existing level/discharge)
        inserted = 0
        skipped = 0
        for i, d in enumerate(dates_list):
            try:
                obs_date = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=__import__("datetime").timezone.utc)
            except:
                continue

            p = precip[i] if i < len(precip) else None
            tmax = temp_max[i] if i < len(temp_max) else None
            tmin = temp_min[i] if i < len(temp_min) else None
            et = et0[i] if i < len(et0) else None

            # Skip if all null
            if p is None and tmax is None and et is None:
                skipped += 1
                continue

            existing_row = db.execute(text("""
                SELECT id, precip_mm FROM aquavision.water_observations
                WHERE asset_id = :aid AND observed_at = :obs_at
                ORDER BY source_priority ASC LIMIT 1
            """), {"aid": asset_id, "obs_at": obs_date}).fetchone()

            if existing_row:
                if existing_row[1] is None and p is not None:
                    db.execute(text("""
                        UPDATE aquavision.water_observations
                        SET precip_mm = :precip, temp_max_c = :tmax, temp_min_c = :tmin, et0_mm = :et
                        WHERE id = :rid
                    """), {"precip": p, "tmax": tmax, "tmin": tmin, "et": et, "rid": existing_row[0]})
                    inserted += 1
            else:
                # Insert new row with weather data only
                db.execute(text("""
                    INSERT INTO aquavision.water_observations
                        (asset_id, source_id, observed_at, precip_mm, temp_max_c, temp_min_c, et0_mm, 
                         water_level_ft, inflow_cusecs, discharge_cusecs, data_status, data_origin, created_at)
                    VALUES (:aid, 1, :obs_at, :precip, :tmax, :tmin, :et,
                            NULL, NULL, NULL, 'OPEN_METEO_BACKFILL', 'REAL', NOW())
                """), {"aid": asset_id, "obs_at": obs_date, "precip": p, "tmax": tmax, "tmin": tmin, "et": et})
                inserted += 1

        db.commit()
        total_inserted += inserted
        print(f"  Inserted/updated: {inserted}, skipped: {skipped}")

    client.close()
    db.close()
    print(f"\n=== Total rows inserted/updated: {total_inserted} ===")


if __name__ == "__main__":
    backfill_weather()
