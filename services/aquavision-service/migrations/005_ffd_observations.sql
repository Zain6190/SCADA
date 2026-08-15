-- migrations/005_ffd_observations.sql
-- FFD/PMD flood bulletin observations.

CREATE TABLE IF NOT EXISTS aquavision.water_ffd_observations (
    id              SERIAL PRIMARY KEY,
    asset_id        INT REFERENCES aquavision.water_assets(id),
    source_id       INT REFERENCES aquavision.water_sources(id),
    
    -- Station info
    station_name    TEXT NOT NULL,
    river_name      TEXT,
    
    -- Readings
    observed_at     DATE NOT NULL,
    gauge_level_ft  NUMERIC,
    discharge_cusecs NUMERIC,
    
    -- FFD-specific
    flood_status    TEXT DEFAULT 'NORMAL',
    -- LOW | MEDIUM | HIGH | VERY_HIGH | EXCEPTIONALLY_HIGH
    forecast_trend  TEXT DEFAULT 'STEADY',
    -- RISING | FALLING | STEADY
    
    -- Source
    bulletin_url    TEXT,
    raw_html        TEXT,
    content_hash    TEXT,
    
    -- Metadata
    data_status     TEXT DEFAULT 'OBSERVED',
    quality_flag    TEXT DEFAULT 'FFD_BULLETIN',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(asset_id, observed_at, source_id)
);

CREATE INDEX IF NOT EXISTS idx_ffd_asset_date 
    ON aquavision.water_ffd_observations(asset_id, observed_at DESC);

-- Add FFD source to water_sources if not exists
INSERT INTO aquavision.water_sources (authority, source_url, source_type, update_frequency, description)
VALUES ('FFD/PMD', 'https://ffd.pmd.gov.pk', 'HTML_BULLETIN', 'DAILY', 'Pakistan Meteorological Department - Flood Forecasting Division')
ON CONFLICT (authority) DO NOTHING;
