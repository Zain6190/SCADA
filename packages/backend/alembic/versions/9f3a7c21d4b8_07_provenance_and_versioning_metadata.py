"""07_provenance_and_versioning_metadata

Revision ID: 9f3a7c21d4b8
Revises: 57d3b7f5e5cd
Create Date: 2026-08-07 23:40:00.000000

Adds data provenance / status columns (point #8) to water_indicators_weekly and
ML versioning metadata (point #9) to water_predictions_weekly. Existing rows are
preserved; new columns are nullable so backfill is optional.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9f3a7c21d4b8'
down_revision: Union[str, None] = '57d3b7f5e5cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sch = 'aquavision'
    # #8 provenance / status on water indicators
    op.add_column('water_indicators_weekly', sa.Column('data_status', sa.Text(), nullable=True, comment='Actual|Calibrated|Estimate|Missing'), schema=sch)
    op.add_column('water_indicators_weekly', sa.Column('data_quality', sa.Text(), nullable=True, comment='Good|Ok|Stale|Missing'), schema=sch)
    op.add_column('water_indicators_weekly', sa.Column('data_provider', sa.Text(), nullable=True, comment='Data origin e.g. GEE-JRC, SATE, Field'), schema=sch)
    op.add_column('water_indicators_weekly', sa.Column('wai_model_version', sa.Text(), nullable=True, comment='Version of the WAI scoring model'), schema=sch)
    op.add_column('water_indicators_weekly', sa.Column('source_observed_at', sa.DateTime(timezone=True), nullable=True, comment='Freshness of underlying observation'), schema=sch)
    op.add_column('water_indicators_weekly', sa.Column('last_validated_at', sa.DateTime(timezone=True), nullable=True), schema=sch)
    # #9 prediction versioning metadata
    op.add_column('water_predictions_weekly', sa.Column('trained_on_week_start', sa.Date(), nullable=True, comment='Cutoff week used to train the model'), schema=sch)
    op.add_column('water_predictions_weekly', sa.Column('dataset_version', sa.Text(), nullable=True, comment='Version of training dataset'), schema=sch)
    op.add_column('water_predictions_weekly', sa.Column('feature_importance_hash', sa.Text(), nullable=True), schema=sch)


def downgrade() -> None:
    sch = 'aquavision'
    op.drop_column('water_predictions_weekly', 'feature_importance_hash', schema=sch)
    op.drop_column('water_predictions_weekly', 'dataset_version', schema=sch)
    op.drop_column('water_predictions_weekly', 'trained_on_week_start', schema=sch)
    op.drop_column('water_indicators_weekly', 'last_validated_at', schema=sch)
    op.drop_column('water_indicators_weekly', 'source_observed_at', schema=sch)
    op.drop_column('water_indicators_weekly', 'wai_model_version', schema=sch)
    op.drop_column('water_indicators_weekly', 'data_provider', schema=sch)
    op.drop_column('water_indicators_weekly', 'data_quality', schema=sch)
    op.drop_column('water_indicators_weekly', 'data_status', schema=sch)