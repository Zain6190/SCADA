"""Apply prediction persistence migration to Neon DB."""
import os
from sqlalchemy import create_engine, text

NEON_URL = os.getenv("DATABASE_URL")
if not NEON_URL:
    print("ERROR: DATABASE_URL not set")
    exit(1)

engine = create_engine(NEON_URL)

statements = [
    """CREATE TABLE IF NOT EXISTS aquavision.water_predictions (
        id SERIAL PRIMARY KEY,
        asset_id INTEGER NOT NULL,
        horizon INTEGER NOT NULL,
        predicted_value DOUBLE PRECISION,
        predicted_lower DOUBLE PRECISION,
        predicted_upper DOUBLE PRECISION,
        risk_score INTEGER,
        risk_category VARCHAR(20),
        exceeds_warning BOOLEAN DEFAULT false,
        exceeds_danger BOOLEAN DEFAULT false,
        model_version VARCHAR(50),
        model_type VARCHAR(30) DEFAULT 'flood_predictor',
        features_used JSONB DEFAULT '[]'::jsonb,
        feature_importance JSONB DEFAULT '{}'::jsonb,
        confidence DOUBLE PRECISION,
        valid_from TIMESTAMPTZ NOT NULL,
        valid_to TIMESTAMPTZ NOT NULL,
        generated_at TIMESTAMPTZ DEFAULT now(),
        created_at TIMESTAMPTZ DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_wp_asset ON aquavision.water_predictions(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_wp_horizon ON aquavision.water_predictions(horizon)",
    "CREATE INDEX IF NOT EXISTS idx_wp_valid ON aquavision.water_predictions(valid_from, valid_to)",
    "CREATE INDEX IF NOT EXISTS idx_wp_generated ON aquavision.water_predictions(generated_at DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_wp_unique ON aquavision.water_predictions(asset_id, horizon, valid_from)",
    """CREATE TABLE IF NOT EXISTS aquavision.model_versions (
        id SERIAL PRIMARY KEY,
        asset_id INTEGER NOT NULL,
        model_type VARCHAR(30) NOT NULL,
        horizon INTEGER,
        version VARCHAR(50) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'EXPERIMENTAL',
        metrics JSONB DEFAULT '{}'::jsonb,
        hyperparams JSONB DEFAULT '{}'::jsonb,
        features JSONB DEFAULT '[]'::jsonb,
        training_samples INTEGER,
        training_window VARCHAR(50),
        trained_at TIMESTAMPTZ,
        promoted_at TIMESTAMPTZ,
        retired_at TIMESTAMPTZ,
        notes TEXT,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mv_asset ON aquavision.model_versions(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_mv_status ON aquavision.model_versions(status)",
    "CREATE INDEX IF NOT EXISTS idx_mv_type ON aquavision.model_versions(model_type)",
    """CREATE TABLE IF NOT EXISTS aquavision.prediction_accuracy (
        id SERIAL PRIMARY KEY,
        asset_id INTEGER NOT NULL,
        horizon INTEGER NOT NULL,
        prediction_id INTEGER,
        predicted_value DOUBLE PRECISION,
        actual_value DOUBLE PRECISION,
        error DOUBLE PRECISION,
        abs_error DOUBLE PRECISION,
        squared_error DOUBLE PRECISION,
        pct_error DOUBLE PRECISION,
        predicted_at TIMESTAMPTZ,
        actual_at TIMESTAMPTZ,
        model_version VARCHAR(50),
        matched_at TIMESTAMPTZ DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pa_asset ON aquavision.prediction_accuracy(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_pa_date ON aquavision.prediction_accuracy(actual_at DESC)",
    """CREATE TABLE IF NOT EXISTS aquavision.feature_drift (
        id SERIAL PRIMARY KEY,
        asset_id INTEGER NOT NULL,
        feature_name VARCHAR(100) NOT NULL,
        psi DOUBLE PRECISION,
        ks_statistic DOUBLE PRECISION,
        mean_current DOUBLE PRECISION,
        mean_baseline DOUBLE PRECISION,
        std_current DOUBLE PRECISION,
        std_baseline DOUBLE PRECISION,
        drift_status VARCHAR(20) DEFAULT 'STABLE',
        evaluation_window VARCHAR(20),
        computed_at TIMESTAMPTZ DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_fd_asset ON aquavision.feature_drift(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_fd_status ON aquavision.feature_drift(drift_status)",
    "CREATE INDEX IF NOT EXISTS idx_fd_date ON aquavision.feature_drift(computed_at DESC)",
    """CREATE TABLE IF NOT EXISTS aquavision.prediction_logs (
        id SERIAL PRIMARY KEY,
        run_type VARCHAR(30) NOT NULL,
        assets_predicted INTEGER DEFAULT 0,
        assets_failed INTEGER DEFAULT 0,
        predictions_written INTEGER DEFAULT 0,
        duration_seconds FLOAT,
        model_versions JSONB DEFAULT '{}'::jsonb,
        errors JSONB DEFAULT '[]'::jsonb,
        started_at TIMESTAMPTZ DEFAULT now(),
        completed_at TIMESTAMPTZ,
        status VARCHAR(20) DEFAULT 'RUNNING'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pl_date ON aquavision.prediction_logs(started_at DESC)",
]

ok = 0
fail = 0
for i, stmt in enumerate(statements):
    with engine.begin() as conn:
        try:
            conn.execute(text(stmt))
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  SKIP {i+1}: {str(e)[:80]}")

print(f"Neon migration complete: {ok} OK, {fail} skipped")
