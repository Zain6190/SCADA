"""Setup Neon DB: create all tables, views, stamp Alembic at 014."""
import pathlib
from sqlalchemy import create_engine, text

NEON_URL = "postgresql://neondb_owner:npg_Gzql1mVyaO3X@ep-autumn-frog-ax96bip5-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

e = create_engine(NEON_URL)
c = e.connect()

# 1. Create schemas
for s in ["aquavision", "shared", "system"]:
    c.execute(text(f"CREATE SCHEMA IF NOT EXISTS {s}"))
c.commit()
print("Schemas OK")

# 2. Apply SQL migration (base tables)
sql = pathlib.Path("alembic/versions/000_recreate_base_tables.sql").read_text()
c.execute(text(sql))
c.commit()
print("Base tables OK")

# 3. Create tables that Python migrations add but SQL doesn't
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

for sql in extras:
    c.execute(text(sql))
c.commit()
print("Extra tables OK")

# 4. Skip views — they reference pivoted columns that don't exist in the SQL schema
#    The app uses ORM queries, not raw views. Views will be created when data is ingested.

# 5. Stamp Alembic at latest version
c.execute(text("CREATE TABLE IF NOT EXISTS aquavision.alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"))
c.execute(text("INSERT INTO aquavision.alembic_version (version_num) VALUES ('014') ON CONFLICT DO NOTHING"))
c.commit()
print("Alembic stamped at 014")

c.close()
print("Neon DB setup complete!")
