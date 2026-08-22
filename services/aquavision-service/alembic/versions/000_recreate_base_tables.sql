-- Rebuild all aquavision base tables (migrations 001-005 were lost with the Docker volume)
-- This recreates everything from the ORM models so Alembic 006+ can run cleanly.

-- water_sources
CREATE TABLE IF NOT EXISTS aquavision.water_sources (
    id BIGSERIAL PRIMARY KEY,
    authority TEXT NOT NULL UNIQUE,
    source_url TEXT,
    source_type TEXT NOT NULL,
    update_frequency TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- water_assets
CREATE TABLE IF NOT EXISTS aquavision.water_assets (
    id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    asset_type TEXT NOT NULL,
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
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- raw_source_records
CREATE TABLE IF NOT EXISTS aquavision.raw_source_records (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES aquavision.water_sources(id),
    retrieved_at TIMESTAMPTZ NOT NULL,
    source_date DATE NOT NULL,
    file_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    raw_content BYTEA NOT NULL,
    parser_version TEXT NOT NULL,
    record_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- water_observations
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
    unit TEXT,
    data_status TEXT NOT NULL DEFAULT 'OBSERVED_OFFICIAL',
    data_origin TEXT NOT NULL DEFAULT 'REAL',
    quality_status TEXT NOT NULL DEFAULT 'VALID',
    quality_flag TEXT,
    raw_record_id BIGINT REFERENCES aquavision.raw_source_records(id),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    source_authority TEXT,
    source_publication_time TIMESTAMPTZ,
    source_parser_version TEXT,
    source_content_hash TEXT,
    source_priority INTEGER DEFAULT 3,
    UNIQUE (asset_id, observed_at, source_id)
);

CREATE INDEX IF NOT EXISTS idx_obs_asset_time ON aquavision.water_observations (asset_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_source ON aquavision.water_observations (source_id);
CREATE INDEX IF NOT EXISTS idx_obs_data_origin ON aquavision.water_observations (data_origin);

-- water_asset_forecasts
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forecast_asset ON aquavision.water_asset_forecasts (asset_id, target_time DESC);

-- water_asset_thresholds
CREATE TABLE IF NOT EXISTS aquavision.water_asset_thresholds (
    id BIGSERIAL PRIMARY KEY,
    asset_id BIGINT NOT NULL UNIQUE REFERENCES aquavision.water_assets(id),
    warning_level_ft NUMERIC,
    danger_level_ft NUMERIC,
    critical_level_ft NUMERIC,
    warning_inflow NUMERIC,
    danger_inflow NUMERIC,
    warning_discharge NUMERIC,
    danger_discharge NUMERIC,
    level_rise_watch_6h NUMERIC,
    level_rise_warning_6h NUMERIC,
    level_rise_critical_6h NUMERIC,
    inflow_rise_watch_6h NUMERIC,
    inflow_rise_warning_6h NUMERIC,
    stale_hours_warning INTEGER DEFAULT 48,
    stale_hours_critical INTEGER DEFAULT 72,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- water_alert_episodes (must exist before operational_alerts FK)
CREATE TABLE IF NOT EXISTS aquavision.water_alert_episodes (
    id BIGSERIAL PRIMARY KEY,
    episode_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'WATCH',
    status TEXT NOT NULL DEFAULT 'OPEN',
    triggered_by_asset_id BIGINT REFERENCES aquavision.water_assets(id),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- water_operational_alerts
CREATE TABLE IF NOT EXISTS aquavision.water_operational_alerts (
    id BIGSERIAL PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'WATCH',
    alert_source TEXT NOT NULL DEFAULT 'RULE',
    alert_domain TEXT NOT NULL DEFAULT 'OPERATIONAL',
    rule_version TEXT,
    model_version TEXT,
    episode_id BIGINT REFERENCES aquavision.water_alert_episodes(id),
    observation_id BIGINT REFERENCES aquavision.water_observations(id),
    triggered_value NUMERIC,
    threshold_value NUMERIC,
    message TEXT NOT NULL,
    reading_level_ft NUMERIC,
    reading_inflow_cusecs NUMERIC,
    reading_outflow_cusecs NUMERIC,
    reading_discharge_cusecs NUMERIC,
    rate_of_change_ft_6h NUMERIC,
    status TEXT NOT NULL DEFAULT 'NEW',
    assigned_to TEXT,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    escalated_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolved_at TIMESTAMPTZ,
    resolution TEXT,
    notes TEXT,
    downstream_impact_summary TEXT,
    downstream_population_exposed BIGINT,
    downstream_bridges_at_risk INTEGER,
    downstream_hospitals_at_risk INTEGER,
    downstream_furthest_asset TEXT,
    downstream_furthest_arrival_hours NUMERIC,
    flood_probability NUMERIC,
    flood_severity TEXT,
    flood_confidence TEXT,
    flood_recommendation TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opalert_asset ON aquavision.water_operational_alerts (asset_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opalert_status ON aquavision.water_operational_alerts (status, severity);
CREATE INDEX IF NOT EXISTS idx_opalert_episode ON aquavision.water_operational_alerts (episode_id);

-- water_alert_audit_log
CREATE TABLE IF NOT EXISTS aquavision.water_alert_audit_log (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES aquavision.water_operational_alerts(id),
    action TEXT NOT NULL,
    performed_by TEXT NOT NULL,
    performed_at TIMESTAMPTZ DEFAULT NOW(),
    old_status TEXT,
    new_status TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_alert ON aquavision.water_alert_audit_log (alert_id, performed_at DESC);

-- water_downstream_impacts
CREATE TABLE IF NOT EXISTS aquavision.water_downstream_impacts (
    id BIGSERIAL PRIMARY KEY,
    source_asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    downstream_asset_id BIGINT REFERENCES aquavision.water_assets(id),
    travel_time_hours_min NUMERIC,
    travel_time_hours_max NUMERIC,
    travel_time_hours_expected NUMERIC,
    distance_km NUMERIC,
    affected_population_est INTEGER,
    affected_village_count INTEGER,
    affected_town_count INTEGER,
    affected_city_count INTEGER,
    bridges_count INTEGER DEFAULT 0,
    hospitals_count INTEGER DEFAULT 0,
    roads_km NUMERIC DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_impact_source ON aquavision.water_downstream_impacts (source_asset_id);

-- water_river_network
CREATE TABLE IF NOT EXISTS aquavision.water_river_network (
    id BIGSERIAL PRIMARY KEY,
    river_name TEXT NOT NULL,
    upstream_asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    downstream_asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    segment_order INTEGER NOT NULL,
    distance_km NUMERIC,
    source_name TEXT DEFAULT 'IRSA/PDMA',
    source_url TEXT,
    verified_at TIMESTAMPTZ,
    verified_by TEXT,
    status TEXT DEFAULT 'PLANNING_ESTIMATE',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_river_upstream ON aquavision.water_river_network (upstream_asset_id);
CREATE INDEX IF NOT EXISTS idx_river_downstream ON aquavision.water_river_network (downstream_asset_id);

-- water_travel_time_models
CREATE TABLE IF NOT EXISTS aquavision.water_travel_time_models (
    id BIGSERIAL PRIMARY KEY,
    river_segment_id BIGINT NOT NULL REFERENCES aquavision.water_river_network(id),
    flow_min_cusecs NUMERIC NOT NULL,
    flow_max_cusecs NUMERIC NOT NULL,
    travel_time_min_hours NUMERIC NOT NULL,
    travel_time_max_hours NUMERIC NOT NULL,
    travel_time_expected_hours NUMERIC NOT NULL,
    method TEXT DEFAULT 'Historical flood-wave observation',
    source_name TEXT DEFAULT 'IRSA/PDMA',
    calibration_event TEXT,
    confidence TEXT DEFAULT 'MEDIUM',
    effective_from DATE,
    effective_to DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_travel_segment ON aquavision.water_travel_time_models (river_segment_id);

-- water_ffd_observations
CREATE TABLE IF NOT EXISTS aquavision.water_ffd_observations (
    id BIGSERIAL PRIMARY KEY,
    asset_id BIGINT REFERENCES aquavision.water_assets(id),
    source_id BIGINT REFERENCES aquavision.water_sources(id),
    station_name TEXT NOT NULL,
    river_name TEXT,
    observed_at DATE NOT NULL,
    gauge_level_ft NUMERIC,
    discharge_cusecs NUMERIC,
    flood_status TEXT DEFAULT 'NORMAL',
    forecast_trend TEXT DEFAULT 'STEADY',
    bulletin_url TEXT,
    raw_html TEXT,
    content_hash TEXT,
    data_status TEXT DEFAULT 'OBSERVED',
    quality_flag TEXT DEFAULT 'FFD_BULLETIN',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (asset_id, observed_at, source_id)
);

CREATE INDEX IF NOT EXISTS idx_ffd_asset_date ON aquavision.water_ffd_observations (asset_id, observed_at DESC);
