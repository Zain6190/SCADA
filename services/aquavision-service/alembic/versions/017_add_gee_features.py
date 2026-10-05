"""Add GEE feature pipeline table (CHIRPS / MOD16 / MOD13Q1).

Revision ID: 017
Revises: 016
Create Date: 2026-10-01
"""
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.gee_features (
            id BIGSERIAL PRIMARY KEY,
            asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
            observed_on DATE NOT NULL,
            rainfall_mm DOUBLE PRECISION,
            et_mm DOUBLE PRECISION,
            ndvi DOUBLE PRECISION,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (asset_id, observed_on)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_gee_features_observed_on
        ON aquavision.gee_features (observed_on DESC)
    """)


def downgrade() -> None:
    op.drop_table("aquavision.gee_features")
