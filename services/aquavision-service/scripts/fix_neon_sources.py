import psycopg2

neon = psycopg2.connect("postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require")
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
