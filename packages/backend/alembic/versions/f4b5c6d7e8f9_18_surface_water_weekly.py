"""18_surface_water_weekly

Revision ID: f4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa

revision = "f4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS aquavision")
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    op.create_table(
        "surface_water_weekly",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("region_id", sa.Integer, sa.ForeignKey("shared.regions.id"), nullable=False),
        sa.Column("week_start_date", sa.Date, nullable=False),
        sa.Column("ndwi_mean", sa.Float, nullable=True),
        sa.Column("mndwi_mean", sa.Float, nullable=True),
        sa.Column("water_area_km2", sa.Float, nullable=True),
        sa.Column("prev_water_area_km2", sa.Float, nullable=True),
        sa.Column("change_pct", sa.Float, nullable=True),
        sa.Column("cloud_pct", sa.Float, nullable=True),
        sa.Column("data_status", sa.String(20), server_default="processed"),
        sa.Column("source_version", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("region_id", "week_start_date", name="uq_surface_water_region_week"),
        schema="aquavision",
    )

    op.create_index(
        "ix_sw_region_date",
        "surface_water_weekly",
        ["region_id", "week_start_date"],
        schema="aquavision",
    )

    op.create_index(
        "ix_sw_week",
        "surface_water_weekly",
        ["week_start_date"],
        schema="aquavision",
    )


def downgrade() -> None:
    op.drop_index("ix_sw_week", schema="aquavision")
    op.drop_index("ix_sw_region_date", schema="aquavision")
    op.drop_table("surface_water_weekly", schema="aquavision")
