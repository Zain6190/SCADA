"""Check and create validation_reports table."""
from infrastructure.db.engine import engine
from sqlalchemy import text

CREATE_SQL = """
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
);
CREATE INDEX IF NOT EXISTS idx_validation_reports_asset ON aquavision.validation_reports(asset_id);
CREATE INDEX IF NOT EXISTS idx_validation_reports_validated ON aquavision.validation_reports(validated_at DESC);
"""

with engine.begin() as conn:
    for stmt in CREATE_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(text(stmt))
    print("validation_reports table ready")
