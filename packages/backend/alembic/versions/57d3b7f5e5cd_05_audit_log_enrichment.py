"""05_audit_log_enrichment

Revision ID: 57d3b7f5e5cd
Revises: c6b5d551e7a2
Create Date: 2026-08-07 23:11:11.518728

Expands system.audit_logs to the recommended shape. Existing rows (if any) are
preserved — the new columns are simply added. Never store passwords/tokens:
only structured action metadata.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '57d3b7f5e5cd'
down_revision: Union[str, None] = 'c6b5d551e7a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('audit_logs', sa.Column('role', sa.Text(), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('module', sa.Text(), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('resource_type', sa.Text(), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('resource_id', sa.Text(), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('region_id', sa.BigInteger(), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('before_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('after_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('result', sa.Text(), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('request_id', sa.Text(), nullable=True), schema='system')
    op.add_column('audit_logs', sa.Column('user_agent', sa.Text(), nullable=True), schema='system')
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['timestamp'], schema='system')
    op.create_index('ix_audit_logs_user', 'audit_logs', ['user_id'], schema='system')
    op.create_index('ix_audit_logs_module', 'audit_logs', ['module'], schema='system')


def downgrade() -> None:
    op.drop_index('ix_audit_logs_module', table_name='audit_logs', schema='system')
    op.drop_index('ix_audit_logs_user', table_name='audit_logs', schema='system')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs', schema='system')
    op.drop_column('audit_logs', 'user_agent', schema='system')
    op.drop_column('audit_logs', 'request_id', schema='system')
    op.drop_column('audit_logs', 'result', schema='system')
    op.drop_column('audit_logs', 'after_value', schema='system')
    op.drop_column('audit_logs', 'before_value', schema='system')
    op.drop_column('audit_logs', 'region_id', schema='system')
    op.drop_column('audit_logs', 'resource_id', schema='system')
    op.drop_column('audit_logs', 'resource_type', schema='system')
    op.drop_column('audit_logs', 'module', schema='system')
    op.drop_column('audit_logs', 'role', schema='system')