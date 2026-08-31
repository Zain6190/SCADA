"""Create validation_reports table on Neon DB."""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("No DATABASE_URL set, skipping Neon")
    exit(0)

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS aquavision.validation_reports (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            model_type VARCHAR(50) NOT NULL DEFAULT 'flood_predictor',
            model_version VARCHAR(50) NOT NULL DEFAULT 'xgb-flood-v1.2',
            horizon INTEGER NOT NULL,
            metrics JSONB NOT NULL DEFAULT '{}',
            data_info JSONB NOT NULL DEFAULT '{}',
            recommendation VARCHAR(20) NOT NULL DEFAULT 'EXPERIMENTAL',
            reasons JSONB NOT NULL DEFAULT '[]',
            fold_details JSONB NOT NULL DEFAULT '[]',
            validated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_validation_reports_asset ON aquavision.validation_reports(asset_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_validation_reports_validated ON aquavision.validation_reports(validated_at DESC)"))
    print("Neon validation_reports table ready")
