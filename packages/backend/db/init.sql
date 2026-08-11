-- =====================================================================
-- IBCP-SCADA - PostgreSQL 16 + PostGIS schema DDL
-- Schemas: shared, aquavision, crop, geo, system
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------
-- SCHEMAS
-- ---------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS shared;
CREATE SCHEMA IF NOT EXISTS aquavision;
CREATE SCHEMA IF NOT EXISTS crop;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS system;

-- =====================================================================
-- SHARED SCHEMA (users, roles, permissions, regions, assets, datasets)
-- =====================================================================

CREATE TABLE shared.users (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE shared.roles (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE shared.permissions (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE shared.user_roles (
    user_id BIGINT NOT NULL REFERENCES shared.users(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES shared.roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE shared.role_permissions (
    role_id       BIGINT NOT NULL REFERENCES shared.roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES shared.permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- Geographic scope (FAIL-CLOSED): a user with NO active scope is denied access.
-- NATIONAL must be explicit (region_id/asset_id NULL). Missing rows are never
-- interpreted as national access.
CREATE TABLE shared.user_region_scopes (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES shared.users(id) ON DELETE CASCADE,
    scope_type  TEXT NOT NULL
                CONSTRAINT ck_user_region_scope_type
                CHECK (scope_type IN ('NATIONAL','PROVINCE','DISTRICT','ASSET')),
    region_id   BIGINT REFERENCES shared.regions(id) ON DELETE CASCADE,
    asset_id    BIGINT REFERENCES shared.assets(id) ON DELETE CASCADE,
    granted_by  BIGINT REFERENCES shared.users(id),
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_user_scope_target CHECK (
        (scope_type = 'NATIONAL' AND region_id IS NULL AND asset_id IS NULL) OR
        (scope_type IN ('PROVINCE','DISTRICT') AND region_id IS NOT NULL AND asset_id IS NULL) OR
        (scope_type = 'ASSET' AND asset_id IS NOT NULL AND region_id IS NULL)
    )
);
CREATE UNIQUE INDEX uq_user_region_scope_active
    ON shared.user_region_scopes (user_id, scope_type, region_id, asset_id)
    WHERE is_active;

CREATE TABLE shared.regions (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    code            TEXT UNIQUE,
    type            TEXT NOT NULL CHECK (type IN ('province','district','tehsil')),
    parent_region_id BIGINT REFERENCES shared.regions(id),
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_regions_geom        ON shared.regions USING GIST (geom);
CREATE INDEX idx_regions_type        ON shared.regions (type);
CREATE INDEX idx_regions_parent      ON shared.regions (parent_region_id);

CREATE TABLE shared.assets (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('dam','reservoir','canal','river','wetland','field','barrage')),
    region_id  BIGINT REFERENCES shared.regions(id),
    geom       geometry(Polygon, 4326) NOT NULL,
    source     TEXT,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    metadata   JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_assets_geom    ON shared.assets USING GIST (geom);
CREATE INDEX idx_assets_type    ON shared.assets (asset_type);
CREATE INDEX idx_assets_region  ON shared.assets (region_id);

CREATE TABLE shared.datasets (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    domain        TEXT CHECK (domain IN ('water','crop','geo')),
    source        TEXT,
    description   TEXT,
    last_updated  TIMESTAMPTZ,
    status        TEXT DEFAULT 'active'
);

-- =====================================================================
-- AQUAVISION SCHEMA
-- =====================================================================

CREATE TABLE aquavision.water_indicators_weekly (
    id                       BIGSERIAL PRIMARY KEY,
    region_id                BIGINT NOT NULL REFERENCES shared.regions(id),
    week_start_date          DATE NOT NULL,
    week_number              INT,
    year                     INT,
    surface_water_area_km2   NUMERIC,
    surface_water_change_pct NUMERIC,
    rainfall_mm_30day        NUMERIC,
    rainfall_anomaly         NUMERIC,
    et_mm_8day               NUMERIC,
    et_anomaly               NUMERIC,
    wai_score                NUMERIC,
    severity                 TEXT CHECK (severity IN ('Normal','Moderate','Stressed','Critical','Severe')),
    data_source_version      TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (region_id, week_start_date)
);
CREATE INDEX idx_water_ind_region_week ON aquavision.water_indicators_weekly (region_id, week_start_date);
CREATE INDEX idx_water_ind_year_week   ON aquavision.water_indicators_weekly (year, week_number);
CREATE INDEX idx_water_ind_severity    ON aquavision.water_indicators_weekly (severity);

CREATE TABLE aquavision.water_predictions_weekly (
    id                     BIGSERIAL PRIMARY KEY,
    region_id              BIGINT NOT NULL REFERENCES shared.regions(id),
    target_week_start_date DATE NOT NULL,
    model_type             TEXT CHECK (model_type IN ('RandomForest','XGBoost')),
    model_version          TEXT NOT NULL,
    predicted_severity     TEXT,
    predicted_wai_score    NUMERIC,
    confidence             NUMERIC,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (region_id, target_week_start_date, model_version)
);
CREATE INDEX idx_water_pred_region_week ON aquavision.water_predictions_weekly (region_id, target_week_start_date);
CREATE INDEX idx_water_pred_severity    ON aquavision.water_predictions_weekly (predicted_severity);

CREATE TABLE aquavision.water_alerts (
    id                       BIGSERIAL PRIMARY KEY,
    region_id                BIGINT NOT NULL REFERENCES shared.regions(id),
    week_start_date          DATE NOT NULL,
    alert_type               TEXT CHECK (alert_type IN ('WAI_CRITICAL','WAI_SEVERE','RAINFALL_DEFICIT','HIGH_ET')),
    severity                 TEXT CHECK (severity IN ('Critical','Severe','Warning')),
    wai_score                NUMERIC,
    rainfall_anomaly         NUMERIC,
    et_anomaly               NUMERIC,
    surface_water_change_pct NUMERIC,
    status                   TEXT DEFAULT 'New' CHECK (status IN ('New','Acknowledged','Resolved')),
    assigned_to_user_id      BIGINT REFERENCES shared.users(id),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at          TIMESTAMPTZ,
    resolved_at              TIMESTAMPTZ,
    notes                    TEXT
);
CREATE INDEX idx_water_alerts_region_status ON aquavision.water_alerts (region_id, status, created_at);
CREATE INDEX idx_water_alerts_severity      ON aquavision.water_alerts (severity);
CREATE INDEX idx_water_alerts_type          ON aquavision.water_alerts (alert_type);

CREATE TABLE aquavision.water_reports (
    id                    BIGSERIAL PRIMARY KEY,
    week_start_date       DATE NOT NULL,
    title                 TEXT NOT NULL,
    scope                 TEXT CHECK (scope IN ('National','Province','District')),
    region_id             BIGINT REFERENCES shared.regions(id),
    file_path             TEXT,
    generated_by_user_id  BIGINT REFERENCES shared.users(id),
    generated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                TEXT DEFAULT 'Success' CHECK (status IN ('Success','Failed'))
);

CREATE TABLE aquavision.water_thresholds (
    id             BIGSERIAL PRIMARY KEY,
    threshold_name TEXT NOT NULL UNIQUE,
    value          NUMERIC NOT NULL,
    description    TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Operating telemetry + logbook (WATER_OPERATOR console)
CREATE TABLE aquavision.asset_telemetry (
    id                 BIGSERIAL PRIMARY KEY,
    asset_id           BIGINT NOT NULL REFERENCES shared.assets(id),
    recorded_at        TIMESTAMPTZ NOT NULL,
    reservoir_level_m  NUMERIC,
    storage_pct        NUMERIC,
    inflow_cumecs     NUMERIC,
    outflow_cumecs    NUMERIC,
    discharge_cumecs  NUMERIC,
    data_status        TEXT CHECK (data_status IN ('Actual','Calibrated','Estimate','Missing')),
    source             TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_asset_telemetry_asset_time ON aquavision.asset_telemetry (asset_id, recorded_at);

CREATE TABLE aquavision.asset_operational_notes (
    id                 BIGSERIAL PRIMARY KEY,
    asset_id           BIGINT NOT NULL REFERENCES shared.assets(id),
    note               TEXT NOT NULL,
    created_by_user_id BIGINT NOT NULL REFERENCES shared.users(id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_asset_operational_notes_asset ON aquavision.asset_operational_notes (asset_id);

-- =====================================================================
-- CROP SCHEMA
-- =====================================================================

CREATE TABLE crop.crop_features (
    id             BIGSERIAL PRIMARY KEY,
    region_id      BIGINT NOT NULL REFERENCES shared.regions(id),
    crop_type      TEXT NOT NULL,
    season         TEXT NOT NULL,
    feature_date   DATE NOT NULL,
    ndvi           NUMERIC,
    evi            NUMERIC,
    savi           NUMERIC,
    rainfall_mm    NUMERIC,
    temperature_avg NUMERIC,
    soil_moisture  NUMERIC,
    wai_score      NUMERIC,
    metadata       JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_crop_features_region_crop_season ON crop.crop_features (region_id, crop_type, season);
CREATE INDEX idx_crop_features_date               ON crop.crop_features (feature_date);

CREATE TABLE crop.crop_models (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    crop_type   TEXT NOT NULL,
    algorithm   TEXT CHECK (algorithm IN ('RandomForest','XGBoost','LSTM')),
    version     TEXT NOT NULL,
    trained_at  TIMESTAMPTZ,
    metrics     JSONB,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE crop.crop_predictions (
    id             BIGSERIAL PRIMARY KEY,
    region_id      BIGINT NOT NULL REFERENCES shared.regions(id),
    crop_type      TEXT NOT NULL,
    season         TEXT NOT NULL,
    predicted_yield NUMERIC NOT NULL,
    yield_unit     TEXT DEFAULT 'tons/ha',
    risk_category  TEXT CHECK (risk_category IN ('Low','Moderate','High')),
    model_id       BIGINT REFERENCES crop.crop_models(id),
    confidence     NUMERIC,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_crop_pred_region_crop_season ON crop.crop_predictions (region_id, crop_type, season);
CREATE INDEX idx_crop_pred_risk               ON crop.crop_predictions (risk_category);

CREATE TABLE crop.crop_alerts (
    id                 BIGSERIAL PRIMARY KEY,
    region_id          BIGINT NOT NULL REFERENCES shared.regions(id),
    crop_type          TEXT NOT NULL,
    season             TEXT NOT NULL,
    risk_category      TEXT NOT NULL,
    trigger_reason     TEXT,
    status             TEXT DEFAULT 'New' CHECK (status IN ('New','Acknowledged','Resolved')),
    assigned_to_user_id BIGINT REFERENCES shared.users(id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at    TIMESTAMPTZ,
    resolved_at        TIMESTAMPTZ,
    notes              TEXT
);

CREATE TABLE crop.crop_reports (
    id                   BIGSERIAL PRIMARY KEY,
    season               TEXT NOT NULL,
    title                TEXT NOT NULL,
    scope                TEXT CHECK (scope IN ('National','Province','District')),
    region_id            BIGINT REFERENCES shared.regions(id),
    file_path            TEXT,
    generated_by_user_id BIGINT REFERENCES shared.users(id),
    generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    status               TEXT DEFAULT 'Success'
);

-- =====================================================================
-- GEO SCHEMA
-- =====================================================================

CREATE TABLE geo.geo_overlays (
    id                 BIGSERIAL PRIMARY KEY,
    region_id          BIGINT NOT NULL REFERENCES shared.regions(id),
    week_start_date    DATE NOT NULL,
    wai_score          NUMERIC,
    water_severity     TEXT,
    predicted_yield    NUMERIC,
    yield_risk         TEXT,
    combined_risk_score NUMERIC,
    geom               geometry(MultiPolygon, 4326) NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_geo_overlays_geom       ON geo.geo_overlays USING GIST (geom);
CREATE INDEX idx_geo_overlays_region_week ON geo.geo_overlays (region_id, week_start_date);
CREATE INDEX idx_geo_overlays_risk        ON geo.geo_overlays (combined_risk_score, yield_risk, water_severity);

CREATE TABLE geo.system_status (
    id                   BIGSERIAL PRIMARY KEY,
    component            TEXT NOT NULL,
    status               TEXT CHECK (status IN ('OK','Degraded','Failed')),
    last_successful_run  TIMESTAMPTZ,
    last_error_message   TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- SYSTEM SCHEMA
-- =====================================================================

CREATE TABLE system.pipeline_runs (
    id              BIGSERIAL PRIMARY KEY,
    pipeline_name   TEXT NOT NULL,
    week_start_date DATE,
    season          TEXT,
    status          TEXT CHECK (status IN ('QUEUED','RUNNING','SUCCESS','PARTIAL_SUCCESS','FAILED','CANCELLED')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    log_path        TEXT,
    error_message   TEXT,
    run_id          TEXT,
    trigger_type    TEXT,
    data_period     TEXT,
    records_read    INTEGER,
    records_written INTEGER,
    records_skipped INTEGER,
    warning_count   INTEGER,
    error_count     INTEGER,
    source_version  TEXT,
    code_version    TEXT,
    model_version   TEXT,
    error_summary   TEXT
);
CREATE INDEX ix_pipeline_runs_run_id ON system.pipeline_runs (run_id);

CREATE TABLE system.pipeline_run_stages (
    id              BIGSERIAL PRIMARY KEY,
    run_pk          BIGINT NOT NULL REFERENCES system.pipeline_runs(id),
    run_id          TEXT NOT NULL,
    stage_name      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('SUCCESS','PARTIAL_SUCCESS','FAILED','SKIPPED','CANCELLED')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    records_read    INTEGER,
    records_written INTEGER,
    records_skipped INTEGER,
    warning_count   INTEGER,
    error_count     INTEGER,
    log_path        TEXT,
    UNIQUE (run_id, stage_name)
);

CREATE TABLE system.audit_logs (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT REFERENCES shared.users(id),
    role          TEXT,
    module        TEXT,
    action        TEXT NOT NULL,
    entity_type   TEXT,
    entity_id     TEXT,
    resource_type TEXT,
    resource_id   TEXT,
    region_id     BIGINT,
    before_value  JSONB,
    after_value   JSONB,
    details       JSONB,
    result        TEXT,
    request_id    TEXT,
    ip_address    TEXT,
    user_agent    TEXT,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_logs_created_at ON system.audit_logs (timestamp);
CREATE INDEX ix_audit_logs_user       ON system.audit_logs (user_id);
CREATE INDEX ix_audit_logs_module     ON system.audit_logs (module);

-- =====================================================================
-- SEED DATA
-- =====================================================================

-- Roles
INSERT INTO shared.roles (name, description) VALUES
('admin', 'System administrator'),
('aquavision_analyst', 'Water monitoring analyst'),
('crop_analyst', 'Crop yield analyst'),
('geo_analyst', 'Geospatial analyst'),
('field_officer', 'Field operations officer'),
('viewer', 'Read-only viewer');

-- Role permissions (analyst: read + analyze + export - least privilege;
-- data ingestion is reserved for admin-level roles. Matches
-- migration 09_separate_analyst_permissions).
INSERT INTO shared.role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM shared.roles r, shared.permissions p
WHERE r.name = 'aquavision_analyst'
  AND p.name IN ('AQUAVISION_READ', 'AQUAVISION_ANALYZE',
                 'AQUAVISION_EXPORT');

-- Field officers (operator role) read, acknowledge/resolve alerts and add
-- logbook notes for their scoped assets.
INSERT INTO shared.role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM shared.roles r, shared.permissions p
WHERE r.name = 'field_officer'
  AND p.name IN ('AQUAVISION_READ', 'AQUAVISION_ACKNOWLEDGE_ALERT',
                 'AQUAVISION_ADD_NOTE');

-- Users (dummy bcrypt hashes; use auth/register in production)
-- Demo accounts: admin@ibcp.gov.pk/admin123, water@ibcp.gov.pk/water123,
-- field@ibcp.gov.pk/field123 (see README).
INSERT INTO shared.users (name, email, password_hash) VALUES
('Admin User', 'admin@ibcp.gov.pk', '$2b$12$kTNWCiUIAhlo61Ac1ASoeuWrg143yAghH0UMKX.D12O3gp.i4B3f2'),
('Aqua Analyst', 'water@ibcp.gov.pk', '$2b$12$j1.l8FtgitiR7BZl69mcyOW5NXanthEu/Vtik0By89zcwnHUWQ3pq'),
('Field Officer', 'field@ibcp.gov.pk', '$2b$12$n/RxH0M7swDkKqZAspuFS.uUYZu8uyM5oYdkFIzKUIonaktDUAl2K');
INSERT INTO shared.user_roles (user_id, role_id) VALUES (1, 1), (2, 2), (3, 5);

-- Explicit national access for the seeded accounts (fail-closed: without this
-- row the accounts would be denied all regional data).
INSERT INTO shared.user_region_scopes (user_id, scope_type, is_active) VALUES
(1, 'NATIONAL', TRUE),
(2, 'NATIONAL', TRUE),
(3, 'NATIONAL', TRUE);

-- Permissions
INSERT INTO shared.permissions (name, description) VALUES
('AQUAVISION_READ', 'Read water indicators and predictions'),
('AQUAVISION_MANAGE_DATA', 'Ingest water data'),
('AQUAVISION_ACKNOWLEDGE_ALERT', 'Acknowledge/resolve water alerts'),
('AQUAVISION_CONFIGURE', 'Configure water thresholds'),
('AQUAVISION_ANALYZE', 'Run water analytics'),
('AQUAVISION_EXPORT', 'Export water data'),
('AQUAVISION_ADD_NOTE', 'Add operational water notes'),
('AQUAVISION_APPROVE_REPORT', 'Approve water reports'),
('AQUAVISION_MANAGE_USERS', 'Manage operational users'),
('CROP_READ', 'Read crop data'),
('CROP_TRAIN_MODEL', 'Train crop yield models'),
('GEOVISION_READ', 'Read geo overlays'),
('SYSTEM_ADMIN', 'System configuration');

-- Regions (provinces + districts) with simplified point-based polygons
INSERT INTO shared.regions (name, code, type, parent_region_id, geom) VALUES
('Punjab', 'PB', 'province', NULL, ST_GeomFromText('POLYGON((70 28, 75 28, 75 34, 70 34, 70 28))', 4326)),
('Sindh', 'SD', 'province', NULL, ST_GeomFromText('POLYGON((66 23, 71 23, 71 28, 66 28, 66 23))', 4326)),
('Khyber Pakhtunkhwa', 'KP', 'province', NULL, ST_GeomFromText('POLYGON((70 32, 74 32, 74 36, 70 36, 70 32))', 4326)),
('Balochistan', 'BL', 'province', NULL, ST_GeomFromText('POLYGON((62 25, 70 25, 70 31, 62 31, 62 25))', 4326)),
('Lahore', 'PB-LHR', 'district', 1, ST_GeomFromText('POLYGON((74.0 31.2, 74.6 31.2, 74.6 31.8, 74.0 31.8, 74.0 31.2))', 4326)),
('Multan', 'PB-MTN', 'district', 1, ST_GeomFromText('POLYGON((71.2 29.9, 71.9 29.9, 71.9 30.5, 71.2 30.5, 71.2 29.9))', 4326)),
('Faisalabad', 'PB-FSD', 'district', 1, ST_GeomFromText('POLYGON((72.8 31.2, 73.4 31.2, 73.4 31.7, 72.8 31.7, 72.8 31.2))', 4326)),
('Bahawalpur', 'PB-BWP', 'district', 1, ST_GeomFromText('POLYGON((71.3 28.9, 72.2 28.9, 72.2 29.7, 71.3 29.7, 71.3 28.9))', 4326)),
('Sargodha', 'PB-SGD', 'district', 1, ST_GeomFromText('POLYGON((72.3 31.7, 73.1 31.7, 73.1 32.4, 72.3 32.4, 72.3 31.7))', 4326)),
('Hyderabad', 'SD-HYD', 'district', 2, ST_GeomFromText('POLYGON((68.0 25.0, 68.8 25.0, 68.8 25.8, 68.0 25.8, 68.0 25.0))', 4326)),
('Sukkur', 'SD-SKR', 'district', 2, ST_GeomFromText('POLYGON((68.5 27.4, 69.4 27.4, 69.4 28.1, 68.5 28.1, 68.5 27.4))', 4326)),
('Larkana', 'SD-LRK', 'district', 2, ST_GeomFromText('POLYGON((67.9 27.2, 68.7 27.2, 68.7 27.9, 67.9 27.9, 67.9 27.2))', 4326)),
('Mirpurkhas', 'SD-MPK', 'district', 2, ST_GeomFromText('POLYGON((68.7 25.2, 69.4 25.2, 69.4 25.8, 68.7 25.8, 68.7 25.2))', 4326)),
('Peshawar', 'KP-PSW', 'district', 3, ST_GeomFromText('POLYGON((71.4 33.9, 71.8 33.9, 71.8 34.2, 71.4 34.2, 71.4 33.9))', 4326)),
('Mardan', 'KP-MRD', 'district', 3, ST_GeomFromText('POLYGON((71.9 34.1, 72.2 34.1, 72.2 34.4, 71.9 34.4, 71.9 34.1))', 4326)),
('Swat', 'KP-SWT', 'district', 3, ST_GeomFromText('POLYGON((72.1 34.5, 72.6 34.5, 72.6 35.1, 72.1 35.1, 72.1 34.5))', 4326)),
('Quetta', 'BL-QTA', 'district', 4, ST_GeomFromText('POLYGON((66.8 29.9, 67.3 29.9, 67.3 30.4, 66.8 30.4, 66.8 29.9))', 4326)),
('Khuzdar', 'BL-KZD', 'district', 4, ST_GeomFromText('POLYGON((66.3 27.5, 67.0 27.5, 67.0 28.1, 66.3 28.1, 66.3 27.5))', 4326));

-- Assets
INSERT INTO shared.assets (name, asset_type, region_id, geom, source) VALUES
('Tarbela Dam', 'dam', 3, ST_GeomFromText('POLYGON((72.60 34.08, 72.72 34.10, 72.72 34.12, 72.60 34.10, 72.60 34.08))', 4326), 'HydroLAKES'),
('Mangla Dam', 'dam', 1, ST_GeomFromText('POLYGON((73.58 33.12, 73.70 33.14, 73.70 33.16, 73.58 33.14, 73.58 33.12))', 4326), 'HydroLAKES'),
('Chashma Barrage', 'barrage', 1, ST_GeomFromText('POLYGON((71.34 32.41, 71.42 32.42, 71.42 32.44, 71.34 32.43, 71.34 32.41))', 4326), 'OSM'),
('Sukkur Barrage', 'barrage', 2, ST_GeomFromText('POLYGON((68.86 27.68, 68.91 27.70, 68.91 27.72, 68.86 27.70, 68.86 27.68))', 4326), 'OSM'),
('Indus River', 'river', 2, ST_GeomFromText('POLYGON((68.10 24.35, 68.20 24.40, 68.18 24.45, 68.08 24.40, 68.10 24.35))', 4326), 'HydroRIVERS'),
('Jhelum River', 'river', 1, ST_GeomFromText('POLYGON((72.28 31.69, 72.36 31.72, 72.34 31.77, 72.26 31.74, 72.28 31.69))', 4326), 'HydroRIVERS'),
('Lower Chenab Canal', 'canal', 1, ST_GeomFromText('POLYGON((73.03 31.40, 73.12 31.43, 73.12 31.45, 73.03 31.42, 73.03 31.40))', 4326), 'OSM'),
('Hub Dam', 'reservoir', 2, ST_GeomFromText('POLYGON((67.04 25.22, 67.12 25.25, 67.12 25.28, 67.04 25.25, 67.04 25.22))', 4326), 'HydroLAKES');

-- Thresholds
INSERT INTO aquavision.water_thresholds (threshold_name, value, description) VALUES
('wai_critical_min', 25.0, 'WAI below this triggers Critical severity'),
('wai_severe_min', 40.0, 'WAI below this triggers Severe severity'),
('wai_stressed_min', 55.0, 'WAI below this triggers Stressed severity'),
('rainfall_deficit_pct', -30.0, 'Rainfall anomaly below this triggers RAINFALL_DEFICIT'),
('et_anomaly_high', 25.0, 'ET anomaly above this triggers HIGH_ET');

-- System status
INSERT INTO geo.system_status (component, status, last_successful_run) VALUES
('aquavision_etl', 'OK', now()),
('crop_etl', 'OK', now()),
('geovision_service', 'OK', now()),
('api_gateway', 'OK', now());
