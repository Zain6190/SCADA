-- migrations/006_water_channels.sql
-- Module 6.4: river and canal condition layer.
--
-- water_river_network (004) models CONNECTIVITY between assets - which barrage
-- is downstream of which, and how long a flood wave takes to travel. It has no
-- geometry and should keep it that way. This adds the spatial layer alongside it.
--
-- Geometry is MultiLineString, not Polygon: a channel is a line. The single
-- pre-existing canal in shared.assets was seeded as a bounding-box POLYGON,
-- which cannot express a channel's course.

-- ============================================================
-- water_channels: river and canal geometry
-- ============================================================
CREATE TABLE IF NOT EXISTS aquavision.water_channels (
    id              BIGSERIAL PRIMARY KEY,
    channel_type    TEXT NOT NULL CHECK (channel_type IN ('river', 'canal', 'link_canal')),
    name            TEXT NOT NULL,
    osm_id          BIGINT,                 -- provenance back to OpenStreetMap
    river_basin     TEXT,
    province        TEXT,

    -- The structure this channel takes water from. Lets an IRSA canal
    -- withdrawal reading attach to a shape on the map.
    feeds_from_asset_id BIGINT REFERENCES aquavision.water_assets(id),

    -- Name as printed in the IRSA daily report ("Dera Ghazi Khan Canal",
    -- "C-J Link"), which is how gauge readings are matched to geometry.
    irsa_label      TEXT,

    length_km       NUMERIC,

    -- The scope's "major canals and wider segments" filter. Narrow
    -- distributaries are loaded for completeness but not monitored: a 10 m
    -- channel cannot be resolved by a 10 m Sentinel-2 pixel.
    is_monitored    BOOLEAN NOT NULL DEFAULT FALSE,

    geom            geometry(MultiLineString, 4326) NOT NULL,

    source_name     TEXT,
    source_url      TEXT,
    retrieved_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_channels_geom ON aquavision.water_channels USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_channels_type ON aquavision.water_channels (channel_type);
CREATE INDEX IF NOT EXISTS idx_channels_monitored ON aquavision.water_channels (is_monitored)
    WHERE is_monitored;
CREATE INDEX IF NOT EXISTS idx_channels_irsa_label ON aquavision.water_channels (irsa_label)
    WHERE irsa_label IS NOT NULL;

-- OSM ids are unique per way; named channels without an osm_id must still be
-- unique by name and type.
CREATE UNIQUE INDEX IF NOT EXISTS uq_channels_osm
    ON aquavision.water_channels (osm_id) WHERE osm_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_channels_name
    ON aquavision.water_channels (channel_type, name) WHERE osm_id IS NULL;


-- ============================================================
-- water_canal_observations: measured canal offtakes from IRSA
-- ============================================================
-- Keyed by the label as PRINTED in the report, not by channel_id, so canal
-- readings can be ingested before any geometry is loaded. The condition
-- service joins these to water_channels via irsa_label when geometry exists.
CREATE TABLE IF NOT EXISTS aquavision.water_canal_observations (
    id              BIGSERIAL PRIMARY KEY,
    -- The structure the offtake leaves from (Taunsa, Chashma, ...).
    asset_id        BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    source_id       BIGINT NOT NULL REFERENCES aquavision.water_sources(id),

    -- "Dera Ghazi Khan Canal", "C-J Link", or '_total' for the aggregate
    -- "Canal W/dls" figure the report gives for some barrages.
    canal_label     TEXT NOT NULL,
    is_aggregate    BOOLEAN NOT NULL DEFAULT FALSE,

    observed_at     TIMESTAMPTZ NOT NULL,
    discharge_cusecs NUMERIC NOT NULL,

    data_status     TEXT NOT NULL DEFAULT 'OBSERVED_OFFICIAL',
    data_origin     TEXT NOT NULL DEFAULT 'REAL',
    quality_status  TEXT NOT NULL DEFAULT 'VALID',
    raw_record_id   BIGINT REFERENCES aquavision.raw_source_records(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (asset_id, canal_label, observed_at, source_id)
);

CREATE INDEX IF NOT EXISTS idx_canal_obs_label_time
    ON aquavision.water_canal_observations (canal_label, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_canal_obs_asset
    ON aquavision.water_canal_observations (asset_id, observed_at DESC);
-- Zero-flow readings are the signal this module exists to surface.
CREATE INDEX IF NOT EXISTS idx_canal_obs_dry
    ON aquavision.water_canal_observations (canal_label, observed_at DESC)
    WHERE discharge_cusecs = 0;


-- ============================================================
-- water_channel_condition: the module's main output
-- ============================================================
-- Two producers write here:
--   GAUGE_DISCHARGE - official IRSA canal withdrawals (available now)
--   NDWI_MASK       - Sentinel-2 water mask sampled along the channel (needs GEE)
-- The `method` column keeps them distinguishable so a gauge reading is never
-- presented as a satellite observation, and consumers never have to branch.
CREATE TABLE IF NOT EXISTS aquavision.water_channel_condition (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      BIGINT NOT NULL REFERENCES aquavision.water_channels(id) ON DELETE CASCADE,
    observed_week   DATE NOT NULL,
    method          TEXT NOT NULL CHECK (method IN ('GAUGE_DISCHARGE', 'NDWI_MASK')),

    discharge_cusecs NUMERIC,     -- gauge path
    wet_fraction     NUMERIC,     -- satellite path, 0..1
    baseline         NUMERIC,     -- rolling seasonal normal for this channel
    change_pct       NUMERIC,     -- vs baseline

    condition       TEXT NOT NULL CHECK (condition IN
                        ('FLOWING', 'REDUCED', 'LOW', 'DRY', 'UNKNOWN')),

    sample_count    INTEGER,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (channel_id, observed_week, method)
);

CREATE INDEX IF NOT EXISTS idx_channel_condition_week
    ON aquavision.water_channel_condition (observed_week DESC, channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_condition_state
    ON aquavision.water_channel_condition (condition)
    WHERE condition IN ('LOW', 'DRY');
