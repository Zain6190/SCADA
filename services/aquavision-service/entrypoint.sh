#!/bin/bash
set -e

echo "=== IBCP-SCADA AquaVision Setup ==="

# 1. Apply SQL migration (creates all base tables)
echo "[1/4] Applying base schema..."
python -c "
import pathlib
from sqlalchemy import create_engine, text
url = '$DATABASE_URL'
sql = pathlib.Path('alembic/versions/000_recreate_base_tables.sql').read_text()
e = create_engine(url)
c = e.connect()
# Create schemas
for s in ['aquavision', 'shared', 'system']:
    c.execute(text(f'CREATE SCHEMA IF NOT EXISTS {s}'))
c.commit()
# Apply base tables
c.execute(text(sql))
c.commit()
# Create extra tables
for ddl in [
    'CREATE TABLE IF NOT EXISTS aquavision.pipeline_runs (id BIGSERIAL PRIMARY KEY, pipeline_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT \"running\", started_at TIMESTAMPTZ DEFAULT NOW(), completed_at TIMESTAMPTZ, error_message TEXT, records_processed INTEGER DEFAULT 0, records_failed INTEGER DEFAULT 0)',
    'CREATE TABLE IF NOT EXISTS aquavision.pipeline_run_stages (id BIGSERIAL PRIMARY KEY, run_id BIGINT REFERENCES aquavision.pipeline_runs(id), stage_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT \"running\", started_at TIMESTAMPTZ DEFAULT NOW(), completed_at TIMESTAMPTZ, error_message TEXT)',
    'CREATE TABLE IF NOT EXISTS aquavision.scheduler_heartbeats (id BIGSERIAL PRIMARY KEY, scheduler_name TEXT NOT NULL UNIQUE, last_heartbeat TIMESTAMPTZ DEFAULT NOW(), status TEXT DEFAULT \"active\")',
    'CREATE TABLE IF NOT EXISTS aquavision.data_quality_log (id BIGSERIAL PRIMARY KEY, observation_id BIGINT, quality_score NUMERIC, issues TEXT, checked_at TIMESTAMPTZ DEFAULT NOW())',
    'CREATE TABLE IF NOT EXISTS aquavision.water_observation_quarantine (id BIGSERIAL PRIMARY KEY, observation_id BIGINT, reason TEXT, quarantined_at TIMESTAMPTZ DEFAULT NOW())',
    'CREATE TABLE IF NOT EXISTS aquavision.notification_deliveries (id BIGSERIAL PRIMARY KEY, alert_id BIGINT, channel TEXT NOT NULL, status TEXT DEFAULT \"pending\", delivered_at TIMESTAMPTZ, error_message TEXT)',
    'CREATE TABLE IF NOT EXISTS aquavision.model_versions (id BIGSERIAL PRIMARY KEY, asset_id BIGINT REFERENCES aquavision.water_assets(id), model_type TEXT NOT NULL, model_path TEXT, metrics JSONB, trained_at TIMESTAMPTZ DEFAULT NOW(), is_active BOOLEAN DEFAULT true)',
    'CREATE TABLE IF NOT EXISTS aquavision.water_indicators_weekly (id BIGSERIAL PRIMARY KEY, asset_id BIGINT, week_start DATE, avg_inflow NUMERIC, avg_outflow NUMERIC, max_inflow NUMERIC, min_inflow NUMERIC, source TEXT)',
    'CREATE TABLE IF NOT EXISTS aquavision.water_predictions_weekly (id BIGSERIAL PRIMARY KEY, asset_id BIGINT, week_start DATE, predicted_inflow NUMERIC, predicted_outflow NUMERIC, horizon_days INTEGER, model_version TEXT)',
    'CREATE TABLE IF NOT EXISTS shared.users (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, is_active BOOLEAN DEFAULT true, created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW())',
]:
    c.execute(text(ddl))
c.commit()
# Add source-aware columns
for col in [
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_authority TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_publication_time TIMESTAMPTZ',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_parser_version TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_content_hash TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_priority INTEGER DEFAULT 4',
]:
    c.execute(text(col))
c.execute(text('CREATE INDEX IF NOT EXISTS ix_water_obs_source_authority ON aquavision.water_observations (source_authority)'))
c.execute(text('CREATE INDEX IF NOT EXISTS ix_water_obs_asset_date_source ON aquavision.water_observations (asset_id, observed_at DESC, source_priority)'))
c.commit()
# Create views
c.execute(text('''CREATE OR REPLACE VIEW aquavision.v_best_observations AS
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
    ) unpivoted ORDER BY asset_id, observed_at, parameter, priority ASC'''))
c.commit()
# Stamp Alembic
c.execute(text('CREATE TABLE IF NOT EXISTS aquavision.alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))'))
c.execute(text(\"INSERT INTO aquavision.alembic_version (version_num) VALUES ('014') ON CONFLICT DO NOTHING\"))
c.commit()
c.close()
print('Schema ready')
" || echo "Schema already applied or error (non-fatal)"

# 2. Seed water assets + auth users
echo "[2/4] Seeding database..."
python db/seed.py || echo "Seed failed or already seeded (non-fatal)"

# 3. Ingest Kaggle data
echo "[3/4] Ingesting Kaggle historical data..."
python -c "
from infrastructure.ingestion.kaggle_ingest import ingest_kaggle_csv
from infrastructure.db.engine import SessionLocal
import os

csv_path = 'data/raw/real/kaggle/pakistans_rivers_flow.csv'
if os.path.exists(csv_path):
    session = SessionLocal()
    try:
        from sqlalchemy import text
        count = session.execute(text('SELECT count(*) FROM aquavision.water_observations')).scalar()
        if count < 100:
            ingest_kaggle_csv(csv_path, session)
            print('Kaggle: loaded observations')
        else:
            print(f'Kaggle: already loaded ({count} observations)')
    finally:
        session.close()
else:
    print(f'Kaggle CSV not found at {csv_path} — skipping')
" || echo "Kaggle ingestion failed (non-fatal)"

# 4. Verify
echo "[4/4] Verifying..."
python -c "
from infrastructure.db.engine import SessionLocal
from sqlalchemy import text
s = SessionLocal()
a = s.execute(text('SELECT count(*) FROM aquavision.water_assets')).scalar()
o = s.execute(text('SELECT count(*) FROM aquavision.water_observations')).scalar()
u = s.execute(text('SELECT count(*) FROM shared.users')).scalar()
print(f'Assets: {a}, Observations: {o}, Users: {u}')
s.close()
" || echo "Verification skipped"

echo "=== Setup complete ==="
echo "Demo credentials: admin / admin123"

# Render provides $PORT, default to 8100 for local
PORT=${PORT:-8100}
exec uvicorn main:app --host 0.0.0.0 --port $PORT
