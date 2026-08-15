-- migrations/004_river_network.sql
-- River network + travel time models for downstream impact mapping.

-- ============================================================
-- water_river_network: river segments connecting assets
-- ============================================================
CREATE TABLE IF NOT EXISTS aquavision.water_river_network (
    id              SERIAL PRIMARY KEY,
    river_name      TEXT NOT NULL,
    upstream_asset_id   INT NOT NULL REFERENCES aquavision.water_assets(id),
    downstream_asset_id INT NOT NULL REFERENCES aquavision.water_assets(id),
    segment_order   INT NOT NULL,
    distance_km     NUMERIC,
    
    -- Source provenance
    source_name     TEXT DEFAULT 'IRSA/PDMA',
    source_url      TEXT,
    verified_at     TIMESTAMPTZ,
    verified_by     TEXT,
    status          TEXT DEFAULT 'PLANNING_ESTIMATE',
    -- PLANNING_ESTIMATE | CALIBRATED | VERIFIED
    
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(upstream_asset_id, downstream_asset_id)
);

-- ============================================================
-- water_travel_time_models: flow-band-based travel times
-- ============================================================
CREATE TABLE IF NOT EXISTS aquavision.water_travel_time_models (
    id                  SERIAL PRIMARY KEY,
    river_segment_id    INT NOT NULL REFERENCES aquavision.water_river_network(id),
    
    -- Flow band
    flow_min_cusecs     NUMERIC NOT NULL,
    flow_max_cusecs     NUMERIC NOT NULL,
    
    -- Travel time estimates
    travel_time_min_hours    NUMERIC NOT NULL,
    travel_time_max_hours    NUMERIC NOT NULL,
    travel_time_expected_hours NUMERIC NOT NULL,
    
    -- Confidence
    method              TEXT DEFAULT 'Historical flood-wave observation',
    source_name         TEXT DEFAULT 'IRSA/PDMA',
    calibration_event   TEXT,
    confidence          TEXT DEFAULT 'MEDIUM',
    -- LOW | MEDIUM | HIGH
    
    effective_from      DATE,
    effective_to        DATE,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_travel_time_segment 
    ON aquavision.water_travel_time_models(river_segment_id);
