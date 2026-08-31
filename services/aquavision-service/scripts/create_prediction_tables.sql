-- ============================================================
-- Migration: Prediction Persistence & Model Lifecycle Tables
-- Schema: aquavision
-- ============================================================

-- 1. water.predictions — Store every flood forecast
CREATE TABLE IF NOT EXISTS aquavision.water_predictions (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    horizon INTEGER NOT NULL,               -- 7, 14, 30 days
    predicted_value DOUBLE PRECISION,        -- predicted inflow/level (cusecs or ft)
    predicted_lower DOUBLE PRECISION,        -- lower bound of prediction interval
    predicted_upper DOUBLE PRECISION,        -- upper bound of prediction interval
    risk_score INTEGER,                      -- 0-100
    risk_category VARCHAR(20),               -- NORMAL, WATCH, WARNING, CRITICAL
    exceeds_warning BOOLEAN DEFAULT false,
    exceeds_danger BOOLEAN DEFAULT false,
    model_version VARCHAR(50),               -- e.g. 'xgb-flood-v1.2'
    model_type VARCHAR(30) DEFAULT 'flood_predictor',  -- flood_predictor, high_flow, classifier
    features_used JSONB DEFAULT '[]'::jsonb,  -- list of feature names used
    feature_importance JSONB DEFAULT '{}'::jsonb,  -- top features with importance scores
    confidence DOUBLE PRECISION,             -- prediction confidence (0-1)
    valid_from TIMESTAMPTZ NOT NULL,         -- prediction validity start
    valid_to TIMESTAMPTZ NOT NULL,           -- prediction validity end
    generated_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_water_predictions_asset ON aquavision.water_predictions(asset_id);
CREATE INDEX IF NOT EXISTS idx_water_predictions_horizon ON aquavision.water_predictions(horizon);
CREATE INDEX IF NOT EXISTS idx_water_predictions_valid ON aquavision.water_predictions(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_water_predictions_generated ON aquavision.water_predictions(generated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_water_predictions_unique ON aquavision.water_predictions(asset_id, horizon, valid_from);


-- 2. aquavision.model_versions — Champion/Challenger tracking
CREATE TABLE IF NOT EXISTS aquavision.model_versions (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    model_type VARCHAR(30) NOT NULL,         -- flood_predictor, high_flow, classifier, wai
    horizon INTEGER,                         -- 7, 14, 30, NULL for classifiers
    version VARCHAR(50) NOT NULL,            -- e.g. 'xgb-flood-v1.2'
    status VARCHAR(20) NOT NULL DEFAULT 'EXPERIMENTAL',  -- EXPERIMENTAL, SHADOW, CHAMPION, RETIRED
    metrics JSONB DEFAULT '{}'::jsonb,       -- {r2, mae, rmse, mape, score, ...}
    hyperparams JSONB DEFAULT '{}'::jsonb,   -- model hyperparameters
    features JSONB DEFAULT '[]'::jsonb,      -- list of feature names
    training_samples INTEGER,
    training_window VARCHAR(50),             -- e.g. '3 years'
    trained_at TIMESTAMPTZ,
    promoted_at TIMESTAMPTZ,                 -- when promoted to CHAMPION
    retired_at TIMESTAMPTZ,                  -- when retired
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_versions_asset ON aquavision.model_versions(asset_id);
CREATE INDEX IF NOT EXISTS idx_model_versions_status ON aquavision.model_versions(status);
CREATE INDEX IF NOT EXISTS idx_model_versions_type ON aquavision.model_versions(model_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_versions_unique ON aquavision.model_versions(asset_id, model_type, horizon, version);


-- 3. aquavision.prediction_accuracy — Track actual vs predicted
CREATE TABLE IF NOT EXISTS aquavision.prediction_accuracy (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    horizon INTEGER NOT NULL,
    prediction_id INTEGER REFERENCES aquavision.water_predictions(id),
    predicted_value DOUBLE PRECISION,
    actual_value DOUBLE PRECISION,
    error DOUBLE PRECISION,                  -- actual - predicted
    abs_error DOUBLE PRECISION,
    squared_error DOUBLE PRECISION,
    pct_error DOUBLE PRECISION,              -- |error| / actual * 100
    predicted_at TIMESTAMPTZ,               -- when prediction was made
    actual_at TIMESTAMPTZ,                  -- when actual was observed
    model_version VARCHAR(50),
    matched_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prediction_accuracy_asset ON aquavision.prediction_accuracy(asset_id);
CREATE INDEX IF NOT EXISTS idx_prediction_accuracy_date ON aquavision.prediction_accuracy(actual_at DESC);


-- 4. aquavision.feature_drift — PSI and drift metrics per feature
CREATE TABLE IF NOT EXISTS aquavision.feature_drift (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    feature_name VARCHAR(100) NOT NULL,
    psi DOUBLE PRECISION,                    -- Population Stability Index
    ks_statistic DOUBLE PRECISION,           -- Kolmogorov-Smirnov statistic
    mean_current DOUBLE PRECISION,           -- mean of recent data
    mean_baseline DOUBLE PRECISION,          -- mean of training data
    std_current DOUBLE PRECISION,
    std_baseline DOUBLE PRECISION,
    drift_status VARCHAR(20) DEFAULT 'STABLE',  -- STABLE, MODERATE, SIGNIFICANT
    evaluation_window VARCHAR(20),           -- '7d', '30d'
    computed_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feature_drift_asset ON aquavision.feature_drift(asset_id);
CREATE INDEX IF NOT EXISTS idx_feature_drift_status ON aquavision.feature_drift(drift_status);
CREATE INDEX IF NOT EXISTS idx_feature_drift_date ON aquavision.feature_drift(computed_at DESC);


-- 5. aquavision.prediction_logs — Audit trail for all prediction runs
CREATE TABLE IF NOT EXISTS aquavision.prediction_logs (
    id SERIAL PRIMARY KEY,
    run_type VARCHAR(30) NOT NULL,           -- SCHEDULED, MANUAL, SHADOW
    assets_predicted INTEGER DEFAULT 0,
    assets_failed INTEGER DEFAULT 0,
    predictions_written INTEGER DEFAULT 0,
    duration_seconds FLOAT,
    model_versions JSONB DEFAULT '{}'::jsonb,  -- {asset_id: version}
    errors JSONB DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'RUNNING'     -- RUNNING, SUCCESS, FAILED
);

CREATE INDEX IF NOT EXISTS idx_prediction_logs_date ON aquavision.prediction_logs(started_at DESC);
