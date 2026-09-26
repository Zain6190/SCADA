import psycopg2
from _db_urls import local_url, neon_url

local = psycopg2.connect(local_url())
neon = psycopg2.connect(neon_url())

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
