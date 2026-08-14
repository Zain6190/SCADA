"""Add SPI (Standardized Precipitation Index) columns.

Revision ID: a1b2c3d4e5f6
Revises: f4b5c6d7e8f9
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "water_indicators_weekly",
        sa.Column("spi_1", sa.Numeric, nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_indicators_weekly",
        sa.Column("spi_3", sa.Numeric, nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_indicators_weekly",
        sa.Column("spi_6", sa.Numeric, nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_indicators_weekly",
        sa.Column("spi_12", sa.Numeric, nullable=True),
        schema="aquavision",
    )
    op.add_column(
        "water_indicators_weekly",
        sa.Column("spi_drought_class", sa.String(20), nullable=True),
        schema="aquavision",
    )


def downgrade() -> None:
    op.drop_column("water_indicators_weekly", "spi_drought_class", schema="aquavision")
    op.drop_column("water_indicators_weekly", "spi_12", schema="aquavision")
    op.drop_column("water_indicators_weekly", "spi_6", schema="aquavision")
    op.drop_column("water_indicators_weekly", "spi_3", schema="aquavision")
    op.drop_column("water_indicators_weekly", "spi_1", schema="aquavision")
