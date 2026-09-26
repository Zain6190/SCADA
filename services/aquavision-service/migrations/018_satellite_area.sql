CREATE TABLE IF NOT EXISTS aquavision.water_satellite_area (
    id                BIGSERIAL PRIMARY KEY,
    asset_id          BIGINT NOT NULL REFERENCES aquavision.water_assets(id),
    observed_on       DATE NOT NULL,
    area_km2          DOUBLE PRECISION,
    source_authority  TEXT NOT NULL DEFAULT 'GEE',
    method            TEXT NOT NULL DEFAULT 'NDWI',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (asset_id, observed_on, method)
);
