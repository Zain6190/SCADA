"""
Bulk sync weather data from local DB to Neon using COPY.
"""
import io
import psycopg2

LOCAL_URL = "postgresql://postgres:1234@172.19.0.2:5432/ibcp_scada"
NEON_URL = "postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

COLS = [
    "asset_id", "source_id", "observed_at", "water_level_ft", "inflow_cusecs",
    "outflow_cusecs", "discharge_cusecs", "upstream_discharge_cusecs",
    "downstream_discharge_cusecs", "precip_mm", "temp_max_c", "temp_min_c",
    "et0_mm", "soil_moisture_m3", "data_status", "data_origin", "source_priority"
]

def sync():
    local = psycopg2.connect(LOCAL_URL)
    neon = psycopg2.connect(NEON_URL)
    
    lcur = local.cursor()
    ncur = neon.cursor()
    
    # Get all rows with weather or physics data
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
    
    # Use COPY for bulk insert
    buffer = io.StringIO()
    count = 0
    for row in rows:
        line = "\t".join([
            str(row[0]) if row[0] is not None else "\\N",
            str(row[1]) if row[1] is not None else "\\N",
            str(row[2]) if row[2] is not None else "\\N",
            str(row[3]) if row[3] is not None else "\\N",
            str(row[4]) if row[4] is not None else "\\N",
            str(row[5]) if row[5] is not None else "\\N",
            str(row[6]) if row[6] is not None else "\\N",
            str(row[7]) if row[7] is not None else "\\N",
            str(row[8]) if row[8] is not None else "\\N",
            str(row[9]) if row[9] is not None else "\\N",
            str(row[10]) if row[10] is not None else "\\N",
            str(row[11]) if row[11] is not None else "\\N",
            str(row[12]) if row[12] is not None else "\\N",
            str(row[13]) if row[13] is not None else "\\N",
            str(row[14]) if row[14] is not None else "\\N",
            str(row[15]) if row[15] is not None else "\\N",
            str(row[16]) if row[16] is not None else "\\N",
        ]) + "\n"
        buffer.write(line)
        count += 1
    
    buffer.seek(0)
    print(f"Prepared {count} rows for COPY")
    
    # Copy to Neon
    columns = ", ".join(COLS)
    ncur.copy_expert(
        f"COPY aquavision.water_observations ({columns}) FROM STDIN WITH (FORMAT text, NULL '\\N')",
        buffer
    )
    neon.commit()
    print(f"Copied {count} rows to Neon")
    
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
