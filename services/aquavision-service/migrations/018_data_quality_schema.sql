-- 018: Align data-quality tables with the ORM models / alembic 008.
-- These tables were created by db/setup_neon.py with an older shape
-- (quality_score/issues and reason/quarantined_at); alembic never runs,
-- so ORM SELECTs/INSERTs failed with UndefinedColumn (threshold evaluation
-- after SOFT_OT publish logged this on every tick).
-- Columns are added as nullable: the ORM always supplies the required
-- values on insert, and this stays safe on non-empty deployments.

ALTER TABLE aquavision.data_quality_log
    ADD COLUMN IF NOT EXISTS asset_id             BIGINT,
    ADD COLUMN IF NOT EXISTS check_type           VARCHAR(50),
    ADD COLUMN IF NOT EXISTS field_name           VARCHAR(50),
    ADD COLUMN IF NOT EXISTS raw_value            DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS expected_range_min   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS expected_range_max   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS quality_status       VARCHAR(20),
    ADD COLUMN IF NOT EXISTS details              TEXT,
    ADD COLUMN IF NOT EXISTS source_record_id     INTEGER,
    ADD COLUMN IF NOT EXISTS created_at           TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS ix_data_quality_log_asset_id
    ON aquavision.data_quality_log (asset_id);
CREATE INDEX IF NOT EXISTS ix_data_quality_log_check_type
    ON aquavision.data_quality_log (check_type);

ALTER TABLE aquavision.water_observation_quarantine
    ADD COLUMN IF NOT EXISTS asset_id           INTEGER,
    ADD COLUMN IF NOT EXISTS source_record_id   INTEGER,
    ADD COLUMN IF NOT EXISTS raw_payload        JSON,
    ADD COLUMN IF NOT EXISTS parsed_values      JSON,
    ADD COLUMN IF NOT EXISTS failure_reason     TEXT,
    ADD COLUMN IF NOT EXISTS field_name         VARCHAR(50),
    ADD COLUMN IF NOT EXISTS raw_value          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS parser_version     VARCHAR(50),
    ADD COLUMN IF NOT EXISTS data_status        VARCHAR(30),
    ADD COLUMN IF NOT EXISTS created_at         TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS ix_quarantine_asset_id
    ON aquavision.water_observation_quarantine (asset_id);
