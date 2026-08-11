"""10_user_access_status

Revision ID: e6f4a2c8d1b5
Revises: b4a3c8d1e2f3
Create Date: 2026-08-09 10:15:00.000000

Access-lifecycle columns for phase 2 (portal access architecture):

  shared.users.access_status       PENDING | APPROVED | REJECTED | ACTIVE | SUSPENDED | REVOKED
  shared.users.access_requested_at When the user logged a first access request.

Existing rows are backfilled to ACTIVE so live accounts keep working. The
account lifecycle is enforced at login: SUSPENDED/REVOKED/inactive users are
rejected with 'account-disabled', PENDING/REJECTED requests with
'access-pending'. Idempotent additive migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e6f4a2c8d1b5'
down_revision: Union[str, None] = 'b4a3c8d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "access_status",
            sa.Text(),
            server_default="ACTIVE",
            nullable=False,
            comment="PENDING|APPROVED|REJECTED|ACTIVE|SUSPENDED|REVOKED",
        ),
        schema="shared",
    )
    op.add_column(
        "users",
        sa.Column(
            "access_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the user's portal access was requested",
        ),
        schema="shared",
    )


def downgrade() -> None:
    op.drop_column("users", "access_requested_at", schema="shared")
    op.drop_column("users", "access_status", schema="shared")