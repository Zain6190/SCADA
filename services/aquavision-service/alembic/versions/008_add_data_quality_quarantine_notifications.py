"""add data quality, quarantine, and notification deliveries

Revision ID: 008
Revises: 007
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Data quality log
    op.create_table(
        'data_quality_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('observation_id', sa.Integer()),
        sa.Column('check_type', sa.String(50), nullable=False),
        sa.Column('field_name', sa.String(50), nullable=False),
        sa.Column('raw_value', sa.Float()),
        sa.Column('expected_range_min', sa.Float()),
        sa.Column('expected_range_max', sa.Float()),
        sa.Column('quality_status', sa.String(20), nullable=False),
        sa.Column('details', sa.Text()),
        sa.Column('source_record_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='aquavision'
    )
    op.create_index('ix_data_quality_log_asset_id', 'data_quality_log', ['asset_id'], schema='aquavision')
    op.create_index('ix_data_quality_log_check_type', 'data_quality_log', ['check_type'], schema='aquavision')

    # Quarantine table for invalid observations
    op.create_table(
        'water_observation_quarantine',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('source_record_id', sa.Integer()),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('parsed_values', sa.JSON()),
        sa.Column('failure_reason', sa.Text(), nullable=False),
        sa.Column('field_name', sa.String(50)),
        sa.Column('raw_value', sa.Float()),
        sa.Column('parser_version', sa.String(50)),
        sa.Column('data_status', sa.String(30)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='aquavision'
    )
    op.create_index('ix_quarantine_asset_id', 'water_observation_quarantine', ['asset_id'], schema='aquavision')

    # Notification deliveries (persistent dedup)
    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('alert_key', sa.String(200), nullable=False),
        sa.Column('recipient', sa.String(200), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('dedup_key', sa.String(300), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default='1'),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='aquavision'
    )
    op.create_unique_constraint(
        'uq_notification_dedup',
        'notification_deliveries',
        ['dedup_key', 'recipient'],
        schema='aquavision'
    )
    op.create_index('ix_notification_dedup_key', 'notification_deliveries', ['dedup_key'], schema='aquavision')


def downgrade() -> None:
    op.drop_index('ix_notification_dedup_key', schema='aquavision')
    op.drop_constraint('uq_notification_dedup', 'notification_deliveries', schema='aquavision')
    op.drop_table('notification_deliveries', schema='aquavision')
    op.drop_index('ix_quarantine_asset_id', schema='aquavision')
    op.drop_table('water_observation_quarantine', schema='aquavision')
    op.drop_index('ix_data_quality_log_check_type', schema='aquavision')
    op.drop_index('ix_data_quality_log_asset_id', schema='aquavision')
    op.drop_table('data_quality_log', schema='aquavision')
