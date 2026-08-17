"""add pipeline runs and stages

Revision ID: 006
Revises: 
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '006'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pipeline_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(50), unique=True, nullable=False),
        sa.Column('pipeline_type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('trigger_type', sa.String(20), nullable=False),
        sa.Column('lock_key', sa.String(100)),
        sa.Column('code_version', sa.String(50)),
        sa.Column('config_version', sa.String(50)),
        sa.Column('source_version', sa.String(50)),
        sa.Column('log_path', sa.String(500)),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('duration_seconds', sa.Float()),
        sa.Column('error_message', sa.Text()),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='aquavision'
    )
    op.create_index('ix_pipeline_runs_pipeline_type', 'pipeline_runs', ['pipeline_type'], schema='aquavision')
    op.create_index('ix_pipeline_runs_status', 'pipeline_runs', ['status'], schema='aquavision')
    op.create_index('ix_pipeline_runs_started_at', 'pipeline_runs', ['started_at'], schema='aquavision')

    op.create_table(
        'pipeline_run_stages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(50), sa.ForeignKey('aquavision.pipeline_runs.run_id'), nullable=False),
        sa.Column('stage_name', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('records_fetched', sa.Integer(), server_default='0'),
        sa.Column('records_stored', sa.Integer(), server_default='0'),
        sa.Column('records_skipped', sa.Integer(), server_default='0'),
        sa.Column('records_invalid', sa.Integer(), server_default='0'),
        sa.Column('warning_count', sa.Integer(), server_default='0'),
        sa.Column('error_message', sa.Text()),
        sa.Column('log_path', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='aquavision'
    )
    op.create_index('ix_pipeline_run_stages_run_id', 'pipeline_run_stages', ['run_id'], schema='aquavision')


def downgrade() -> None:
    op.drop_index('ix_pipeline_run_stages_run_id', schema='aquavision')
    op.drop_table('pipeline_run_stages', schema='aquavision')
    op.drop_index('ix_pipeline_runs_started_at', schema='aquavision')
    op.drop_index('ix_pipeline_runs_status', schema='aquavision')
    op.drop_index('ix_pipeline_runs_pipeline_type', schema='aquavision')
    op.drop_table('pipeline_runs', schema='aquavision')
