"""Fetch weather forecasts for all assets and store in DB."""
import os, sys, time
sys.path.insert(0, '/app')

import httpx
from sqlalchemy import create_engine, text
from datetime import date

e = create_engine(os.getenv('DATABASE_URL'))
OPEN_METEO = 'https://api.open-meteo.com/v1/forecast'

with e.connect() as c:
    assets = c.execute(text(
        'SELECT id, canonical_name, latitude, longitude '
        'FROM aquavision.water_assets WHERE is_active=true AND latitude IS NOT NULL'
    )).fetchall()

today = date.today()
count = 0
client = httpx.Client(timeout=30)

for asset in assets:
    aid, name, lat, lon = asset[0], asset[1], float(asset[2]), float(asset[3])
    try:
        resp = client.get(OPEN_METEO, params={
            'latitude': lat, 'longitude': lon,
            'daily': 'precipitation_sum,temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,wind_speed_10m_max',
            'forecast_days': 16, 'timezone': 'auto',
        })
        resp.raise_for_status()
        data = resp.json()['daily']
        with e.begin() as conn:
            for horizon in [7, 14, 16]:
                n = min(horizon, len(data['time']))
                precip_vals = [v for v in data['precipitation_sum'][:n] if v is not None]
                tmax_vals = [v for v in data['temperature_2m_max'][:n] if v is not None]
                tmin_vals = [v for v in data['temperature_2m_min'][:n] if v is not None]
                hum_vals = [v for v in data['relative_humidity_2m_mean'][:n] if v is not None]
                wind_vals = [v for v in data['wind_speed_10m_max'][:n] if v is not None]

                conn.execute(text("""
                    INSERT INTO aquavision.weather_forecasts
                        (asset_id, forecast_date, horizon_days, precip_sum_mm, temp_max_c, temp_min_c, humidity_mean_pct, wind_speed_kmh, fetched_at)
                    VALUES (:aid, :fd, :hd, :p, :tmax, :tmin, :hum, :wind, now())
                    ON CONFLICT (asset_id, forecast_date, horizon_days) DO UPDATE SET
                        precip_sum_mm=EXCLUDED.precip_sum_mm, temp_max_c=EXCLUDED.temp_max_c,
                        temp_min_c=EXCLUDED.temp_min_c, humidity_mean_pct=EXCLUDED.humidity_mean_pct,
                        wind_speed_kmh=EXCLUDED.wind_speed_kmh, fetched_at=now()
                """), {
                    'aid': aid, 'fd': today, 'hd': horizon,
                    'p': round(sum(precip_vals), 2) if precip_vals else 0,
                    'tmax': round(max(tmax_vals), 2) if tmax_vals else None,
                    'tmin': round(min(tmin_vals), 2) if tmin_vals else None,
                    'hum': round(sum(hum_vals)/len(hum_vals), 2) if hum_vals else None,
                    'wind': round(max(wind_vals), 2) if wind_vals else None,
                })
                count += 1
        print(f'  {name}: OK')
    except Exception as ex:
        print(f'  {name}: FAILED - {ex}')
    time.sleep(0.3)

client.close()
print(f'Total: {count} forecast rows for {len(assets)} assets')
