"""Seed Neon DB directly with SQLAlchemy."""
from sqlalchemy import create_engine, text

NEON_URL = "postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

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
    # (id, source_asset_id, downstream_asset_id, travel_min, travel_max, travel_expected, distance_km, affected_pop, villages, towns, cities, bridges, hospitals, roads_km)
    (1, 1, 4, 24, 30, 26, 120, 3193000, 150, 5, 2, 45, 12, 350),   # Tarbela→Kalabagh (Islamabad+Rawalpindi)
    (2, 4, 5, 68, 76, 72, 250, 590000, 80, 3, 1, 30, 8, 280),      # Kalabagh→Taunsa (Mianwali+DG Khan)
    (3, 5, 6, 44, 52, 48, 350, 2413000, 120, 4, 2, 55, 10, 400),   # Taunsa→Guddu (Sukkur+Multan)
    (4, 6, 7, 20, 28, 24, 180, 2274000, 90, 3, 1, 35, 7, 220),     # Guddu→Sukkur (Hyderabad)
    (5, 7, 8, 74, 82, 78, 380, 16644000, 200, 8, 3, 60, 15, 500),  # Sukkur→Kotri (Karachi)
    (6, 10, 11, 105, 117, 111, 500, 500000, 60, 2, 1, 25, 5, 180),  # Marala→Panjnad
    (7, 11, 6, 20, 28, 24, 150, 1872000, 70, 3, 1, 20, 4, 160),    # Panjnad→Guddu (Multan)
]

AUTH_USERS = [
    (1, 'Admin User', 'admin@ibcp.gov.pk', '$2b$12$kTNWCiUIAhlo61Ac1ASoeuWrg143yAghH0UMKX.D12O3gp.i4B3f2'),
    (2, 'Aqua Analyst', 'water@ibcp.gov.pk', '$2b$12$j1.l8FtgitiR7BZl69mcyOW5NXanthEu/Vtik0By89zcwnHUWQ3pq'),
    (3, 'Field Officer', 'field@ibcp.gov.pk', '$2b$12$n/RxH0M7swDkKqZAspuFS.uUYZu8uyM5oYdkFIzKUIonaktDUAl2K'),
]

e = create_engine(NEON_URL)
c = e.connect()

count = c.execute(text("SELECT count(*) FROM aquavision.water_assets")).scalar()
if count >= 11:
    print(f"Already seeded ({count} assets). Skipping.")
else:
    print("Seeding water_assets...")
    for a in WATER_ASSETS:
        c.execute(text("""
            INSERT INTO aquavision.water_assets 
            (id, canonical_name, asset_type, river, province, district, 
             latitude, longitude, capacity_maf, normal_level_ft, dead_level_ft,
             warning_level_ft, critical_level_ft, source_authority, source_identifier, is_active)
            VALUES (:id, :name, :type, :river, :province, :district,
                    :lat, :lon, :cap, :normal, :dead, :warn, :crit, :auth, :src, true)
            ON CONFLICT (id) DO UPDATE SET canonical_name=EXCLUDED.canonical_name
        """), {"id": a[0], "name": a[1], "type": a[2], "river": a[3], "province": a[4],
               "district": a[5], "lat": a[6], "lon": a[7], "cap": a[8],
               "normal": a[9], "dead": a[10], "warn": a[11], "crit": a[12],
               "auth": a[13], "src": a[14]})
    c.execute(text("SELECT setval('aquavision.water_assets_id_seq', 11)"))

    print("Seeding downstream_impacts...")
    for i in DOWNSTREAM_IMPACTS:
        c.execute(text("""
            INSERT INTO aquavision.water_downstream_impacts
            (id, source_asset_id, downstream_asset_id, travel_time_hours_min, travel_time_hours_max,
             travel_time_hours_expected, distance_km, affected_population_est, affected_village_count,
             affected_town_count, affected_city_count, bridges_count, hospitals_count, roads_km)
            VALUES (:id, :src, :dst, :tmin, :tmax, :texp, :dist, :pop, :villages, :towns, :cities, :bridges, :hospitals, :roads)
            ON CONFLICT (id) DO NOTHING
        """), {"id": i[0], "src": i[1], "dst": i[2], "tmin": i[3], "tmax": i[4], "texp": i[5],
               "dist": i[6], "pop": i[7], "villages": i[8], "towns": i[9], "cities": i[10],
               "bridges": i[11], "hospitals": i[12], "roads": i[13]})
    c.execute(text("SELECT setval('aquavision.water_downstream_impacts_id_seq', 16)"))

    print("Seeding auth users...")
    for u in AUTH_USERS:
        c.execute(text("""
            INSERT INTO shared.users (id, name, email, password_hash, is_active)
            VALUES (:id, :name, :email, :hash, true)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
        """), {"id": u[0], "name": u[1], "email": u[2], "hash": u[3]})
    c.execute(text("SELECT setval('shared.users_id_seq', 3)"))

    c.commit()
    print("Seeding complete: 11 assets, 8 impacts, 3 users")

c.close()
