"""14_supervisor_delegation

Revision ID: d7e8f9a0b1c2
Revises: 9c1d2e3f4a5b
Create Date: 2026-08-11 10:30:00.000000

Enables the delegated user-registration workflow (District Supervisor ->
Field Operator):

  Adds the shared.permissions.MANAGE_OPERATORS permission. It is granted to
  the water_supervisor role and the admin role. The permission powers the
  supervisor-facing account endpoints (/auth/operators*):

    - a supervisor may create / approve accounts ONLY in the
      geographic scope they already hold (Server clamps the new user's
      region to the supervisor's own region_ids; the client can never
      choose an out-of-scope area).
    - a supervisor may assign ONLY delegated roles
      (field_officer / viewer / analysts) - never admin or supervisor.

  Idempotent - inserts the permission only if missing, grants only if the
  role_permissions row is absent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = '9c1d2e3f4a5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERM = "MANAGE_OPERATORS"
GRANT_TO = ["water_supervisor", "admin"]


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.execute(
        sa.text("SELECT 1 FROM shared.permissions p WHERE p.name = :name")
        .bindparams(name=PERM)
    ).first():
        conn.execute(
            sa.text("INSERT INTO shared.permissions (name, description) VALUES "
                    "(:name, 'Create and approve operator accounts within the caller-owned scope')")
            .bindparams(name=PERM)
        )
    for role in GRANT_TO:
        if conn.execute(
            sa.text(
                """
                SELECT 1 FROM shared.role_permissions rp
                JOIN shared.roles r ON r.id = rp.role_id
                JOIN shared.permissions p ON p.id = rp.permission_id
                WHERE r.name = :role AND p.name = :perm
                """
            ).bindparams(role=role, perm=PERM)
        ).first():
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO shared.role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM shared.roles r, shared.permissions p
                WHERE r.name = :role AND p.name = :perm
                """
            ).bindparams(role=role, perm=PERM)
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Do NOT delete the permission row if a user might reference it elsewhere;
    # only sever the grants to the roles we added in this migration.
    conn.execute(
        sa.text(
            """
            DELETE FROM shared.role_permissions rp USING shared.roles r,
                  shared.permissions p, (SELECT unnest(ARRAY[:roles]) AS rn) x
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
              AND r.name = x.rn AND p.name = :perm
            """
        ).bindparams(roles=GRANT_TO, perm=PERM)
    )