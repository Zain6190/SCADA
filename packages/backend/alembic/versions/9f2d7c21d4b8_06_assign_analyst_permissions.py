"""06_assign_analyst_permissions

Revision ID: 9f3a7c21d4b8
Revises: 57d3b7f5e5cd
Create Date: 2026-08-08 00:10:00.000000

Assigns the fine-grained analyst permissions (created but previously unassigned
in migration 04) to the aquavision_analyst role:

  aquavision_analyst:
    - AQUAVISION_READ      (already present)
    - AQUAVISION_ANALYZE
    - AQUAVISION_EXPORT

This is a pure data migration - no schema changes. It is idempotent (checks
existing role_permissions rows before inserting) so re-running on any
environment is safe. NOTE: the analyst role previously also carried
AQUAVISION_MANAGE_DATA; that was later revoked by migration
09_separate_analyst_permissions to enforce least privilege (analysis is
separate from data management).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9f2d7c21d4b8'
down_revision: Union[str, None] = '9f3a7c21d4b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Permissions to (re-)ensure on the analyst role.
ANALYST_PERMISSIONS = ["AQUAVISION_ANALYZE", "AQUAVISION_EXPORT"]


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
    conn = op.get_bind()
    for perm in ANALYST_PERMISSIONS:
        _grant(conn, "aquavision_analyst", perm)


def downgrade() -> None:
    conn = op.get_bind()
    for perm in ANALYST_PERMISSIONS:
        conn.execute(
            sa.text(
                """
                DELETE FROM shared.role_permissions rp
                USING shared.roles r, shared.permissions p
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
                  AND r.name = :role AND p.name = :perm
                """
            ).bindparams(role="aquavision_analyst", perm=perm)
        )