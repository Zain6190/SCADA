"""Seed DB directly with psycopg2. Reads DATABASE_URL from env."""
import os
import psycopg2

DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    print("DATABASE_URL not set — skipping seed")
    exit(0)

WATER_ASSETS = [
    (1, 'Tarbela Reservoir', 'reservoir', 'Indus', 'KPK', 'Haripur', 34.0887, 72.6837, 11.47, 1550, 1355, 1540, 1550, 'IRSA', 'tarbela'),
    (2, 'Mangla Reservoir', 'reservoir', 'Jhelum', 'AJK', 'Mirpur', 33.1387, 73.6437, 7.39, 1242, 1040, 1235, 1242, 'IRSA', 'mangla'),
    (3, 'Chashma Barrage', 'barrage', 'Indus', 'Punjab', 'Mianwali', 32.4927, 71.4707, 0.88, 648, 637, 647, 648, 'IRSA', 'chashma'),
    (4, 'Kalabagh', 'barrage', 'Indus', 'Punjab', 'Mianwali', 32.9627, 71.4807, None, 640, 630, 638, 640, 'IRSA', 'kalabagh'),
    (5, 'Taunsa Barrage', 'barrage', 'Indus', 'Punjab', 'Dera Ghazi Khan', 30.5007, 71.2577, 1.32, 507, 490, 505, 507, 'IRSA', 'taunsa'),
    (6, 'Guddu Barrage', 'barrage', 'Indus', 'Sindh', 'Ghotki', 28.4407, 68.7347, 1.22, 404, 390, 402, 404, 'IRSA', 'guddu'),
    (7, 'Sukkur Barrage', 'barrage', 'Indus', 'Sindh', 'Sukkur', 27.7147, 68.8317, 1.36, 268, 255, 266, 268, 'IRSA', 'sukkur'),
    (8, 'Kotri Barrage', 'barrage', 'Indus', 'Sindh', 'Jamshoro', 25.3507, 68.3157, 0.93, 10, 0, 8, 10, 'IRSA', 'kotri'),
    (9, 'Kabul @ Nowshera', 'river_station', 'Kabul', 'KPK', 'Nowshera', 34.0107, 71.9787, None, None, None, None, None, 'FFD/PMD', 'kabul_nowshera'),
    (10, 'Chenab @ Marala', 'river_station', 'Chenab', 'Punjab', 'Sialkot', 32.4987, 74.5547, None, None, None, None, None, 'FFD/PMD', 'chenab_marala'),
    (11, 'Panjnad', 'river_station', 'Panjnad', 'Punjab', 'Bahawalpur', 29.3907, 71.2527, None, None, None, None, None, 'IRSA', 'panjnad'),
]

DOWNSTREAM_IMPACTS = [
    (1, 1, 4, 24, 30, 26, 120, 3193000, 150, 5, 2, 45, 12, 350),
    (2, 4, 5, 68, 76, 72, 250, 590000, 80, 3, 1, 30, 8, 280),
    (3, 5, 6, 44, 52, 48, 350, 2413000, 120, 4, 2, 55, 10, 400),
    (4, 6, 7, 20, 28, 24, 180, 2274000, 90, 3, 1, 35, 7, 220),
    (5, 7, 8, 74, 82, 78, 380, 16644000, 200, 8, 3, 60, 15, 500),
    (6, 10, 11, 105, 117, 111, 500, 500000, 60, 2, 1, 25, 5, 180),
    (7, 11, 6, 20, 28, 24, 150, 1872000, 70, 3, 1, 20, 4, 160),
]

AUTH_USERS = [
    (1, 'Admin User', 'admin@ibcp.gov.pk', '$2b$12$kTNWCiUIAhlo61Ac1ASoeuWrg143yAghH0UMKX.D12O3gp.i4B3f2'),
    (2, 'Aqua Analyst', 'water@ibcp.gov.pk', '$2b$12$j1.l8FtgitiR7BZl69mcyOW5NXanthEu/Vtik0By89zcwnHUWQ3pq'),
    (3, 'Field Officer', 'field@ibcp.gov.pk', '$2b$12$n/RxH0M7swDkKqZAspuFS.uUYZu8uyM5oYdkFIzKUIonaktDUAl2K'),
]

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute("SELECT count(*) FROM aquavision.water_assets")
count = cur.fetchone()[0]
if count >= 11:
    print(f"Already seeded ({count} assets). Skipping.")
else:
    print("Seeding water_assets...")
    for a in WATER_ASSETS:
        cur.execute("""
            INSERT INTO aquavision.water_assets 
            (id, canonical_name, asset_type, river, province, district, 
             latitude, longitude, capacity_maf, normal_level_ft, dead_level_ft,
             warning_level_ft, critical_level_ft, source_authority, source_identifier, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            ON CONFLICT (id) DO UPDATE SET canonical_name=EXCLUDED.canonical_name
        """, (a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8],
              a[9], a[10], a[11], a[12], a[13], a[14]))
    cur.execute("SELECT setval('aquavision.water_assets_id_seq', 11)")

    print("Seeding downstream_impacts...")
    for i in DOWNSTREAM_IMPACTS:
        cur.execute("""
            INSERT INTO aquavision.water_downstream_impacts
            (id, source_asset_id, downstream_asset_id, travel_time_hours_min, travel_time_hours_max,
             travel_time_hours_expected, distance_km, affected_population_est, affected_village_count,
             affected_town_count, affected_city_count, bridges_count, hospitals_count, roads_km)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7], i[8], i[9], i[10], i[11], i[12], i[13]))
    cur.execute("SELECT setval('aquavision.water_downstream_impacts_id_seq', 16)")

    print("Seeding auth users...")
    for u in AUTH_USERS:
        cur.execute("""
            INSERT INTO shared.users (id, name, email, password_hash, is_active)
            VALUES (%s, %s, %s, %s, true)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
        """, (u[0], u[1], u[2], u[3]))
    cur.execute("SELECT setval('shared.users_id_seq', 3)")

    conn.commit()
    print("Seeding complete: 11 assets, 8 impacts, 3 users")

cur.close()
conn.close()
