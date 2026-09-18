import psycopg2

local = psycopg2.connect("postgresql://postgres:1234@172.19.0.2:5432/ibcp_scada")
neon = psycopg2.connect("postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require")

lcur = local.cursor()
ncur = neon.cursor()

print("=== LOCAL water_sources ===")
lcur.execute("SELECT id, authority FROM aquavision.water_sources ORDER BY id")
for r in lcur.fetchall():
    print(f"  Source {r[0]}: {r[1]}")

print("\n=== NEON water_sources ===")
ncur.execute("SELECT id, authority FROM aquavision.water_sources ORDER BY id")
for r in ncur.fetchall():
    print(f"  Source {r[0]}: {r[1]}")

# Check what source_ids are used in local observations
print("\n=== LOCAL source_ids in observations ===")
lcur.execute("SELECT source_id, COUNT(*) FROM aquavision.water_observations GROUP BY source_id ORDER BY source_id")
for r in lcur.fetchall():
    print(f"  source_id={r[0]}: {r[1]} rows")

lcur.close()
ncur.close()
local.close()
neon.close()
