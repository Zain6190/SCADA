"""
Sync weather data + physics observations from local DB to Neon DB.
"""
import psycopg2
import psycopg2.extras

LOCAL_URL = "postgresql://postgres:1234@172.19.0.2:5432/ibcp_scada"
NEON_URL = "postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

def sync():
    local = psycopg2.connect(LOCAL_URL)
    neon = psycopg2.connect(NEON_URL)
    
    lcur = local.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ncur = neon.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # 1. Sync weather data (rows with precip/temp/et that Neon doesn't have)
    print("=== Syncing weather data ===")
    lcur.execute("""
        SELECT asset_id, source_id, observed_at, water_level_ft, inflow_cusecs, 
               outflow_cusecs, discharge_cusecs, upstream_discharge_cusecs,
               downstream_discharge_cusecs, precip_mm, temp_max_c, temp_min_c, 
               et0_mm, soil_moisture_m3, data_status, data_origin, source_priority
        FROM aquavision.water_observations
        WHERE precip_mm IS NOT NULL OR temp_max_c IS NOT NULL OR et0_mm IS NOT NULL
        ORDER BY asset_id, observed_at
    """)
    rows = lcur.fetchall()
    print(f"  Local rows with weather: {len(rows)}")
    
    synced = 0
    skipped = 0
    for row in rows:
        try:
            ncur.execute("""
                INSERT INTO aquavision.water_observations 
                    (asset_id, source_id, observed_at, water_level_ft, inflow_cusecs,
                     outflow_cusecs, discharge_cusecs, upstream_discharge_cusecs,
                     downstream_discharge_cusecs, precip_mm, temp_max_c, temp_min_c,
                     et0_mm, soil_moisture_m3, data_status, data_origin, source_priority)
                VALUES (%(asset_id)s, %(source_id)s, %(observed_at)s, %(water_level_ft)s, %(inflow_cusecs)s,
                        %(outflow_cusecs)s, %(discharge_cusecs)s, %(upstream_discharge_cusecs)s,
                        %(downstream_discharge_cusecs)s, %(precip_mm)s, %(temp_max_c)s, %(temp_min_c)s,
                        %(et0_mm)s, %(soil_moisture_m3)s, %(data_status)s, %(data_origin)s, %(source_priority)s)
                ON CONFLICT (asset_id, observed_at, source_id) DO UPDATE SET
                    precip_mm = COALESCE(EXCLUDED.precip_mm, aquavision.water_observations.precip_mm),
                    temp_max_c = COALESCE(EXCLUDED.temp_max_c, aquavision.water_observations.temp_max_c),
                    temp_min_c = COALESCE(EXCLUDED.temp_min_c, aquavision.water_observations.temp_min_c),
                    et0_mm = COALESCE(EXCLUDED.et0_mm, aquavision.water_observations.et0_mm),
                    inflow_cusecs = COALESCE(EXCLUDED.inflow_cusecs, aquavision.water_observations.inflow_cusecs)
            """, dict(row))
            synced += 1
        except Exception as e:
            skipped += 1
            if skipped <= 3:
                print(f"  Skip: {e}")
    
    neon.commit()
    print(f"  Synced: {synced}, Skipped: {skipped}")
    
    # 2. Verify Neon counts
    print("\n=== Neon data counts ===")
    ncur.execute("""
        SELECT asset_id, COUNT(*) as cnt,
               SUM(CASE WHEN precip_mm IS NOT NULL THEN 1 ELSE 0 END) as weather,
               SUM(CASE WHEN inflow_cusecs IS NOT NULL THEN 1 ELSE 0 END) as hydro
        FROM aquavision.water_observations
        GROUP BY asset_id ORDER BY asset_id
    """)
    for row in ncur.fetchall():
        print(f"  Asset {row['asset_id']:2d}: {row['cnt']:5d} total, {row['weather'] or 0:5d} weather, {row['hydro'] or 0:5d} hydro")
    
    lcur.close()
    ncur.close()
    local.close()
    neon.close()

if __name__ == "__main__":
    sync()
