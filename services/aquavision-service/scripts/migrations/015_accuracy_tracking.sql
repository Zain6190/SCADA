-- Migration 015: Add accuracy tracking columns + materialized view
-- Adds: within_interval, direction_correct, matched_column, data_origin to prediction_accuracy
-- Creates: materialized view for fast API reads

BEGIN;

-- Add new columns to prediction_accuracy
ALTER TABLE aquavision.prediction_accuracy
    ADD COLUMN IF NOT EXISTS within_interval BOOLEAN,
    ADD COLUMN IF NOT EXISTS direction_correct BOOLEAN,
    ADD COLUMN IF NOT EXISTS matched_column VARCHAR(30),
    ADD COLUMN IF NOT EXISTS data_origin VARCHAR(20);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_pa_asset_horizon
    ON aquavision.prediction_accuracy(asset_id, horizon, actual_at DESC);

CREATE INDEX IF NOT EXISTS idx_pa_model_version
    ON aquavision.prediction_accuracy(model_version, actual_at DESC);

-- Materialized view: latest accuracy snapshot per asset+horizon (30-day and 90-day rolling)
CREATE MATERIALIZED VIEW IF NOT EXISTS aquavision.mv_accuracy_snapshot AS
WITH base AS (
    SELECT
        asset_id,
        horizon,
        model_version,
        actual_at,
        error,
        abs_error,
        squared_error,
        pct_error,
        within_interval,
        direction_correct
    FROM aquavision.prediction_accuracy
    WHERE actual_value IS NOT NULL
),
rolling AS (
    SELECT
        asset_id,
        horizon,
        model_version,
        actual_at,

        -- 30-day rolling
        AVG(abs_error) OVER w30 AS mae_30d,
        SQRT(AVG(squared_error) OVER w30) AS rmse_30d,
        AVG(pct_error) OVER w30 AS mape_30d,
        AVG(error) OVER w30 AS bias_30d,
        AVG(CASE WHEN within_interval THEN 1.0 ELSE 0.0 END) OVER w30 AS coverage_30d,
        AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END) OVER w30 AS direction_30d,
        COUNT(*) OVER w30 AS sample_count_30d,

        -- 90-day rolling
        AVG(abs_error) OVER w90 AS mae_90d,
        SQRT(AVG(squared_error) OVER w90) AS rmse_90d,
        AVG(pct_error) OVER w90 AS mape_90d,
        AVG(error) OVER w90 AS bias_90d,
        AVG(CASE WHEN within_interval THEN 1.0 ELSE 0.0 END) OVER w90 AS coverage_90d,
        AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END) OVER w90 AS direction_90d,
        COUNT(*) OVER w90 AS sample_count_90d

    FROM base
    WINDOW
        w30 AS (PARTITION BY asset_id, horizon
                 ORDER BY actual_at
                 RANGE BETWEEN INTERVAL '30 days' PRECEDING AND CURRENT ROW),
        w90 AS (PARTITION BY asset_id, horizon
                 ORDER BY actual_at
                 RANGE BETWEEN INTERVAL '90 days' PRECEDING AND CURRENT ROW)
)
SELECT DISTINCT ON (asset_id, horizon)
    asset_id, horizon, model_version,
    mae_30d, rmse_30d, mape_30d, bias_30d, coverage_30d, direction_30d, sample_count_30d,
    mae_90d, rmse_90d, mape_90d, bias_90d, coverage_90d, direction_90d, sample_count_90d,
    actual_at AS last_evaluated_at
FROM rolling
ORDER BY asset_id, horizon, actual_at DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_accuracy_snapshot
    ON aquavision.mv_accuracy_snapshot(asset_id, horizon);

COMMIT;
