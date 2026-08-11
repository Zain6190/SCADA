"""02_scope_fail_closed

Revision ID: 246378684414
Revises: 01145485c28e
Create Date: 2026-08-07 22:48:53.990773

Introduces the explicit, fail-closed geographic scope model.

The old table used a composite PRIMARY KEY (user_id, region_id) and treated
"no rows" as national access. This migration replaces it with a typed model
(scope_type NATIONAL/DISTRICT) and an explicit id.

Data preservation:
  - Existing (user_id, region_id) rows become DISTRICT-type active scopes.
  - Existing rows therefore keep exactly the regions they already had.
  - NOTE: under the new fail-closed model a user with NO scope rows is DENIED
    regional data. Admins must be granted an explicit NATIONAL scope.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '246378684414'
down_revision: Union[str, None] = '01145485c28e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the new typed table.
    op.execute(sa.text("""
        CREATE TABLE shared.user_region_scopes_new (
            id           BIGSERIAL PRIMARY KEY,
            user_id      BIGINT NOT NULL REFERENCES shared.users(id) ON DELETE CASCADE,
            scope_type   TEXT NOT NULL
                         CONSTRAINT ck_user_region_scope_type
                         CHECK (scope_type IN ('NATIONAL','PROVINCE','DISTRICT','ASSET')),
            region_id    BIGINT REFERENCES shared.regions(id) ON DELETE CASCADE,
            asset_id     BIGINT REFERENCES shared.assets(id) ON DELETE CASCADE,
            granted_by   BIGINT REFERENCES shared.users(id),
            granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at   TIMESTAMPTZ,
            is_active    BOOLEAN NOT NULL DEFAULT TRUE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_user_scope_target CHECK (
                (scope_type = 'NATIONAL' AND region_id IS NULL AND asset_id IS NULL) OR
                (scope_type IN ('PROVINCE','DISTRICT') AND region_id IS NOT NULL AND asset_id IS NULL) OR
                (scope_type = 'ASSET' AND asset_id IS NOT NULL AND region_id IS NULL)
            )
        )
    """))

    # 2. Preserve existing region scopes as DISTRICT-type active scopes.
    op.execute(
        sa.text(
            "INSERT INTO shared.user_region_scopes_new (user_id, scope_type, region_id, granted_at, is_active) "
            "SELECT user_id, 'DISTRICT', region_id, now(), TRUE FROM shared.user_region_scopes"
        )
    )

    # 3. Replace old table.
    op.execute(sa.text("DROP TABLE shared.user_region_scopes"))
    op.execute(sa.text("ALTER TABLE shared.user_region_scopes_new RENAME TO user_region_scopes"))

    # 4. Duplicate-active prevention: unique on active scopes per (user,type,target).
    # Avoid premature unique collisions between duplicated rows inserted above by
    # keeping the index partial on is_active (applies to newly-created rows too).
    op.execute(sa.text("""
        CREATE UNIQUE INDEX uq_user_region_scope_active
        ON shared.user_region_scopes (user_id, scope_type, region_id, asset_id)
        WHERE is_active
    """))


def downgrade() -> None:
    # Revert to the simple composite-key scope table (national when empty).
    op.execute(sa.text("DROP INDEX IF EXISTS shared.uq_user_region_scope_active"))
    op.execute(sa.text("""
        CREATE TABLE shared.user_region_scopes_old (
            user_id   BIGINT NOT NULL REFERENCES shared.users(id) ON DELETE CASCADE,
            region_id BIGINT NOT NULL REFERENCES shared.regions(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, region_id)
        )
    """))
    op.execute(
        sa.text(
            "INSERT INTO shared.user_region_scopes_old (user_id, region_id) "
            "SELECT user_id, region_id FROM shared.user_region_scopes "
            "WHERE scope_type IN ('NATIONAL','PROVINCE','DISTRICT') AND region_id IS NOT NULL"
        )
    )
    op.execute(sa.text("DROP TABLE shared.user_region_scopes"))
    op.execute(sa.text("ALTER TABLE shared.user_region_scopes_old RENAME TO user_region_scopes"))