"""add alert lineage and episode tracking

Revision ID: 010
Revises: 009
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create water_alert_episodes table
    op.create_table(
        'water_alert_episodes',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('episode_key', sa.Text, nullable=False, unique=True),
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('severity', sa.Text, nullable=False, server_default='WATCH'),
        sa.Column('status', sa.Text, nullable=False, server_default='OPEN'),
        sa.Column('triggered_by_asset_id', sa.BigInteger, sa.ForeignKey('aquavision.water_assets.id')),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='aquavision'
    )
    op.create_index('ix_water_alert_episodes_episode_key', 'water_alert_episodes', ['episode_key'], schema='aquavision')

    # 2. Add lineage fields to water_operational_alerts
    op.add_column('water_operational_alerts',
        sa.Column('alert_source', sa.Text, nullable=False, server_default='RULE'),
        schema='aquavision')
    op.add_column('water_operational_alerts',
        sa.Column('alert_domain', sa.Text, nullable=False, server_default='OPERATIONAL'),
        schema='aquavision')
    op.add_column('water_operational_alerts',
        sa.Column('rule_version', sa.Text),
        schema='aquavision')
    op.add_column('water_operational_alerts',
        sa.Column('model_version', sa.Text),
        schema='aquavision')
    op.add_column('water_operational_alerts',
        sa.Column('episode_id', sa.BigInteger, sa.ForeignKey('aquavision.water_alert_episodes.id')),
        schema='aquavision')

    # 3. Add lineage fields to water_alerts
    op.add_column('water_alerts',
        sa.Column('alert_source', sa.Text, nullable=False, server_default='WAI_MODEL'),
        schema='aquavision')
    op.add_column('water_alerts',
        sa.Column('alert_domain', sa.Text, nullable=False, server_default='WATER_STRESS'),
        schema='aquavision')
    op.add_column('water_alerts',
        sa.Column('model_version', sa.Text),
        schema='aquavision')

    # 4. Indexes
    op.create_index('ix_water_operational_alerts_alert_source', 'water_operational_alerts', ['alert_source'], schema='aquavision')
    op.create_index('ix_water_operational_alerts_episode_id', 'water_operational_alerts', ['episode_id'], schema='aquavision')


def downgrade() -> None:
    op.drop_index('ix_water_operational_alerts_episode_id', schema='aquavision')
    op.drop_index('ix_water_operational_alerts_alert_source', schema='aquavision')
    op.drop_column('water_operational_alerts', 'episode_id', schema='aquavision')
    op.drop_column('water_operational_alerts', 'model_version', schema='aquavision')
    op.drop_column('water_operational_alerts', 'rule_version', schema='aquavision')
    op.drop_column('water_operational_alerts', 'alert_domain', schema='aquavision')
    op.drop_column('water_operational_alerts', 'alert_source', schema='aquavision')
    op.drop_column('water_alerts', 'model_version', schema='aquavision')
    op.drop_column('water_alerts', 'alert_domain', schema='aquavision')
    op.drop_column('water_alerts', 'alert_source', schema='aquavision')
    op.drop_index('ix_water_alert_episodes_episode_key', schema='aquavision')
    op.drop_table('water_alert_episodes', schema='aquavision')
