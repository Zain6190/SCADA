# Alembic migration 013: Source-aware observation architecture.
# NOTE: Columns were added via direct SQL due to transaction issues with views.
# This migration tracks the version but the actual work was done via psql.

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Source-aware architecture already applied via direct SQL.
    
    What was done:
    1. Added columns: source_authority, source_publication_time, 
       source_parser_version, source_content_hash, source_priority
    2. Populated source_authority from water_sources.authority
    3. Set source_priority: IRSA=1, FFD/PMD=2, KAGGLE=3, SYNTHETIC=4
    4. Created indexes: ix_water_obs_source_authority, ix_water_obs_asset_date_source
    5. Created views: v_unified_observations, v_best_observations, 
       v_irsa_observations, v_kaggle_observations, v_source_coverage
    """
    pass


def downgrade() -> None:
    from alembic import op

    op.execute("DROP VIEW IF EXISTS aquavision.v_source_coverage")
    op.execute("DROP VIEW IF EXISTS aquavision.v_kaggle_observations")
    op.execute("DROP VIEW IF EXISTS aquavision.v_irsa_observations")
    op.execute("DROP VIEW IF EXISTS aquavision.v_best_observations")
    op.execute("DROP VIEW IF EXISTS aquavision.v_unified_observations")
    op.drop_index("ix_water_obs_asset_date_source", "water_observations", schema="aquavision")
    op.drop_index("ix_water_obs_source_authority", "water_observations", schema="aquavision")
    op.drop_column("water_observations", "source_priority", schema="aquavision")
    op.drop_column("water_observations", "source_content_hash", schema="aquavision")
    op.drop_column("water_observations", "source_parser_version", schema="aquavision")
    op.drop_column("water_observations", "source_publication_time", schema="aquavision")
    op.drop_column("water_observations", "source_authority", schema="aquavision")
