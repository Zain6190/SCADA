"""16_pipeline_run_status_lifecycle

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-11 12:30:00.000000

Aligns system.pipeline_runs.status with the lifecycle used by
scripts/run_pipeline.py (and the orchestrator service):

    QUEUED -> RUNNING -> SUCCESS | PARTIAL_SUCCESS | FAILED

The initial init.sql baseline allowed only 'Success'/'Failed'/'Partial', which
would reject the new lifecycle values. Idempotent: drops the old CHECK (if the
name exists, i.e. DB was seeded from init.sql) and installs the new one.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system.pipeline_runs "
        "DROP CONSTRAINT IF EXISTS pipeline_runs_status_check"
    )
    op.execute(
        "ALTER TABLE system.pipeline_runs ADD CONSTRAINT pipeline_runs_status_check "
        "CHECK (status IN ('QUEUED','RUNNING','SUCCESS','PARTIAL_SUCCESS','FAILED'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE system.pipeline_runs "
        "DROP CONSTRAINT IF EXISTS pipeline_runs_status_check"
    )
    op.execute(
        "ALTER TABLE system.pipeline_runs ADD CONSTRAINT pipeline_runs_status_check "
        "CHECK (status IN ('Success','Failed','Partial'))"
    )
