"""Add flood_probability to water_asset_forecasts (classifier shadow scoring).

Revision ID: 018
Revises: 017
Create Date: 2026-10-02
"""
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE IF EXISTS aquavision.water_asset_forecasts
        ADD COLUMN IF NOT EXISTS flood_probability DOUBLE PRECISION
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE IF EXISTS aquavision.water_asset_forecasts
        DROP COLUMN IF EXISTS flood_probability
    """)
