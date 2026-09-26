-- Official IRSA/FFD days for Soft OT replay, plus cursor and scenario divergence.
-- Alembic equivalent: alembic/versions/016_add_ot_process_days.py
-- Run: docker exec -i ibcp-postgis psql -U postgres -d ibcp_scada < migrations/017_ot_process_days.sql

ALTER TABLE aquavision.water_ot_devices
    ADD COLUMN IF NOT EXISTS control_mode TEXT NOT NULL DEFAULT 'TRACK',
    ADD COLUMN IF NOT EXISTS gate_cmd_pct DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fault_state TEXT;

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
);

CREATE INDEX IF NOT EXISTS idx_ot_process_days_date
    ON aquavision.water_ot_process_days (observed_on DESC);

CREATE TABLE IF NOT EXISTS aquavision.water_ot_runtime_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    cursor_date DATE,
    state_json JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT water_ot_runtime_state_singleton CHECK (id = 1)
);

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
);
