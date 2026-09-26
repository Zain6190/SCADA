import psycopg2

from _db_urls import neon_url

conn = psycopg2.connect(neon_url())
cur = conn.cursor()

cols = [
    "ADD COLUMN IF NOT EXISTS precip_mm DOUBLE PRECISION",
    "ADD COLUMN IF NOT EXISTS temp_max_c DOUBLE PRECISION",
    "ADD COLUMN IF NOT EXISTS temp_min_c DOUBLE PRECISION",
    "ADD COLUMN IF NOT EXISTS et0_mm DOUBLE PRECISION",
    "ADD COLUMN IF NOT EXISTS soil_moisture_m3 DOUBLE PRECISION",
]
for c in cols:
    cur.execute(f"ALTER TABLE aquavision.water_observations {c}")
    print(f"OK: {c}")

conn.commit()
cur.close()
conn.close()
print("All columns added to Neon")
