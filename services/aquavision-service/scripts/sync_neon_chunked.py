"""
Sync weather + physics data from local DB to Neon, handling duplicates.
"""
import psycopg2

LOCAL_URL = "postgresql://postgres:1234@172.19.0.2:5432/ibcp_scada"
NEON_URL = "postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

def sync():
    local = psycopg2.connect(LOCAL_URL)
    neon = psycopg2.connect(NEON_URL)
    
    lcur = local.cursor()
    ncur = neon.cursor()
    
    lcur.execute("""
        SELECT asset_id, source_id, observed_at, water_level_ft, inflow_cusecs,
               outflow_cusecs, discharge_cusecs, upstream_discharge_cusecs,
               downstream_discharge_cusecs, precip_mm, temp_max_c, temp_min_c,
               et0_mm, soil_moisture_m3, data_status, data_origin, source_priority
        FROM aquavision.water_observations
        WHERE precip_mm IS NOT NULL OR temp_max_c IS NOT NULL OR et0_mm IS NOT NULL
           OR data_origin = 'ESTIMATED_PHYSICS'
        ORDER BY asset_id, observed_at
    """)
    
    rows = lcur.fetchall()
    print(f"Fetched {len(rows)} rows from local DB")
    
    inserted = 0
    updated = 0
    errors = 0
    chunk_size = 500
    
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i+chunk_size]
        values = []
        for row in chunk:
            values.append(tuple(str(v) if v is not None else None for v in row))
        
        args_str = ",".join(
            ncur.mogrify(
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", v
            ).decode() for v in values
        )
        
        try:
            ncur.execute(f"""
                INSERT INTO aquavision.water_observations 
                    (asset_id, source_id, observed_at, water_level_ft, inflow_cusecs,
                     outflow_cusecs, discharge_cusecs, upstream_discharge_cusecs,
                     downstream_discharge_cusecs, precip_mm, temp_max_c, temp_min_c,
                     et0_mm, soil_moisture_m3, data_status, data_origin, source_priority)
                VALUES {args_str}
                ON CONFLICT (asset_id, observed_at, source_id) DO UPDATE SET
                    precip_mm = COALESCE(EXCLUDED.precip_mm, aquavision.water_observations.precip_mm),
                    temp_max_c = COALESCE(EXCLUDED.temp_max_c, aquavision.water_observations.temp_max_c),
                    temp_min_c = COALESCE(EXCLUDED.temp_min_c, aquavision.water_observations.temp_min_c),
                    et0_mm = COALESCE(EXCLUDED.et0_mm, aquavision.water_observations.et0_mm),
                    inflow_cusecs = COALESCE(EXCLUDED.inflow_cusecs, aquavision.water_observations.inflow_cusecs),
                    data_status = COALESCE(EXCLUDED.data_status, aquavision.water_observations.data_status),
                    data_origin = COALESCE(EXCLUDED.data_origin, aquavision.water_observations.data_origin)
            """)
            neon.commit()
            inserted += len(chunk)
            if inserted % 5000 == 0:
                print(f"  Progress: {inserted}/{len(rows)}")
        except Exception as e:
            errors += 1
            neon.rollback()
            if errors <= 3:
                print(f"  Chunk error: {e}")
    
    print(f"\nInserted/updated: {inserted}, Errors: {errors}")
    
    # Verify
    ncur.execute("""
        SELECT asset_id, COUNT(*) as cnt,
               SUM(CASE WHEN precip_mm IS NOT NULL THEN 1 ELSE 0 END) as weather,
               SUM(CASE WHEN inflow_cusecs IS NOT NULL THEN 1 ELSE 0 END) as hydro
        FROM aquavision.water_observations
        GROUP BY asset_id ORDER BY asset_id
    """)
    print("\n=== Neon data counts ===")
    for row in ncur.fetchall():
        print(f"  Asset {row[0]:2d}: {row[1]:5d} total, {row[2] or 0:5d} weather, {row[3] or 0:5d} hydro")
    
    lcur.close()
    ncur.close()
    local.close()
    neon.close()

if __name__ == "__main__":
    sync()
