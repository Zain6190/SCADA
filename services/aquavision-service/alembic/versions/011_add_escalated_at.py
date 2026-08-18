"""011 Add escalated_at to water_operational_alerts for auto-escalation.

Revision ID: 011
Revises: 010
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "water_operational_alerts",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        schema="aquavision",
    )


def downgrade() -> None:
    op.drop_column("water_operational_alerts", "escalated_at", schema="aquavision")
