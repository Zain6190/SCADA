"""03_seed_national_scopes

Revision ID: 4e3d4d51902a
Revises: 246378684414
Create Date: 2026-08-07 22:54:02.178007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e3d4d51902a'
down_revision: Union[str, None] = '246378684414'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Seeded demo accounts historically relied on "empty scope == national".
    # Under fail-closed rules those users now need an EXPLICIT NATIONAL scope.
    # Only grant to the known seeded accounts (they have no regional scope yet).
    op.execute(sa.text("""
        INSERT INTO shared.user_region_scopes (user_id, scope_type, is_active)
        SELECT u.id, 'NATIONAL', TRUE
        FROM shared.users u
        WHERE u.email IN (
            'admin@ibcp.gov.pk',
            'water@ibcp.gov.pk',
            'field@ibcp.gov.pk',
            'viewer@ibcp.gov.pk'
        )
        AND NOT EXISTS (
            SELECT 1 FROM shared.user_region_scopes s
            WHERE s.user_id = u.id AND s.is_active
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DELETE FROM shared.user_region_scopes
        WHERE scope_type = 'NATIONAL'
          AND user_id IN (
              SELECT id FROM shared.users
              WHERE email IN ('admin@ibcp.gov.pk','water@ibcp.gov.pk',
                              'field@ibcp.gov.pk','viewer@ibcp.gov.pk')
          )
    """))
