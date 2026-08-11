"""11_grant_admin_export_permission

Revision ID: f1c2d3e4a5b6
Revises: e6f4a2c8d1b5
Create Date: 2026-08-10 10:30:00.000000

Grants AQUAVISION_EXPORT (and AQUAVISION_APPROVE_REPORT if present) to the
administrator role so admins can generate weekly PDF reports and bulk-export
CSV / GeoJSON data. The admin role previously lacked AQUAVISION_EXPORT while
the frontend treats the admin role as all-powerful (hasPermission returns true),
creating a frontend/backend inconsistency.

Admin role already holds AQUAVISION_MANAGE_DATA which implies broad data
access; export privileges are a natural extension. Idempotent - only inserts
missing role_permissions rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1c2d3e4a5b6'
down_revision: Union[str, None] = 'e6f4a2c8d1b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_EXPORT_PERMS = ["AQUAVISION_EXPORT", "AQUAVISION_APPROVE_REPORT"]


def _grant(conn, role_name: str, perm_name: str) -> None:
    """Insert a role_permissions row if it doesn't already exist (idempotent)."""
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
    for perm in ADMIN_EXPORT_PERMS:
        _grant(conn, "admin", perm)


def downgrade() -> None:
    conn = op.get_bind()
    for perm in ADMIN_EXPORT_PERMS:
        conn.execute(
            sa.text(
                """
                DELETE FROM shared.role_permissions rp
                USING shared.roles r, shared.permissions p
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
                  AND r.name = :role AND p.name = :perm
                """
            ).bindparams(role="admin", perm=perm)
        )