"""08_asset_telemetry_and_notes

Revision ID: a8b9c0d1e2f3
Revises: 9f2d7c21d4b8
Create Date: 2026-08-09 08:00:00.000000

Adds the operational-telemetry + operator context the WATER_OPERATOR
dashboard needs (a hardened SCADA operator surface):

  aquavision.asset_telemetry
    - per-asset operational readings (reservoir level, storage pct,
      inflow / outflow / discharge cumecs) with a rich 24h series so the
      operator console can show live conditions and recent history.

  aquavision.asset_operational_notes
    - free-text operator notes attached to an asset (a SCADA logbook),
      recorded by the authenticated user who writes them.

Also grants the existing AQUAVISION_ADD_NOTE permission to the
field_officer role so operators can take note of their assigned assets.

Schema additions only; demo readings are seeded by the service layer's
seed_if_empty() so a fresh/empty DB (live or migrated) gets them the same
way the existing indicator seeds behave.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, None] = '9f2d7c21d4b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _grant(conn, role_name: str, perm_name: str) -> None:
    """Insert a role_permissions row if it doesn't already exist."""
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM shared.role_permissions rp
            JOIN shared.roles r ON r.id = rp.role_id
            JOIN shared.permissions p ON p.id = rp.permission_id
            WHERE r.name = :role AND p.name = :perm
            """
        ).bindparams(role=role_name, perm=perm_name)
    ).first()
    if row:
        return
    conn.execute(
        sa.text(
            """
            INSERT INTO shared.role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM shared.roles r, shared.permissions p
            WHERE r.name = :role AND p.name = :perm
            """
        ).bindparams(role=role_name, perm=perm_name)
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS aquavision")

    op.create_table(
        "asset_telemetry",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.BigInteger, sa.ForeignKey("shared.assets.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reservoir_level_m", sa.Numeric, nullable=True),
        sa.Column("storage_pct", sa.Numeric, nullable=True),
        sa.Column("inflow_cumecs", sa.Numeric, nullable=True),
        sa.Column("outflow_cumecs", sa.Numeric, nullable=True),
        sa.Column("discharge_cumecs", sa.Numeric, nullable=True),
        sa.Column("data_status", sa.Text, nullable=True, comment="Actual|Calibrated|Estimate|Missing"),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index("ix_asset_telemetry_asset_time", "asset_id", "recorded_at"),
        schema="aquavision",
    )

    op.create_table(
        "asset_operational_notes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.BigInteger, sa.ForeignKey("shared.assets.id"), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger, sa.ForeignKey("shared.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index("ix_asset_operational_notes_asset", "asset_id"),
        schema="aquavision",
    )

    conn = op.get_bind()
    _grant(conn, "field_officer", "AQUAVISION_ADD_NOTE")


def downgrade() -> None:
    op.drop_table("asset_operational_notes", schema="aquavision")
    op.drop_table("asset_telemetry", schema="aquavision")
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM shared.role_permissions rp
            USING shared.roles r, shared.permissions p
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
              AND r.name = :role AND p.name = :perm
            """
        ).bindparams(role="field_officer", perm="AQUAVISION_ADD_NOTE")
    )