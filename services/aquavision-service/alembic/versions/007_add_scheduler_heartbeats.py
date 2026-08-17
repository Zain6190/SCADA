"""add scheduler heartbeats

Revision ID: 007
Revises: 006
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scheduler_heartbeats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('service_name', sa.String(50), nullable=False),
        sa.Column('instance_id', sa.String(100), nullable=False),
        sa.Column('host_name', sa.String(100)),
        sa.Column('container_id', sa.String(100)),
        sa.Column('version', sa.String(50)),
        sa.Column('process_id', sa.Integer()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), server_default='RUNNING'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        schema='aquavision'
    )
    op.create_unique_constraint(
        'uq_scheduler_heartbeat',
        'scheduler_heartbeats',
        ['service_name', 'instance_id'],
        schema='aquavision'
    )


def downgrade() -> None:
    op.drop_constraint('uq_scheduler_heartbeat', 'scheduler_heartbeats', schema='aquavision')
    op.drop_table('scheduler_heartbeats', schema='aquavision')
