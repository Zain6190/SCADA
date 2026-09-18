import psycopg2

neon = psycopg2.connect("postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require")
cur = neon.cursor()

# Local has: 1=IRSA, 2=FFD/PMD, 3=KAGGLE, 4=SENSOR_API, 5=GEE
# Neon has:  1=KAGGLE, 2=FFD/PMD, 4=OPEN_METEO, 5=PHYSICS_MODEL
# We need to create source_id=3=KAGGLE, 1=IRSA in Neon

# Create IRSA as source_id=1
cur.execute("""
    INSERT INTO aquavision.water_sources (id, authority, source_url, source_type, update_frequency, description)
    VALUES (1, 'IRSA', 'http://pakirsa.gov.pk', 'PDF_DAILY_REPORT', 'DAILY', 'Indus River System Authority')
    ON CONFLICT (id) DO UPDATE SET authority='IRSA'
""")

# Create KAGGLE as source_id=3
cur.execute("""
    INSERT INTO aquavision.water_sources (id, authority, source_url, source_type, update_frequency, description)
    VALUES (3, 'KAGGLE', 'kaggle.com', 'CSV', 'ONE_TIME', 'Pakistan Rivers Flow dataset')
    ON CONFLICT (id) DO UPDATE SET authority='KAGGLE'
""")

# Create SENSOR_API as source_id=4
cur.execute("""
    INSERT INTO aquavision.water_sources (id, authority, source_url, source_type, update_frequency, description)
    VALUES (4, 'SENSOR_API', 'internal', 'API', 'REAL_TIME', 'Sensor telemetry')
    ON CONFLICT (id) DO UPDATE SET authority='SENSOR_API'
""")

# Create GEE as source_id=5
cur.execute("""
    INSERT INTO aquavision.water_sources (id, authority, source_url, source_type, update_frequency, description)
    VALUES (5, 'GEE', 'earthengine.google.com', 'API', 'MONTHLY', 'Google Earth Engine satellite data')
    ON CONFLICT (id) DO UPDATE SET authority='GEE'
""")

neon.commit()

cur.execute("SELECT id, authority FROM aquavision.water_sources ORDER BY id")
print("Neon sources after fix:")
for r in cur.fetchall():
    print(f"  Source {r[0]}: {r[1]}")

cur.close()
neon.close()
