"""Setup DB: create all tables, views, stamp Alembic at 014. Reads DATABASE_URL from env."""
import os
import pathlib
import psycopg2

DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    print("DATABASE_URL not set — skipping schema setup")
    exit(0)

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

# 1. Create schemas
for s in ["aquavision", "shared", "system"]:
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
conn.commit()
print("Schemas OK")

# 2. Apply SQL migration (base tables)
sql = pathlib.Path("alembic/versions/000_recreate_base_tables.sql").read_text()
cur.execute(sql)
conn.commit()
print("Base tables OK")

# 3. Create extra tables
extras = [
    """CREATE TABLE IF NOT EXISTS aquavision.pipeline_runs (
        id BIGSERIAL PRIMARY KEY, pipeline_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running', started_at TIMESTAMPTZ DEFAULT NOW(),
        completed_at TIMESTAMPTZ, error_message TEXT,
        records_processed INTEGER DEFAULT 0, records_failed INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS aquavision.pipeline_run_stages (
        id BIGSERIAL PRIMARY KEY, run_id BIGINT REFERENCES aquavision.pipeline_runs(id),
        stage_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'running',
        started_at TIMESTAMPTZ DEFAULT NOW(), completed_at TIMESTAMPTZ, error_message TEXT)""",
    """CREATE TABLE IF NOT EXISTS aquavision.scheduler_heartbeats (
        id BIGSERIAL PRIMARY KEY, scheduler_name TEXT NOT NULL UNIQUE,
        last_heartbeat TIMESTAMPTZ DEFAULT NOW(), status TEXT DEFAULT 'active')""",
    """CREATE TABLE IF NOT EXISTS aquavision.data_quality_log (
        id BIGSERIAL PRIMARY KEY, observation_id BIGINT,
        quality_score NUMERIC, issues TEXT, checked_at TIMESTAMPTZ DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS aquavision.water_observation_quarantine (
        id BIGSERIAL PRIMARY KEY, observation_id BIGINT,
        reason TEXT, quarantined_at TIMESTAMPTZ DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS aquavision.notification_deliveries (
        id BIGSERIAL PRIMARY KEY, alert_id BIGINT, channel TEXT NOT NULL,
        status TEXT DEFAULT 'pending', delivered_at TIMESTAMPTZ, error_message TEXT)""",
    """CREATE TABLE IF NOT EXISTS aquavision.model_versions (
        id BIGSERIAL PRIMARY KEY, asset_id BIGINT REFERENCES aquavision.water_assets(id),
        model_type TEXT NOT NULL, model_path TEXT, metrics JSONB,
        trained_at TIMESTAMPTZ DEFAULT NOW(), is_active BOOLEAN DEFAULT true)""",
    """CREATE TABLE IF NOT EXISTS aquavision.water_indicators_weekly (
        id BIGSERIAL PRIMARY KEY, asset_id BIGINT, week_start DATE,
        avg_inflow NUMERIC, avg_outflow NUMERIC, max_inflow NUMERIC,
        min_inflow NUMERIC, source TEXT)""",
    """CREATE TABLE IF NOT EXISTS aquavision.water_predictions_weekly (
        id BIGSERIAL PRIMARY KEY, asset_id BIGINT, week_start DATE,
        predicted_inflow NUMERIC, predicted_outflow NUMERIC,
        horizon_days INTEGER, model_version TEXT)""",
    """CREATE TABLE IF NOT EXISTS shared.users (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW())""",
]

for ddl in extras:
    cur.execute(ddl)
conn.commit()
print("Extra tables OK")

# 4. Add source-aware columns if missing
for col in [
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_authority TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_publication_time TIMESTAMPTZ',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_parser_version TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_content_hash TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_priority INTEGER DEFAULT 4',
]:
    cur.execute(col)
cur.execute('CREATE INDEX IF NOT EXISTS ix_water_obs_source_authority ON aquavision.water_observations (source_authority)')
cur.execute('CREATE INDEX IF NOT EXISTS ix_water_obs_asset_date_source ON aquavision.water_observations (asset_id, observed_at DESC, source_priority)')
conn.commit()
print("Source-aware columns OK")

# 5. Create views
cur.execute('''CREATE OR REPLACE VIEW aquavision.v_best_observations AS
    SELECT DISTINCT ON (asset_id, observed_at, parameter)
        asset_id, observed_at, parameter, value, source, priority, data_origin, data_status, quality_status
    FROM (
        SELECT asset_id, observed_at, 'water_level_ft' as parameter, water_level_ft as value,
               source_authority as source, source_priority as priority, data_origin, data_status, quality_status
        FROM aquavision.water_observations WHERE water_level_ft IS NOT NULL
        UNION ALL
        SELECT asset_id, observed_at, 'inflow_cusecs', inflow_cusecs, source_authority, source_priority, data_origin, data_status, quality_status
        FROM aquavision.water_observations WHERE inflow_cusecs IS NOT NULL
        UNION ALL
        SELECT asset_id, observed_at, 'outflow_cusecs', outflow_cusecs, source_authority, source_priority, data_origin, data_status, quality_status
        FROM aquavision.water_observations WHERE outflow_cusecs IS NOT NULL
        UNION ALL
        SELECT asset_id, observed_at, 'discharge_cusecs', discharge_cusecs, source_authority, source_priority, data_origin, data_status, quality_status
        FROM aquavision.water_observations WHERE discharge_cusecs IS NOT NULL
    ) unpivoted ORDER BY asset_id, observed_at, parameter, priority ASC''')
conn.commit()
print("Views OK")

# 6. Stamp Alembic
cur.execute("CREATE TABLE IF NOT EXISTS aquavision.alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))")
cur.execute("INSERT INTO aquavision.alembic_version (version_num) VALUES ('014') ON CONFLICT DO NOTHING")
conn.commit()
print("Alembic stamped at 014")

cur.close()
conn.close()
print("DB setup complete!")
