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
    """CREATE TABLE IF NOT EXISTS shared.regions (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
        type TEXT NOT NULL DEFAULT 'province', parent_region_id BIGINT REFERENCES shared.regions(id),
        created_at TIMESTAMPTZ DEFAULT now())""",
    """INSERT INTO shared.regions (name, code, type) VALUES
        ('Khyber Pakhtunkhwa','KPK','province'),('Punjab','PUN','province'),
        ('Sindh','SIN','province'),('Balochistan','BAL','province'),
        ('Azad Kashmir','AJK','province'),('Gilgit-Baltistan','GB','province'),
        ('Islamabad','ISB','territory') ON CONFLICT (code) DO NOTHING""",
    """CREATE TABLE IF NOT EXISTS aquavision.water_indicators_weekly (
        id BIGSERIAL PRIMARY KEY, region_id BIGINT NOT NULL REFERENCES shared.regions(id),
        week_start_date DATE NOT NULL, week_number INTEGER, year INTEGER,
        surface_water_area_km2 NUMERIC, surface_water_change_pct NUMERIC,
        rainfall_mm_30day NUMERIC, rainfall_anomaly NUMERIC,
        et_mm_8day NUMERIC, et_anomaly NUMERIC, wai_score NUMERIC,
        severity TEXT, data_source_version TEXT,
        created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (region_id, week_start_date))""",
    """CREATE TABLE IF NOT EXISTS aquavision.water_predictions_weekly (
        id BIGSERIAL PRIMARY KEY, region_id BIGINT NOT NULL REFERENCES shared.regions(id),
        target_week_start_date DATE NOT NULL, model_type TEXT, model_version TEXT NOT NULL,
        predicted_severity TEXT, predicted_wai_score NUMERIC, confidence NUMERIC,
        created_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (region_id, target_week_start_date, model_version))""",
    """CREATE TABLE IF NOT EXISTS aquavision.water_alerts (
        id BIGSERIAL PRIMARY KEY, region_id BIGINT NOT NULL REFERENCES shared.regions(id),
        week_start_date DATE NOT NULL, alert_type TEXT NOT NULL, severity TEXT NOT NULL,
        alert_source TEXT NOT NULL DEFAULT 'WAI_MODEL', alert_domain TEXT NOT NULL DEFAULT 'WATER_STRESS',
        model_version TEXT, wai_score NUMERIC, rainfall_anomaly NUMERIC, et_anomaly NUMERIC,
        surface_water_change_pct NUMERIC, status TEXT DEFAULT 'New',
        assigned_to_user_id BIGINT REFERENCES shared.users(id),
        created_at TIMESTAMPTZ DEFAULT now(), acknowledged_at TIMESTAMPTZ,
        resolved_at TIMESTAMPTZ, notes TEXT)""",
    """CREATE TABLE IF NOT EXISTS aquavision.water_reports (
        id BIGSERIAL PRIMARY KEY, week_start_date DATE NOT NULL,
        title TEXT NOT NULL, scope TEXT NOT NULL,
        region_id BIGINT REFERENCES shared.regions(id),
        file_path TEXT, generated_by_user_id BIGINT REFERENCES shared.users(id),
        generated_at TIMESTAMPTZ DEFAULT now(), status TEXT DEFAULT 'Success')""",
    """CREATE TABLE IF NOT EXISTS aquavision.water_thresholds (
        id BIGSERIAL PRIMARY KEY, threshold_name TEXT NOT NULL UNIQUE,
        value NUMERIC NOT NULL, description TEXT,
        updated_at TIMESTAMPTZ DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS shared.users (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())""",
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
