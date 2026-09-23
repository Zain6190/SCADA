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

# Canal offtake readings are written by the IRSA ingestion pipeline.
cur.execute("""
    CREATE TABLE IF NOT EXISTS aquavision.water_canal_observations (
        id BIGSERIAL PRIMARY KEY,
        asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
        source_id BIGINT NOT NULL REFERENCES aquavision.water_sources(id),
        canal_label TEXT NOT NULL,
        is_aggregate BOOLEAN NOT NULL DEFAULT FALSE,
        observed_at TIMESTAMPTZ NOT NULL,
        discharge_cusecs NUMERIC NOT NULL,
        data_status TEXT NOT NULL DEFAULT 'OBSERVED_OFFICIAL',
        data_origin TEXT NOT NULL DEFAULT 'REAL',
        quality_status TEXT NOT NULL DEFAULT 'VALID',
        raw_record_id BIGINT REFERENCES aquavision.raw_source_records(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (asset_id, canal_label, observed_at, source_id)
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_canal_obs_label_time ON aquavision.water_canal_observations (canal_label, observed_at DESC)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_canal_obs_asset ON aquavision.water_canal_observations (asset_id, observed_at DESC)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_canal_obs_dry ON aquavision.water_canal_observations (canal_label, observed_at DESC) WHERE discharge_cusecs = 0")
conn.commit()
print("Canal observation tables OK")

# 3. Create extra tables.
#    ORDER MATTERS: FK targets (shared.users, shared.regions, shared.assets,
#    aquavision.pipeline_runs) are created before anything that references them.
extras = [
    # ── shared.users (full access-lifecycle shape; FK target) ──────────────
    """CREATE TABLE IF NOT EXISTS shared.users (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),
        access_status TEXT NOT NULL DEFAULT 'ACTIVE',
        access_requested_at TIMESTAMPTZ,
        last_login_at TIMESTAMPTZ)""",
    # ── RBAC reference tables ──────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS shared.roles (
        id BIGSERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT)""",
    """CREATE TABLE IF NOT EXISTS shared.permissions (
        id BIGSERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT)""",
    # ── regions (FK target for assets, scopes, water_* tables) ─────────────
    """CREATE TABLE IF NOT EXISTS shared.regions (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
        type TEXT NOT NULL DEFAULT 'province', parent_region_id BIGINT REFERENCES shared.regions(id),
        geom geometry(MultiPolygon,4326) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())""",
    """INSERT INTO shared.regions (name, code, type, geom) VALUES
        ('Khyber Pakhtunkhwa','KPK','province', ST_Multi(ST_MakeEnvelope(69.5,33.5,75.0,37.0,4326))),
        ('Punjab','PUN','province', ST_Multi(ST_MakeEnvelope(71.0,30.0,76.0,34.5,4326))),
        ('Sindh','SIN','province', ST_Multi(ST_MakeEnvelope(67.0,23.5,71.0,28.5,4326))),
        ('Balochistan','BAL','province', ST_Multi(ST_MakeEnvelope(61.0,24.5,70.5,31.0,4326))),
        ('Azad Kashmir','AJK','province', ST_Multi(ST_MakeEnvelope(72.0,33.0,75.5,35.5,4326))),
        ('Gilgit-Baltistan','GB','province', ST_Multi(ST_MakeEnvelope(73.5,34.5,76.5,37.0,4326))),
        ('Islamabad','ISB','province', ST_Multi(ST_MakeEnvelope(72.8,33.3,73.5,34.0,4326)))
        ON CONFLICT (code) DO NOTHING""",
    # ── RBAC association tables ────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS shared.user_roles (
        user_id BIGINT NOT NULL REFERENCES shared.users(id),
        role_id BIGINT NOT NULL REFERENCES shared.roles(id),
        PRIMARY KEY (user_id, role_id))""",
    """CREATE TABLE IF NOT EXISTS shared.role_permissions (
        role_id BIGINT NOT NULL REFERENCES shared.roles(id),
        permission_id BIGINT NOT NULL REFERENCES shared.permissions(id),
        PRIMARY KEY (role_id, permission_id))""",
    """CREATE TABLE IF NOT EXISTS shared.assets (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, asset_type TEXT NOT NULL,
        region_id BIGINT REFERENCES shared.regions(id),
        geom geometry(Polygon,4326) NOT NULL,
        source TEXT, is_active BOOLEAN NOT NULL DEFAULT true,
        metadata JSONB)""",
    "CREATE INDEX IF NOT EXISTS idx_assets_geom ON shared.assets USING gist (geom)",
    """CREATE TABLE IF NOT EXISTS shared.user_region_scopes (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES shared.users(id),
        scope_type TEXT NOT NULL CHECK (scope_type IN ('NATIONAL','PROVINCE','DISTRICT','ASSET')),
        region_id BIGINT REFERENCES shared.regions(id),
        asset_id BIGINT REFERENCES shared.assets(id),
        granted_by BIGINT REFERENCES shared.users(id),
        granted_at TIMESTAMPTZ DEFAULT now(),
        expires_at TIMESTAMPTZ,
        is_active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now(),
        CHECK (
            (scope_type = 'NATIONAL' AND region_id IS NULL AND asset_id IS NULL) OR
            (scope_type IN ('PROVINCE','DISTRICT') AND region_id IS NOT NULL AND asset_id IS NULL) OR
            (scope_type = 'ASSET' AND asset_id IS NOT NULL AND region_id IS NULL)
        ))""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_user_region_scope_active
        ON shared.user_region_scopes (user_id, scope_type, region_id, asset_id)
        WHERE is_active""",
    # ── system.audit_logs (FK target: shared.users) ────────────────────────
    """CREATE TABLE IF NOT EXISTS system.audit_logs (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT REFERENCES shared.users(id),
        action TEXT NOT NULL,
        entity_type TEXT, entity_id TEXT,
        details JSONB,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
        ip_address TEXT,
        role TEXT, module TEXT, resource_type TEXT, resource_id TEXT,
        region_id BIGINT,
        before_value JSONB, after_value JSONB,
        result TEXT, request_id TEXT, user_agent TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON system.audit_logs (timestamp)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_user ON system.audit_logs (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_module ON system.audit_logs (module)",
    # ── aquavision operational tables ──────────────────────────────────────
    # Full pipeline_runs shape (alembic 006) — required by the scheduler.
    """CREATE TABLE IF NOT EXISTS aquavision.pipeline_runs (
        id BIGSERIAL PRIMARY KEY,
        run_id VARCHAR(50) NOT NULL UNIQUE,
        pipeline_type VARCHAR(20) NOT NULL,
        status VARCHAR(20) NOT NULL,
        trigger_type VARCHAR(20) NOT NULL,
        lock_key VARCHAR(100),
        code_version VARCHAR(50), config_version VARCHAR(50),
        source_version VARCHAR(50), log_path VARCHAR(500),
        started_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ,
        duration_seconds DOUBLE PRECISION,
        error_message TEXT,
        retry_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_pipeline_type ON aquavision.pipeline_runs (pipeline_type)",
    "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_status ON aquavision.pipeline_runs (status)",
    "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started_at ON aquavision.pipeline_runs (started_at)",
    # Full pipeline_run_stages shape (alembic 006).
    """CREATE TABLE IF NOT EXISTS aquavision.pipeline_run_stages (
        id BIGSERIAL PRIMARY KEY,
        run_id VARCHAR(50) NOT NULL REFERENCES aquavision.pipeline_runs(run_id),
        stage_name VARCHAR(50) NOT NULL,
        status VARCHAR(20) NOT NULL,
        started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
        records_fetched INTEGER NOT NULL DEFAULT 0,
        records_stored INTEGER NOT NULL DEFAULT 0,
        records_skipped INTEGER NOT NULL DEFAULT 0,
        records_invalid INTEGER NOT NULL DEFAULT 0,
        warning_count INTEGER NOT NULL DEFAULT 0,
        error_message TEXT, log_path VARCHAR(500),
        created_at TIMESTAMPTZ DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_pipeline_run_stages_run_id ON aquavision.pipeline_run_stages (run_id)",
    # Full scheduler_heartbeats shape (alembic 007) — required by the scheduler.
    """CREATE TABLE IF NOT EXISTS aquavision.scheduler_heartbeats (
        id BIGSERIAL PRIMARY KEY,
        service_name VARCHAR(50) NOT NULL,
        instance_id VARCHAR(100) NOT NULL,
        host_name VARCHAR(100), container_id VARCHAR(100),
        version VARCHAR(50), process_id INTEGER,
        started_at TIMESTAMPTZ,
        last_heartbeat_at TIMESTAMPTZ NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (service_name, instance_id))""",
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
    """CREATE TABLE IF NOT EXISTS aquavision.weather_forecasts (
        id BIGSERIAL PRIMARY KEY,
        asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
        forecast_date DATE NOT NULL,
        horizon_days INTEGER NOT NULL,
        precip_sum_mm NUMERIC, temp_max_c NUMERIC, temp_min_c NUMERIC,
        humidity_mean_pct NUMERIC, wind_speed_kmh NUMERIC,
        fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (asset_id, forecast_date, horizon_days))""",
    # water_indicators_weekly with SPI columns (was backend migration 19).
    """CREATE TABLE IF NOT EXISTS aquavision.water_indicators_weekly (
        id BIGSERIAL PRIMARY KEY, region_id BIGINT NOT NULL REFERENCES shared.regions(id),
        week_start_date DATE NOT NULL, week_number INTEGER, year INTEGER,
        surface_water_area_km2 NUMERIC, surface_water_change_pct NUMERIC,
        rainfall_mm_30day NUMERIC, rainfall_anomaly NUMERIC,
        et_mm_8day NUMERIC, et_anomaly NUMERIC,
        spi_1 NUMERIC, spi_3 NUMERIC, spi_6 NUMERIC, spi_12 NUMERIC,
        spi_drought_class VARCHAR(20),
        wai_score NUMERIC,
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
    # surface_water_weekly (was backend migration 18; written by ml-pipeline
    # scripts/sync_surface_water.py). FK -> shared.regions, so it lives here
    # (after regions), not in 000_recreate_base_tables.sql.
    """CREATE TABLE IF NOT EXISTS aquavision.surface_water_weekly (
        id SERIAL PRIMARY KEY,
        region_id INTEGER NOT NULL REFERENCES shared.regions(id),
        week_start_date DATE NOT NULL,
        ndwi_mean DOUBLE PRECISION, mndwi_mean DOUBLE PRECISION,
        water_area_km2 DOUBLE PRECISION,
        prev_water_area_km2 DOUBLE PRECISION,
        change_pct DOUBLE PRECISION, cloud_pct DOUBLE PRECISION,
        data_status VARCHAR(20) NOT NULL DEFAULT 'processed',
        source_version VARCHAR(64),
        created_at TIMESTAMPTZ DEFAULT now(),
        CONSTRAINT uq_surface_water_region_week UNIQUE (region_id, week_start_date))""",
    "CREATE INDEX IF NOT EXISTS ix_sw_region_date ON aquavision.surface_water_weekly (region_id, week_start_date)",
    "CREATE INDEX IF NOT EXISTS ix_sw_week ON aquavision.surface_water_weekly (week_start_date)",
]

errors = []
for ddl in extras:
    try:
        cur.execute(ddl)
        conn.commit()
    except Exception as e:
        conn.rollback()
        msg = str(e).split("\n")[0]
        errors.append(msg)
        print(f"Extra DDL failed (continuing): {msg}")
if errors:
    print(f"Extra tables: {len(errors)} statement(s) failed")
else:
    print("Extra tables OK")

# 3b. RBAC seed (idempotent): permissions, roles, role->permission grants,
#     bootstrap admin user + role + NATIONAL scope. Live DBs already have
#     these rows (ON CONFLICT / WHERE NOT EXISTS no-op).
rbac_seed = [
    """INSERT INTO shared.permissions (name, description) VALUES
        ('AQUAVISION_READ','Read water monitoring data'),
        ('AQUAVISION_ANALYZE','Run analysis on water data'),
        ('AQUAVISION_EXPORT','Export water reports and data'),
        ('AQUAVISION_ACKNOWLEDGE_ALERT','Acknowledge operational alerts'),
        ('AQUAVISION_ADD_NOTE','Add operator notes to assets/alerts'),
        ('AQUAVISION_APPROVE_REPORT','Approve generated reports'),
        ('AQUAVISION_MANAGE_DATA','Create/edit reference and observation data'),
        ('AQUAVISION_CONFIGURE','Configure thresholds and system settings'),
        ('AQUAVISION_MANAGE_USERS','Manage user accounts'),
        ('AQUAVISION_ESCALATE_ALERT','Escalate alerts to supervisors'),
        ('AQUAVISION_RESOLVE_ALERT','Resolve operational alerts'),
        ('AQUAVISION_SEND_INSTRUCTION','Send field instructions'),
        ('AQUAVISION_VERIFY_RESPONSE','Verify operational response'),
        ('CROP_READ','Read crop intelligence data'),
        ('CROP_TRAIN_MODEL','Train crop models'),
        ('GEOVISION_READ','Read geospatial layers'),
        ('MANAGE_OPERATORS','Create and approve operator accounts within the caller-owned scope'),
        ('SYSTEM_ADMIN','Full system administration')
        ON CONFLICT (name) DO NOTHING""",
    """INSERT INTO shared.roles (name, description) VALUES
        ('admin','System administrator'),
        ('aquavision_analyst','Water monitoring analyst'),
        ('crop_analyst','Crop yield analyst'),
        ('field_officer','Field operations officer'),
        ('geo_analyst','Geospatial analyst'),
        ('viewer','Read-only viewer'),
        ('water_supervisor','Supervisor role: coordinates and verifies operational response')
        ON CONFLICT (name) DO NOTHING""",
    """INSERT INTO shared.role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM (VALUES
            ('admin','AQUAVISION_READ'),('admin','AQUAVISION_MANAGE_DATA'),
            ('admin','AQUAVISION_CONFIGURE'),('admin','AQUAVISION_EXPORT'),
            ('admin','AQUAVISION_ACKNOWLEDGE_ALERT'),('admin','AQUAVISION_RESOLVE_ALERT'),
            ('admin','AQUAVISION_ESCALATE_ALERT'),('admin','AQUAVISION_SEND_INSTRUCTION'),
            ('admin','AQUAVISION_VERIFY_RESPONSE'),('admin','AQUAVISION_APPROVE_REPORT'),
            ('admin','CROP_READ'),('admin','CROP_TRAIN_MODEL'),
            ('admin','GEOVISION_READ'),('admin','MANAGE_OPERATORS'),
            ('admin','SYSTEM_ADMIN'),
            ('aquavision_analyst','AQUAVISION_READ'),
            ('aquavision_analyst','AQUAVISION_ANALYZE'),
            ('aquavision_analyst','AQUAVISION_EXPORT'),
            ('field_officer','AQUAVISION_READ'),
            ('field_officer','AQUAVISION_ACKNOWLEDGE_ALERT'),
            ('field_officer','AQUAVISION_ADD_NOTE'),
            ('viewer','AQUAVISION_READ'),
            ('water_supervisor','AQUAVISION_READ'),
            ('water_supervisor','AQUAVISION_ANALYZE'),
            ('water_supervisor','AQUAVISION_EXPORT'),
            ('water_supervisor','AQUAVISION_ACKNOWLEDGE_ALERT'),
            ('water_supervisor','AQUAVISION_ADD_NOTE'),
            ('water_supervisor','AQUAVISION_ESCALATE_ALERT'),
            ('water_supervisor','AQUAVISION_RESOLVE_ALERT'),
            ('water_supervisor','AQUAVISION_SEND_INSTRUCTION'),
            ('water_supervisor','AQUAVISION_VERIFY_RESPONSE'),
            ('water_supervisor','AQUAVISION_APPROVE_REPORT'),
            ('water_supervisor','MANAGE_OPERATORS')
        ) AS t(role, perm)
        JOIN shared.roles r ON r.name = t.role
        JOIN shared.permissions p ON p.name = t.perm
        ON CONFLICT DO NOTHING""",
    # Bootstrap admin (admin / admin123). Same bcrypt hash as the live DB.
    """INSERT INTO shared.users (name, email, password_hash, is_active, access_status)
        VALUES ('System Admin', 'admin@ibcp.gov.pk',
                '$2b$12$DTWqOOxw1CyxwyEUBh8dF.TQRKHpOrVrpZErgLGKjqoIwAdkbpZSu',
                true, 'ACTIVE')
        ON CONFLICT (email) DO NOTHING""",
    """INSERT INTO shared.user_roles (user_id, role_id)
        SELECT u.id, r.id FROM shared.users u, shared.roles r
        WHERE u.email = 'admin@ibcp.gov.pk' AND r.name = 'admin'
        ON CONFLICT DO NOTHING""",
    """INSERT INTO shared.user_region_scopes (user_id, scope_type, is_active)
        SELECT u.id, 'NATIONAL', true FROM shared.users u
        WHERE u.email = 'admin@ibcp.gov.pk'
          AND NOT EXISTS (
              SELECT 1 FROM shared.user_region_scopes s
              WHERE s.user_id = u.id AND s.scope_type = 'NATIONAL' AND s.is_active)
    """,
]
rbac_errors = []
for ddl in rbac_seed:
    try:
        cur.execute(ddl)
        conn.commit()
    except Exception as e:
        conn.rollback()
        msg = str(e).split("\n")[0]
        rbac_errors.append(msg)
        print(f"RBAC seed failed (continuing): {msg}")
if rbac_errors:
    print(f"RBAC seed: {len(rbac_errors)} statement(s) failed")
else:
    print("RBAC seed OK")

# 4. Add source-aware columns if missing
for col in [
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_authority TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_publication_time TIMESTAMPTZ',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_parser_version TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_content_hash TEXT',
    'ALTER TABLE aquavision.water_observations ADD COLUMN IF NOT EXISTS source_priority INTEGER DEFAULT 4',
    # SPI columns on pre-existing water_indicators_weekly (backend migration 19)
    'ALTER TABLE aquavision.water_indicators_weekly ADD COLUMN IF NOT EXISTS spi_1 NUMERIC',
    'ALTER TABLE aquavision.water_indicators_weekly ADD COLUMN IF NOT EXISTS spi_3 NUMERIC',
    'ALTER TABLE aquavision.water_indicators_weekly ADD COLUMN IF NOT EXISTS spi_6 NUMERIC',
    'ALTER TABLE aquavision.water_indicators_weekly ADD COLUMN IF NOT EXISTS spi_12 NUMERIC',
    'ALTER TABLE aquavision.water_indicators_weekly ADD COLUMN IF NOT EXISTS spi_drought_class VARCHAR(20)',
    # Access-lifecycle columns on pre-existing shared.users (backend migrations 10/13)
    "ALTER TABLE shared.users ADD COLUMN IF NOT EXISTS access_status TEXT NOT NULL DEFAULT 'ACTIVE'",
    'ALTER TABLE shared.users ADD COLUMN IF NOT EXISTS access_requested_at TIMESTAMPTZ',
    'ALTER TABLE shared.users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ',
]:
    cur.execute(col)
cur.execute('CREATE INDEX IF NOT EXISTS ix_water_obs_source_authority ON aquavision.water_observations (source_authority)')
cur.execute('CREATE INDEX IF NOT EXISTS ix_water_obs_asset_date_source ON aquavision.water_observations (asset_id, observed_at DESC, source_priority)')
conn.commit()
print("Source-aware columns OK")

# 5. Create views (canonical definitions: alembic/versions/014_create_source_aware_views.sql)
cur.execute("DROP VIEW IF EXISTS aquavision.v_best_observations")
cur.execute('''CREATE VIEW aquavision.v_best_observations AS
    WITH unpivoted AS (
        SELECT asset_id, observed_at::date AS observed_at, 'level' AS parameter,
               water_level_ft AS value, source_authority AS source,
               COALESCE(source_priority, 99) AS priority, data_origin
        FROM aquavision.water_observations WHERE water_level_ft IS NOT NULL
        UNION ALL
        SELECT asset_id, observed_at::date, 'inflow', inflow_cusecs, source_authority,
               COALESCE(source_priority, 99), data_origin
        FROM aquavision.water_observations WHERE inflow_cusecs IS NOT NULL
        UNION ALL
        SELECT asset_id, observed_at::date, 'outflow', outflow_cusecs, source_authority,
               COALESCE(source_priority, 99), data_origin
        FROM aquavision.water_observations WHERE outflow_cusecs IS NOT NULL
        UNION ALL
        SELECT asset_id, observed_at::date, 'discharge', discharge_cusecs, source_authority,
               COALESCE(source_priority, 99), data_origin
        FROM aquavision.water_observations WHERE discharge_cusecs IS NOT NULL
    ),
    ranked AS (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY asset_id, observed_at, parameter
            ORDER BY priority ASC, observed_at DESC
        ) AS rn
        FROM unpivoted WHERE value IS NOT NULL
    )
    SELECT asset_id, observed_at, parameter, value, source, priority, data_origin
    FROM ranked WHERE rn = 1''')
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
