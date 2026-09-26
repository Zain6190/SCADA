"""Add Soft OT official-day replay tables.

Revision ID: 016
Revises: 015
Create Date: 2026-09-26
"""
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE aquavision.water_ot_devices
            ADD COLUMN IF NOT EXISTS control_mode TEXT NOT NULL DEFAULT 'TRACK',
            ADD COLUMN IF NOT EXISTS gate_cmd_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS fault_state TEXT
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.water_ot_process_days (
            id BIGSERIAL PRIMARY KEY,
            observed_on DATE NOT NULL,
            asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
            device_code TEXT NOT NULL,
            level_ft DOUBLE PRECISION,
            inflow_cusecs DOUBLE PRECISION,
            outflow_cusecs DOUBLE PRECISION,
            discharge_cusecs DOUBLE PRECISION,
            canal_offtake_cusecs DOUBLE PRECISION NOT NULL DEFAULT 0,
            gate_pct_derived DOUBLE PRECISION,
            source_authority TEXT NOT NULL,
            source_url TEXT,
            UNIQUE (observed_on, asset_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ot_process_days_date
        ON aquavision.water_ot_process_days (observed_on DESC)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.water_ot_runtime_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            cursor_date DATE,
            state_json JSONB,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT water_ot_runtime_state_singleton CHECK (id = 1)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.water_ot_divergences (
            id BIGSERIAL PRIMARY KEY,
            asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
            observed_on DATE NOT NULL,
            official_outflow DOUBLE PRECISION,
            scenario_outflow DOUBLE PRECISION,
            official_gate_pct DOUBLE PRECISION,
            scenario_gate_pct DOUBLE PRECISION,
            reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS aquavision.water_ot_divergences")
    op.execute("DROP TABLE IF EXISTS aquavision.water_ot_runtime_state")
    op.execute("DROP TABLE IF EXISTS aquavision.water_ot_process_days")
    op.execute("ALTER TABLE aquavision.water_ot_devices DROP COLUMN IF EXISTS fault_state")
    op.execute("ALTER TABLE aquavision.water_ot_devices DROP COLUMN IF EXISTS gate_cmd_pct")
    op.execute("ALTER TABLE aquavision.water_ot_devices DROP COLUMN IF EXISTS control_mode")
