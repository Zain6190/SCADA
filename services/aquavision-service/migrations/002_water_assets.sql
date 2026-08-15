-- Migration: Create water asset observation tables
-- Run: docker exec -i ibcp-postgis psql -U postgres -d ibcp_scada < migrations/002_water_assets.sql

-- 1. Water sources (IRSA, PMD, GEE, etc.)
CREATE TABLE IF NOT EXISTS aquavision.water_sources (
    id BIGSERIAL PRIMARY KEY,
    authority TEXT NOT NULL UNIQUE,
    source_url TEXT,
    source_type TEXT NOT NULL,       -- PDF_DAILY_REPORT, CSV, API, SATELLITE
    update_frequency TEXT,            -- DAILY, WEEKLY, MONTHLY
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Canonical water asset registry
CREATE TABLE IF NOT EXISTS aquavision.water_assets (
    id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    asset_type TEXT NOT NULL,         -- reservoir, barrage, river_station, canal, lake
    river TEXT,
    province TEXT,
    district TEXT,
    latitude NUMERIC,
    longitude NUMERIC,
    capacity_maf NUMERIC,
    normal_level_ft NUMERIC,
    dead_level_ft NUMERIC,
    warning_level_ft NUMERIC,
    critical_level_ft NUMERIC,
    source_authority TEXT,
    source_identifier TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Raw source records (immutable archive)
CREATE TABLE IF NOT EXISTS aquavision.raw_source_records (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES aquavision.water_sources(id),
    retrieved_at TIMESTAMPTZ NOT NULL,
    source_date DATE NOT NULL,
    file_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,       -- SHA-256
    raw_content BYTEA NOT NULL,
    parser_version TEXT NOT NULL,
    record_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Normalized water observations
CREATE TABLE IF NOT EXISTS aquavision.water_observations (
    id BIGSERIAL PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    source_id BIGINT NOT NULL REFERENCES aquavision.water_sources(id),
    observed_at TIMESTAMPTZ NOT NULL,
    water_level_ft NUMERIC,
    storage_volume NUMERIC,
    storage_percent NUMERIC,
    inflow_cusecs NUMERIC,
    outflow_cusecs NUMERIC,
    discharge_cusecs NUMERIC,
    upstream_discharge_cusecs NUMERIC,
    downstream_discharge_cusecs NUMERIC,
    unit TEXT,                         -- cusecs, feet, MAF
    data_status TEXT NOT NULL DEFAULT 'OBSERVED',  -- OBSERVED|ESTIMATED|FORECAST|SYNTHETIC|MISSING
    quality_flag TEXT,                 -- OFFICIAL_DAILY_REPORT, FFD_BULLETIN, etc.
    raw_record_id BIGINT REFERENCES aquavision.raw_source_records(id),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (asset_id, observed_at, source_id)
);

-- 5. Model forecasts per asset
CREATE TABLE IF NOT EXISTS aquavision.water_asset_forecasts (
    id BIGSERIAL PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    generated_at TIMESTAMPTZ NOT NULL,
    target_time TIMESTAMPTZ NOT NULL,
    predicted_level_ft NUMERIC,
    predicted_storage NUMERIC,
    predicted_inflow NUMERIC,
    predicted_outflow NUMERIC,
    predicted_discharge NUMERIC,
    confidence NUMERIC,
    model_version TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_obs_asset_time ON aquavision.water_observations (asset_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_source_date ON aquavision.raw_source_records (source_id, source_date DESC);
CREATE INDEX IF NOT EXISTS idx_forecast_asset ON aquavision.water_asset_forecasts (asset_id, target_time);
CREATE INDEX IF NOT EXISTS idx_asset_type ON aquavision.water_assets (asset_type);
