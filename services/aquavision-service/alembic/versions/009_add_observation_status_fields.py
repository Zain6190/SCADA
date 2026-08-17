"""add quality_status to water_observations

Revision ID: 009
Revises: 008
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # data_status already exists from prior migration
    # Update existing 'OBSERVED' values to 'OBSERVED_OFFICIAL'
    op.execute("""
        UPDATE aquavision.water_observations
        SET data_status = 'OBSERVED_OFFICIAL'
        WHERE data_status = 'OBSERVED'
    """)

    # Add quality_status (validity)
    op.add_column(
        'water_observations',
        sa.Column('quality_status', sa.String(20), server_default='VALID'),
        schema='aquavision'
    )
    op.create_index('ix_water_observations_quality_status', 'water_observations', ['quality_status'], schema='aquavision')


def downgrade() -> None:
    op.drop_index('ix_water_observations_quality_status', schema='aquavision')
    op.drop_column('water_observations', 'quality_status', schema='aquavision')
