-- migrations/003_threshold_alerts.sql
-- Asset-specific thresholds + operational alert system.

-- ============================================================
-- water_asset_thresholds: per-asset threshold rules
-- ============================================================
CREATE TABLE IF NOT EXISTS aquavision.water_asset_thresholds (
    id              SERIAL PRIMARY KEY,
    asset_id        INT NOT NULL REFERENCES aquavision.water_assets(id) ON DELETE CASCADE,
    
    -- Level thresholds (reservoirs)
    warning_level_ft    NUMERIC,
    danger_level_ft     NUMERIC,
    critical_level_ft   NUMERIC,
    
    -- Inflow thresholds (cusecs)
    warning_inflow      NUMERIC,
    danger_inflow       NUMERIC,
    
    -- Discharge thresholds (cusecs) - river stations
    warning_discharge   NUMERIC,
    danger_discharge    NUMERIC,
    
    -- Rate of change thresholds
    -- e.g., level rise > 0.5 ft in 6 hours = WATCH
    level_rise_watch_6h     NUMERIC,  -- ft
    level_rise_warning_6h   NUMERIC,  -- ft
    level_rise_critical_6h  NUMERIC,  -- ft
    
    inflow_rise_watch_6h    NUMERIC,  -- cusecs
    inflow_rise_warning_6h  NUMERIC,  -- cusecs
    
    -- Data staleness
    stale_hours_warning     INT DEFAULT 48,  -- hours without data = WATCH
    stale_hours_critical    INT DEFAULT 72,  -- hours without data = CRITICAL
    
    -- Metadata
    is_active       BOOLEAN DEFAULT TRUE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(asset_id)
);

-- ============================================================
-- water_operational_alerts: real-time operational alerts
-- ============================================================
CREATE TABLE IF NOT EXISTS aquavision.water_operational_alerts (
    id              SERIAL PRIMARY KEY,
    asset_id        INT NOT NULL REFERENCES aquavision.water_assets(id),
    
    -- Alert identity
    alert_type      TEXT NOT NULL,
    -- HIGH_INFLOW, RISING_LEVEL, RAPID_RISE, LEVEL_ABOVE_WARNING,
    -- LEVEL_ABOVE_DANGER, LEVEL_ABOVE_CRITICAL, HIGH_INFLOW_LOW_OUTFLOW,
    -- FORECAST_DANGER_24H, FORECAST_DANGER_7D, DATA_STALE, FLOOD_FORECAST
    
    severity        TEXT NOT NULL DEFAULT 'WATCH',
    -- NORMAL, WATCH, ADVISORY, WARNING, CRITICAL
    
    -- Triggering observation
    observation_id  INT REFERENCES aquavision.water_observations(id),
    
    -- Alert details
    triggered_value NUMERIC,       -- the value that triggered the alert
    threshold_value NUMERIC,       -- the threshold that was exceeded
    message         TEXT NOT NULL, -- human-readable description
    
    -- Current readings at time of alert
    reading_level_ft        NUMERIC,
    reading_inflow_cusecs   NUMERIC,
    reading_outflow_cusecs  NUMERIC,
    reading_discharge_cusecs NUMERIC,
    rate_of_change_ft_6h    NUMERIC,
    
    -- Status tracking
    status          TEXT NOT NULL DEFAULT 'NEW',
    -- NEW, ACKNOWLEDGED, INVESTIGATING, ESCALATED, ACTION_REQUIRED,
    -- WAITING_FOR_VERIFICATION, RESOLVED, FALSE_OR_INVALID_DATA
    
    -- Workflow
    assigned_to     TEXT,          -- operator/supervisor name
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    resolved_by     TEXT,
    resolved_at     TIMESTAMPTZ,
    
    -- Resolution
    resolution      TEXT,          -- FALSE_POSITIVE, TRUE_POSITIVE, DATA_ERROR, etc.
    
    -- Audit
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_alerts_active 
    ON aquavision.water_operational_alerts(severity, status) 
    WHERE status IN ('NEW', 'ACKNOWLEDGED', 'INVESTIGATING');

CREATE INDEX IF NOT EXISTS idx_alerts_asset 
    ON aquavision.water_operational_alerts(asset_id, created_at DESC);

-- ============================================================
-- water_alert_audit_log: full audit trail
-- ============================================================
CREATE TABLE IF NOT EXISTS aquavision.water_alert_audit_log (
    id              SERIAL PRIMARY KEY,
    alert_id        INT NOT NULL REFERENCES aquavision.water_operational_alerts(id) ON DELETE CASCADE,
    
    action          TEXT NOT NULL,  -- CREATED, ACKNOWLEDGED, INVESTIGATED, ESCALATED, RESOLVED, etc.
    performed_by    TEXT NOT NULL,
    performed_at    TIMESTAMPTZ DEFAULT NOW(),
    
    old_status      TEXT,
    new_status      TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_alert 
    ON aquavision.water_alert_audit_log(alert_id, performed_at DESC);

-- ============================================================
-- water_downstream_impacts: downstream risk mapping
-- ============================================================
CREATE TABLE IF NOT EXISTS aquavision.water_downstream_impacts (
    id              SERIAL PRIMARY KEY,
    
    source_asset_id     INT NOT NULL REFERENCES aquavision.water_assets(id),
    downstream_asset_id INT REFERENCES aquavision.water_assets(id),
    
    -- Travel time estimates
    travel_time_hours_min   NUMERIC,
    travel_time_hours_max   NUMERIC,
    travel_time_hours_expected NUMERIC,
    distance_km             NUMERIC,
    
    -- Affected area
    affected_population_est INTEGER,
    affected_village_count  INTEGER,
    affected_town_count     INTEGER,
    affected_city_count     INTEGER,
    
    -- Critical infrastructure
    bridges_count   INTEGER DEFAULT 0,
    hospitals_count INTEGER DEFAULT 0,
    roads_km        NUMERIC DEFAULT 0,
    
    -- GIS (optional, for map display)
    impact_zone_geom GEOMETRY(POLYGON, 4326),
    
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
