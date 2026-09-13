-- 016_prediction_errors.sql
-- Create prediction_errors table for tracking prediction accuracy.

CREATE TABLE IF NOT EXISTS aquavision.prediction_errors (
    id SERIAL PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    model_version VARCHAR(50) NOT NULL,
    prediction_date TIMESTAMPTZ NOT NULL,
    target_date TIMESTAMPTZ NOT NULL,
    horizon INTEGER NOT NULL,
    predicted_value DOUBLE PRECISION NOT NULL,
    actual_value DOUBLE PRECISION NOT NULL,
    error DOUBLE PRECISION NOT NULL,
    error_pct DOUBLE PRECISION NOT NULL,
    data_origin VARCHAR(20) NOT NULL DEFAULT 'REAL',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_prediction_errors_asset ON aquavision.prediction_errors(asset_id);
CREATE INDEX IF NOT EXISTS idx_prediction_errors_target ON aquavision.prediction_errors(target_date);
CREATE INDEX IF NOT EXISTS idx_prediction_errors_model ON aquavision.prediction_errors(model_version);
CREATE INDEX IF NOT EXISTS idx_prediction_errors_lookup ON aquavision.prediction_errors(asset_id, horizon, prediction_date);

-- Accuracy summary view
CREATE OR REPLACE VIEW aquavision.v_accuracy_summary AS
SELECT 
    asset_id,
    horizon,
    model_version,
    COUNT(*) as total_predictions,
    ROUND(AVG(ABS(error))::numeric, 2) as mae,
    ROUND(SQRT(AVG(error * error))::numeric, 2) as rmse,
    ROUND(AVG(error_pct)::numeric, 1) as mape_pct,
    ROUND(AVG(CASE WHEN error > 0 THEN 100.0 ELSE 0.0 END)::numeric, 1) as overprediction_pct,
    ROUND(AVG(CASE WHEN error < 0 THEN 100.0 ELSE 0.0 END)::numeric, 1) as underprediction_pct,
    MIN(target_date) as earliest_prediction,
    MAX(target_date) as latest_prediction
FROM aquavision.prediction_errors
GROUP BY asset_id, horizon, model_version;

COMMENT ON TABLE aquavision.prediction_errors IS 'Tracks prediction vs actual values for accuracy monitoring';
COMMENT ON COLUMN aquavision.prediction_errors.error IS 'predicted - actual (positive = overprediction)';
COMMENT ON COLUMN aquavision.prediction_errors.error_pct IS 'abs(error) / actual * 100';
