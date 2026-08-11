"""04_standardize_permissions

Revision ID: c6b5d551e7a2
Revises: 4e3d4d51902a
Create Date: 2026-08-07 23:03:18.687622

Standardizes permission identifiers to an action-scoped convention. Old names
are migrated in place; because role_permissions reference permission_id (not
the name), all existing role assignments are preserved automatically.

Old -> New mapping:
  water:read          -> AQUAVISION_READ
  water:write         -> AQUAVISION_MANAGE_DATA
  water:ack_alert     -> AQUAVISION_ACKNOWLEDGE_ALERT
  water:config        -> AQUAVISION_CONFIGURE
  crop:read           -> CROP_READ
  crop:train_model    -> CROP_TRAIN_MODEL
  geo:read            -> GEOVISION_READ
  admin:config        -> SYSTEM_ADMIN

Additional fine-grained permissions are added (unassigned unless noted) for the
future Analyst / Supervisor / Data-Manager roles:
  AQUAVISION_ANALYZE, AQUAVISION_EXPORT, AQUAVISION_APPROVE_REPORT,
  AQUAVISION_MANAGE_USERS, AQUAVISION_ADD_NOTE
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c6b5d551e7a2'
down_revision: Union[str, None] = '4e3d4d51902a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENAME = {
    "water:read": "AQUAVISION_READ",
    "water:write": "AQUAVISION_MANAGE_DATA",
    "water:ack_alert": "AQUAVISION_ACKNOWLEDGE_ALERT",
    "water:config": "AQUAVISION_CONFIGURE",
    "crop:read": "CROP_READ",
    "crop:train_model": "CROP_TRAIN_MODEL",
    "geo:read": "GEOVISION_READ",
    "admin:config": "SYSTEM_ADMIN",
}

NEW = [
    "AQUAVISION_ANALYZE",
    "AQUAVISION_EXPORT",
    "AQUAVISION_ADD_NOTE",
    "AQUAVISION_APPROVE_REPORT",
    "AQUAVISION_MANAGE_USERS",
]


def upgrade() -> None:
    table = sa.table(
        "permissions",
        sa.column("name", sa.Text()),
        sa.column("description", sa.Text()),
        schema="shared",
    )
    for old, new in RENAME.items():
        # Take ownership of the canonical name wherever it exists (id stays the
        # same, so role_permissions mappings carry over).
        op.execute(
            sa.text(
                "UPDATE shared.permissions SET name = :new WHERE name = :old"
            ).bindparams(new=new, old=old)
        )

    conn = op.get_bind()
    existing = {
        r[0] for r in conn.execute(
            sa.text("SELECT name FROM shared.permissions")
        ).fetchall()
    }
    for name in NEW:
        if name not in existing and name not in RENAME.values():
            op.execute(
                sa.text(
                    "INSERT INTO shared.permissions (name, description) "
                    "VALUES (:name, :desc)"
                ).bindparams(name=name, desc=f"Standard {name} permission")
            )


def downgrade() -> None:
    for old, new in RENAME.items():
        op.execute(
            sa.text("UPDATE shared.permissions SET name = :old WHERE name = :new"
                    ).bindparams(old=old, new=new)
        )
    conn = op.get_bind()
    existing = {r[0] for r in conn.execute(
        sa.text("SELECT name FROM shared.permissions")
    ).fetchall()}
    for name in NEW:
        if name in existing:
            op.execute(
                sa.text("DELETE FROM shared.permissions WHERE name = :name"
                        ).bindparams(name=name)
            )