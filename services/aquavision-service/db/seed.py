"""Seed database with water assets and auth users.
Idempotent — safe to run multiple times.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from infrastructure.db.engine import SessionLocal

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
    (1, 1, 'population_center', 'Islamabad', 1095000, 33.6941, 73.0479, 0, 0),
    (2, 1, 'population_center', 'Rawalpindi', 2098000, 33.5651, 73.0169, 15, 0.5),
    (3, 4, 'population_center', 'Mianwali', 118000, 32.5833, 71.5333, 0, 0),
    (4, 5, 'population_center', 'Dera Ghazi Khan', 472000, 30.0500, 70.6333, 0, 0),
    (5, 6, 'population_center', 'Sukkur', 541000, 27.7167, 68.8500, 0, 0),
    (6, 7, 'population_center', 'Hyderabad', 1733000, 25.3960, 68.3580, 0, 0),
    (7, 8, 'population_center', 'Karachi', 14910000, 24.8607, 67.0011, 0, 0),
    (8, 5, 'population_center', 'Multan', 1872000, 30.1575, 71.5249, 120, 48),
]

AUTH_USERS = [
    (1, 'Admin User', 'admin@ibcp.gov.pk', '$2b$12$kTNWCiUIAhlo61Ac1ASoeuWrg143yAghH0UMKX.D12O3gp.i4B3f2'),
    (2, 'Aqua Analyst', 'water@ibcp.gov.pk', '$2b$12$j1.l8FtgitiR7BZl69mcyOW5NXanthEu/Vtik0By89zcwnHUWQ3pq'),
    (3, 'Field Officer', 'field@ibcp.gov.pk', '$2b$12$n/RxH0M7swDkKqZAspuFS.uUYZu8uyM5oYdkFIzKUIonaktDUAl2K'),
]


def seed():
    session = SessionLocal()
    try:
        # Check if already seeded
        result = session.execute(text("SELECT count(*) FROM aquavision.water_assets"))
        count = result.scalar()
        if count >= 11:
            print(f"Already seeded ({count} assets). Skipping.")
            return

        print("Seeding water_assets...")
        for a in WATER_ASSETS:
            session.execute(text("""
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
        session.execute(text("SELECT setval('aquavision.water_assets_id_seq', 11)"))

        print("Seeding downstream_impacts...")
        for i in DOWNSTREAM_IMPACTS:
            session.execute(text("""
                INSERT INTO aquavision.water_downstream_impacts
                (id, asset_id, impact_type, name, population, latitude, longitude, distance_km, travel_time_hours)
                VALUES (:id, :asset, :type, :name, :pop, :lat, :lon, :dist, :travel)
                ON CONFLICT (id) DO NOTHING
            """), {"id": i[0], "asset": i[1], "type": i[2], "name": i[3],
                   "pop": i[4], "lat": i[5], "lon": i[6], "dist": i[7], "travel": i[8]})
        session.execute(text("SELECT setval('aquavision.water_downstream_impacts_id_seq', 16)"))

        print("Seeding auth users...")
        for u in AUTH_USERS:
            session.execute(text("""
                INSERT INTO shared.users (id, name, email, password_hash, is_active)
                VALUES (:id, :name, :email, :hash, true)
                ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
            """), {"id": u[0], "name": u[1], "email": u[2], "hash": u[3]})
        session.execute(text("SELECT setval('shared.users_id_seq', 3)"))

        session.commit()
        print("Seeding complete: 11 assets, 8 impacts, 3 users")
    except Exception as e:
        session.rollback()
        print(f"Seed error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
