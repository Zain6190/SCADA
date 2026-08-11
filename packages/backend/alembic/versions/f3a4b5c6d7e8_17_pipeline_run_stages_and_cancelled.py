"""17_pipeline_run_stages_and_cancelled

Revision ID: f3a4b5c6d7e8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-11 13:00:00.000000

- Adds CANCELLED to system.pipeline_runs.status (operator cancellation /
  pre-start abort).
- Creates system.pipeline_run_stages: one row per run per stage with status,
  record counts, timing and log path - the base for the admin dashboard,
  per-stage retry and stage-level alerting.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system.pipeline_runs "
        "DROP CONSTRAINT IF EXISTS pipeline_runs_status_check"
    )
    op.execute(
        "ALTER TABLE system.pipeline_runs ADD CONSTRAINT pipeline_runs_status_check "
        "CHECK (status IN ('QUEUED','RUNNING','SUCCESS','PARTIAL_SUCCESS','FAILED','CANCELLED'))"
    )
    op.create_table(
        "pipeline_run_stages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_pk", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("stage_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_read", sa.Integer(), nullable=True),
        sa.Column("records_written", sa.Integer(), nullable=True),
        sa.Column("records_skipped", sa.Integer(), nullable=True),
        sa.Column("warning_count", sa.Integer(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=True),
        sa.Column("log_path", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('SUCCESS','PARTIAL_SUCCESS','FAILED','SKIPPED','CANCELLED')",
            name="pipeline_run_stages_status_check",
        ),
        sa.ForeignKeyConstraint(["run_pk"], ["system.pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "stage_name", name="uq_pipeline_run_stages_run_stage"),
        schema="system",
    )


def downgrade() -> None:
    op.drop_table("pipeline_run_stages", schema="system")
    op.execute(
        "ALTER TABLE system.pipeline_runs "
        "DROP CONSTRAINT IF EXISTS pipeline_runs_status_check"
    )
    op.execute(
        "ALTER TABLE system.pipeline_runs ADD CONSTRAINT pipeline_runs_status_check "
        "CHECK (status IN ('QUEUED','RUNNING','SUCCESS','PARTIAL_SUCCESS','FAILED'))"
    )
