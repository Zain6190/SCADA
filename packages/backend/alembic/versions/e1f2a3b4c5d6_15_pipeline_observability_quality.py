"""15_pipeline_observability_quality

Revision ID: e1f2a3b4c5d6
Revises: d7e8f9a0b1c2
Create Date: 2026-08-11 12:00:00.000000

Adds the observability + data-quality layer that makes the weekly GEE pipeline
operationally trustworthy:

  system.pipeline_runs      - every execution is recorded with run id, status
                              lifecycle (QUEUED/RUNNING/SUCCESS/PARTIAL_SUCCESS/
                              FAILED), trigger type, data period, record counts,
                              warning/error counts and version provenance.
  aquavision.water_indicators_weekly
                            - completeness/quality fields so a partial month
                              (e.g. July rainfall not yet finalized) is shown as
                              PARTIAL, never as "zero rainfall":
                              period_start/end, is_complete_period, coverage_pct,
                              observation_count, expected_observation_count,
                              quality_status (VALID|PARTIAL|STALE|SUSPECT|INVALID).
  aquavision.water_alerts   - alert source attribution so users can tell MODEL
                              forecasts from RULE triggers / DATA_QUALITY flags:
                              source, confidence, rule_version.
  aquavision.water_predictions_weekly
                            - forecast-vs-actual validation columns:
                              lower_bound, upper_bound, feature_version,
                              training_cutoff, actual_value, error, validated_at.

All new columns are nullable/backward-compatible. Idempotent via IF NOT EXISTS.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(schema: str, table: str, column: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND column_name = :c"
        ).bindparams(s=schema, t=table, c=column)
    ).first()
    return row is not None


def _add(schema: str, table: str, column: str, coltype) -> None:
    if not _has_column(schema, table, column):
        op.add_column(table, sa.Column(column, coltype, nullable=True), schema=schema)


def upgrade() -> None:
    # ---- system.pipeline_runs: observability ----
    _add("system", "pipeline_runs", "run_id", sa.Text())
    _add("system", "pipeline_runs", "trigger_type", sa.Text())
    _add("system", "pipeline_runs", "data_period", sa.Text())
    _add("system", "pipeline_runs", "records_read", sa.Integer())
    _add("system", "pipeline_runs", "records_written", sa.Integer())
    _add("system", "pipeline_runs", "records_skipped", sa.Integer())
    _add("system", "pipeline_runs", "warning_count", sa.Integer())
    _add("system", "pipeline_runs", "error_count", sa.Integer())
    _add("system", "pipeline_runs", "source_version", sa.Text())
    _add("system", "pipeline_runs", "code_version", sa.Text())
    _add("system", "pipeline_runs", "model_version", sa.Text())
    _add("system", "pipeline_runs", "error_summary", sa.Text())
    op.create_index("ix_pipeline_runs_run_id", "pipeline_runs", ["run_id"],
                    unique=True, schema="system", postgresql_where=sa.text("run_id IS NOT NULL"))

    # ---- indicators: completeness + quality ----
    _add("aquavision", "water_indicators_weekly", "period_start", sa.Date())
    _add("aquavision", "water_indicators_weekly", "period_end", sa.Date())
    _add("aquavision", "water_indicators_weekly", "is_complete_period", sa.Boolean())
    _add("aquavision", "water_indicators_weekly", "coverage_percent", sa.Numeric())
    _add("aquavision", "water_indicators_weekly", "observation_count", sa.Integer())
    _add("aquavision", "water_indicators_weekly", "expected_observation_count", sa.Integer())
    _add("aquavision", "water_indicators_weekly", "quality_status", sa.Text())

    # ---- alerts: source attribution ----
    _add("aquavision", "water_alerts", "source", sa.Text())
    _add("aquavision", "water_alerts", "confidence", sa.Numeric())
    _add("aquavision", "water_alerts", "rule_version", sa.Text())

    # ---- predictions: forecast-vs-actual validation ----
    _add("aquavision", "water_predictions_weekly", "lower_bound", sa.Numeric())
    _add("aquavision", "water_predictions_weekly", "upper_bound", sa.Numeric())
    _add("aquavision", "water_predictions_weekly", "feature_version", sa.Text())
    _add("aquavision", "water_predictions_weekly", "training_cutoff", sa.Date())
    _add("aquavision", "water_predictions_weekly", "actual_value", sa.Numeric())
    _add("aquavision", "water_predictions_weekly", "error", sa.Numeric())
    _add("aquavision", "water_predictions_weekly", "validated_at", sa.DateTime(timezone=True))


def downgrade() -> None:
    for col in ("error_summary", "model_version", "code_version", "source_version",
                "error_count", "warning_count", "records_skipped", "records_written",
                "records_read", "data_period", "trigger_type", "run_id"):
        op.drop_column("pipeline_runs", col, schema="system")
    for col in ("quality_status", "expected_observation_count", "observation_count",
                "coverage_percent", "is_complete_period", "period_end", "period_start"):
        op.drop_column("water_indicators_weekly", col, schema="aquavision")
    for col in ("rule_version", "confidence", "source"):
        op.drop_column("water_alerts", col, schema="aquavision")
    for col in ("validated_at", "error", "actual_value", "training_cutoff",
                "feature_version", "upper_bound", "lower_bound"):
        op.drop_column("water_predictions_weekly", col, schema="aquavision")
    op.drop_index("ix_pipeline_runs_run_id", table_name="pipeline_runs", schema="system")