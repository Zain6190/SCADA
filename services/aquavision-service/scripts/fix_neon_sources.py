import psycopg2
from _db_urls import neon_url

neon = psycopg2.connect(neon_url())
cur = neon.cursor()

cur.execute("SELECT id, authority FROM aquavision.water_sources ORDER BY id")
print("Before:")
for r in cur.fetchall():
    print(f"  Source {r[0]}: {r[1]}")

for auth in ["KAGGLE", "OPEN_METEO", "PHYSICS_MODEL"]:
    cur.execute(
        "INSERT INTO aquavision.water_sources (authority, source_url, source_type, update_frequency, description) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (auth, "internal", "API", "DAILY", f"{auth} source")
    )

neon.commit()

cur.execute("SELECT id, authority FROM aquavision.water_sources ORDER BY id")
print("After:")
for r in cur.fetchall():
    print(f"  Source {r[0]}: {r[1]}")

cur.close()
neon.close()
