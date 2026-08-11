"""13_admin_user_lifecycle

Revision ID: 9c1d2e3f4a5b
Revises: a7b8c9d0e1f2
Create Date: 2026-08-11 09:00:00.000000

Extends the Phase-3 admin user lifecycle (user registration workflow):

  shared.users.last_login_at - updated on successful sign-in so the admin
      list can show "last login" (previously not tracked).

The account expiry story reuses shared.user_region_scopes.expires_at (already
present) - a TEMPORARY account is expressed as a scope row with an expiry, and
the fail-closed scope resolver (either rbac.get_active_scopes) already refuses
expired scopes, so expired temporary access automatically grants no data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9c1d2e3f4a5b'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Last successful sign-in"),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_column("users", "last_login_at", schema="shared")