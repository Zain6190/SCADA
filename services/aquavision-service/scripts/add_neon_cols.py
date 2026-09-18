import psycopg2

NEON_URL = "postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

conn = psycopg2.connect(NEON_URL)
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
