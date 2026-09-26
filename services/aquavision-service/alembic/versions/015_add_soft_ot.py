"""Add Soft OT devices, tags, values, commands, and SOFT_OT source.

Revision ID: 015
Revises: 014
Create Date: 2026-09-20
"""
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO aquavision.water_sources
            (authority, source_url, source_type, update_frequency, description)
        VALUES
            ('SOFT_OT', 'soft-ot-runtime', 'SIMULATED_OT', 'SUB_DAILY',
             'Software PLC/RTU runtime — simulated telemetry, data_origin=SYNTHETIC, never displaces IRSA/FFD')
        ON CONFLICT (authority) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            source_type = EXCLUDED.source_type,
            update_frequency = EXCLUDED.update_frequency,
            description = EXCLUDED.description
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.water_ot_devices (
            id BIGSERIAL PRIMARY KEY,
            device_code TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK (kind IN ('RTU', 'PLC')),
            asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
            scan_ms INTEGER NOT NULL,
            publish_s INTEGER NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            comms_ok BOOLEAN NOT NULL DEFAULT TRUE,
            last_scan_at TIMESTAMPTZ,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.water_ot_tags (
            id BIGSERIAL PRIMARY KEY,
            device_id BIGINT NOT NULL REFERENCES aquavision.water_ot_devices(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            tag_class TEXT NOT NULL CHECK (tag_class IN ('AI', 'DI', 'AO', 'DO')),
            unit TEXT,
            description TEXT,
            UNIQUE (device_id, name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.water_ot_tag_values (
            id BIGSERIAL PRIMARY KEY,
            tag_id BIGINT NOT NULL REFERENCES aquavision.water_ot_tags(id) ON DELETE CASCADE,
            value DOUBLE PRECISION,
            quality TEXT NOT NULL DEFAULT 'VALID',
            observed_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ot_tag_values_tag_time
        ON aquavision.water_ot_tag_values (tag_id, observed_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS aquavision.water_ot_commands (
            id BIGSERIAL PRIMARY KEY,
            device_id BIGINT NOT NULL REFERENCES aquavision.water_ot_devices(id) ON DELETE CASCADE,
            asset_id BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
            tag_name TEXT NOT NULL,
            value DOUBLE PRECISION,
            action TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'virtual-hmi',
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ot_commands_device_time
        ON aquavision.water_ot_commands (device_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ot_devices_asset
        ON aquavision.water_ot_devices (asset_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS aquavision.water_ot_commands")
    op.execute("DROP TABLE IF EXISTS aquavision.water_ot_tag_values")
    op.execute("DROP TABLE IF EXISTS aquavision.water_ot_tags")
    op.execute("DROP TABLE IF EXISTS aquavision.water_ot_devices")
    op.execute("DELETE FROM aquavision.water_sources WHERE authority = 'SOFT_OT'")
