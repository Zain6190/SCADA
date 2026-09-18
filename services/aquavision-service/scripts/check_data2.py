import sys
sys.path.insert(0, "/app")
from sqlalchemy import text
from infrastructure.db.engine import SessionLocal
db = SessionLocal()
rows = db.execute(text("""
    SELECT asset_id, COUNT(*) as cnt, 
           MIN(observed_at) as first_obs, MAX(observed_at) as last_obs,
           SUM(CASE WHEN water_level_ft IS NOT NULL OR inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL THEN 1 ELSE 0 END) as hydro,
           SUM(CASE WHEN precip_mm IS NOT NULL THEN 1 ELSE 0 END) as weather
    FROM aquavision.water_observations 
    GROUP BY asset_id ORDER BY asset_id
""")).mappings().all()
print(f"{'Asset':>6} {'Total':>7} {'Hydro':>7} {'Weather':>8} {'First':>12} {'Last':>12}")
print("-" * 60)
for r in rows:
    print(f"{r['asset_id']:6d} {r['cnt']:7d} {r['hydro']:7d} {r['weather']:8d} {str(r['first_obs'])[:10]:>12} {str(r['last_obs'])[:10]:>12}")
db.close()
