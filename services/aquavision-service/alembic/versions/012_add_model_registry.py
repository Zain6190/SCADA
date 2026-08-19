# Alembic migration 012: Add model registry and validation tables.
# Phase 3: ML Validation

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSON, BIGINT

    # Model version registry
    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.model_versions (
            id BIGSERIAL PRIMARY KEY,
            model_type VARCHAR(50) NOT NULL,
            asset_id BIGINT REFERENCES aquavision.water_assets(id),
            version VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'EXPERIMENTAL',
            metrics JSON,
            validation_report_id BIGINT,
            trained_at TIMESTAMPTZ,
            approved_at TIMESTAMPTZ,
            approved_by VARCHAR(100),
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Validation reports
    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.validation_reports (
            id BIGSERIAL PRIMARY KEY,
            asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
            model_type VARCHAR(50) NOT NULL,
            model_version VARCHAR(50) NOT NULL,
            horizon INTEGER NOT NULL,
            metrics JSON NOT NULL,
            data_info JSON NOT NULL,
            recommendation VARCHAR(20) NOT NULL,
            reasons JSON,
            fold_details JSON,
            validated_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Prediction errors
    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.prediction_errors (
            id BIGSERIAL PRIMARY KEY,
            asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
            model_version VARCHAR(50) NOT NULL,
            prediction_date TIMESTAMPTZ NOT NULL,
            target_date TIMESTAMPTZ NOT NULL,
            horizon INTEGER NOT NULL,
            predicted_value DOUBLE PRECISION NOT NULL,
            actual_value DOUBLE PRECISION NOT NULL,
            error DOUBLE PRECISION NOT NULL,
            error_pct DOUBLE PRECISION NOT NULL,
            data_origin VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_versions_type ON aquavision.model_versions(model_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_versions_status ON aquavision.model_versions(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_validation_reports_asset ON aquavision.validation_reports(asset_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_prediction_errors_asset ON aquavision.prediction_errors(asset_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_prediction_errors_date ON aquavision.prediction_errors(prediction_date)")


def downgrade() -> None:
    from alembic import op
    op.execute("DROP TABLE IF EXISTS aquavision.prediction_errors")
    op.execute("DROP TABLE IF EXISTS aquavision.validation_reports")
    op.execute("DROP TABLE IF EXISTS aquavision.model_versions")
