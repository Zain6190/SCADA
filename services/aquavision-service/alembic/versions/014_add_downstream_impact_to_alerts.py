"""Add downstream impact columns to water_operational_alerts

Revision ID: 014
Revises: 013
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "water_operational_alerts",
        sa.Column("downstream_impact_summary", sa.Text(), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_operational_alerts",
        sa.Column("downstream_population_exposed", sa.BigInteger(), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_operational_alerts",
        sa.Column("downstream_bridges_at_risk", sa.Integer(), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_operational_alerts",
        sa.Column("downstream_hospitals_at_risk", sa.Integer(), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_operational_alerts",
        sa.Column("downstream_furthest_asset", sa.Text(), nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_operational_alerts",
        sa.Column("downstream_furthest_arrival_hours", sa.Numeric(), nullable=True),
        schema="aquavision",
    )


def downgrade() -> None:
    op.drop_column("water_operational_alerts", "downstream_impact_summary", schema="aquavision")
    op.drop_column("water_operational_alerts", "downstream_population_exposed", schema="aquavision")
    op.drop_column("water_operational_alerts", "downstream_bridges_at_risk", schema="aquavision")
    op.drop_column("water_operational_alerts", "downstream_hospitals_at_risk", schema="aquavision")
    op.drop_column("water_operational_alerts", "downstream_furthest_asset", schema="aquavision")
    op.drop_column("water_operational_alerts", "downstream_furthest_arrival_hours", schema="aquavision")
