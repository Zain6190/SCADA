-- IBCP-SCADA Seed Data
-- Run after Alembic migrations: docker compose exec db psql -U postgres -d ibcp_scada -f /docker-entrypoint-initdb.d/seed.sql

-- =====================================================
-- WATER ASSETS (11 monitoring stations)
-- =====================================================
INSERT INTO aquavision.water_assets (id, canonical_name, asset_type, river, province, district, latitude, longitude, capacity_maf, normal_level_ft, dead_level_ft, warning_level_ft, critical_level_ft, source_authority, source_identifier, is_active)
VALUES
(1, 'Tarbela Reservoir', 'reservoir', 'Indus', 'KPK', 'Haripur', 34.0887, 72.6837, 11.47, 1550, 1355, 1540, 1550, 'IRSA', 'tarbela', true),
(2, 'Mangla Reservoir', 'reservoir', 'Jhelum', 'AJK', 'Mirpur', 33.1387, 73.6437, 7.39, 1242, 1040, 1235, 1242, 'IRSA', 'mangla', true),
(3, 'Chashma Barrage', 'barrage', 'Indus', 'Punjab', 'Mianwali', 32.4927, 71.4707, 0.88, 648, 637, 647, 648, 'IRSA', 'chashma', true),
(4, 'Kalabagh', 'barrage', 'Indus', 'Punjab', 'Mianwali', 32.9627, 71.4807, NULL, 640, 630, 638, 640, 'IRSA', 'kalabagh', true),
(5, 'Taunsa Barrage', 'barrage', 'Indus', 'Punjab', 'Dera Ghazi Khan', 30.5007, 71.2577, 1.32, 507, 490, 505, 507, 'IRSA', 'taunsa', true),
(6, 'Guddu Barrage', 'barrage', 'Indus', 'Sindh', 'Ghotki', 28.4407, 68.7347, 1.22, 404, 390, 402, 404, 'IRSA', 'guddu', true),
(7, 'Sukkur Barrage', 'barrage', 'Indus', 'Sindh', 'Sukkur', 27.7147, 68.8317, 1.36, 268, 255, 266, 268, 'IRSA', 'sukkur', true),
(8, 'Kotri Barrage', 'barrage', 'Indus', 'Sindh', 'Jamshoro', 25.3507, 68.3157, 0.93, 10, 0, 8, 10, 'IRSA', 'kotri', true),
(9, 'Kabul @ Nowshera', 'river_station', 'Kabul', 'KPK', 'Nowshera', 34.0107, 71.9787, NULL, NULL, NULL, NULL, NULL, 'FFD/PMD', 'kabul_nowshera', true),
(10, 'Chenab @ Marala', 'river_station', 'Chenab', 'Punjab', 'Sialkot', 32.4987, 74.5547, NULL, NULL, NULL, NULL, NULL, 'FFD/PMD', 'chenab_marala', true),
(11, 'Panjnad', 'river_station', 'Panjnad', 'Punjab', 'Bahawalpur', 29.3907, 71.2527, NULL, NULL, NULL, NULL, NULL, 'IRSA', 'panjnad', true)
ON CONFLICT (id) DO UPDATE SET
  canonical_name = EXCLUDED.canonical_name,
  asset_type = EXCLUDED.asset_type,
  river = EXCLUDED.river,
  province = EXCLUDED.province,
  district = EXCLUDED.district,
  latitude = EXCLUDED.latitude,
  longitude = EXCLUDED.longitude,
  capacity_maf = EXCLUDED.capacity_maf,
  normal_level_ft = EXCLUDED.normal_level_ft,
  dead_level_ft = EXCLUDED.dead_level_ft,
  warning_level_ft = EXCLUDED.warning_level_ft,
  critical_level_ft = EXCLUDED.critical_level_ft,
  is_active = EXCLUDED.is_active;

SELECT setval('aquavision.water_assets_id_seq', 11);

-- =====================================================
-- DOWNSTREAM IMPACTS (population, bridges, hospitals)
-- =====================================================
INSERT INTO aquavision.water_downstream_impacts (id, asset_id, impact_type, name, population, latitude, longitude, distance_km, travel_time_hours)
VALUES
(1, 1, 'population_center', 'Islamabad', 1095000, 33.6941, 73.0479, 0, 0),
(2, 1, 'population_center', 'Rawalpindi', 2098000, 33.5651, 73.0169, 15, 0.5),
(3, 4, 'population_center', 'Mianwali', 118000, 32.5833, 71.5333, 0, 0),
(4, 5, 'population_center', 'Dera Ghazi Khan', 472000, 30.0500, 70.6333, 0, 0),
(5, 6, 'population_center', 'Sukkur', 541000, 27.7167, 68.8500, 0, 0),
(6, 7, 'population_center', 'Hyderabad', 1733000, 25.3960, 68.3580, 0, 0),
(7, 8, 'population_center', 'Karachi', 14910000, 24.8607, 67.0011, 0, 0),
(8, 5, 'population_center', 'Multan', 1872000, 30.1575, 71.5249, 120, 48),
(9, 4, 'bridge', 'Kalabagh Bridge', NULL, 32.9627, 71.4807, 0, 0),
(10, 5, 'bridge', 'Taunsa Barrage Bridge', NULL, 30.5007, 71.2577, 0, 0),
(11, 6, 'bridge', 'Guddu Bridge', NULL, 28.4407, 68.7347, 0, 0),
(12, 7, 'bridge', 'Sukkur Bridge', NULL, 27.7147, 68.8317, 0, 0),
(13, 8, 'bridge', 'Kotri Bridge', NULL, 25.3507, 68.3157, 0, 0),
(14, 8, 'hospital', 'Civil Hospital Karachi', 3000, 24.8607, 67.0011, 0, 0),
(15, 7, 'hospital', 'Civil Hospital Sukkur', 1200, 27.7147, 68.8317, 0, 0),
(16, 6, 'hospital', 'Guddu Hospital', 500, 28.4407, 68.7347, 0, 0)
ON CONFLICT (id) DO NOTHING;

SELECT setval('aquavision.water_downstream_impacts_id_seq', 16);

-- =====================================================
-- AUTH USERS
-- =====================================================
INSERT INTO shared.users (id, name, email, password_hash, is_active)
VALUES
(1, 'Admin User', 'admin@ibcp.gov.pk', '$2b$12$kTNWCiUIAhlo61Ac1ASoeuWrg143yAghH0UMKX.D12O3gp.i4B3f2', true),
(2, 'Aqua Analyst', 'water@ibcp.gov.pk', '$2b$12$j1.l8FtgitiR7BZl69mcyOW5NXanthEu/Vtik0By89zcwnHUWQ3pq', true),
(3, 'Field Officer', 'field@ibcp.gov.pk', '$2b$12$n/RxH0M7swDkKqZAspuFS.uUYZu8uyM5oYdkFIzKUIonaktDUAl2K', true)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  email = EXCLUDED.email,
  password_hash = EXCLUDED.password_hash;

SELECT setval('shared.users_id_seq', 3);
