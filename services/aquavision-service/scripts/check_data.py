from sqlalchemy import text
from infrastructure.db.engine import SessionLocal
db = SessionLocal()
rows = db.execute(text("""
    SELECT asset_id, COUNT(*) as cnt, 
           MIN(observed_at) as first_obs, MAX(observed_at) as last_obs
    FROM aquavision.water_observations 
    GROUP BY asset_id ORDER BY asset_id
""")).mappings().all()
for r in rows:
    aid = r["asset_id"]
    cnt = r["cnt"]
    first = r["first_obs"]
    last = r["last_obs"]
    print(f"Asset {aid:2d}: {cnt:5d} obs, {first} to {last}")
db.close()
