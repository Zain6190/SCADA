"""09_separate_analyst_manage_data

Revision ID: b4a3c8d1e2f3
Revises: a8b9c0d1e2f3
Create Date: 2026-08-09 09:30:00.000000

Separates "data management" from "analysis" at the role boundary (Phase 1,
task 2, least privilege):

  aquavision_analyst:  REMOVE AQUAVISION_MANAGE_DATA
    keeps AQUAVISION_READ + AQUAVISION_ANALYZE + AQUAVISION_EXPORT

The analyst role reads, analyzes and exports water indicators but can no
longer ingest/edit raw data. Raw-data ingestion (managing the weekly
indicator record) is reserved for administrator-level roles. This is a pure
data migration, idempotent (delete-if-present) so re-running is safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4a3c8d1e2f3'
down_revision: Union[str, None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REVOKED_PERM = "AQUAVISION_MANAGE_DATA"


def _revoke(conn, role_name: str, perm_name: str) -> None:
    """Delete a role_permissions row if present."""
    conn.execute(
        sa.text(
            """
            DELETE FROM shared.role_permissions rp
            USING shared.roles r, shared.permissions p
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
              AND r.name = :role AND p.name = :perm
            """
        ).bindparams(role=role_name, perm=perm_name)
    )


def upgrade() -> None:
    conn = op.get_bind()
    _revoke(conn, "aquavision_analyst", REVOKED_PERM)


def downgrade() -> None:
    conn = op.get_bind()
    # Restore the row if the permission/role exist.
    conn.execute(
        sa.text(
            """
            INSERT INTO shared.role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM shared.roles r, shared.permissions p
            WHERE r.name = :role AND p.name = :perm
              AND NOT EXISTS (
                  SELECT 1 FROM shared.role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        ).bindparams(role="aquavision_analyst", perm=REVOKED_PERM)
    )