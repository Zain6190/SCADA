CREATE TABLE IF NOT EXISTS aquavision.surface_water_weekly (
    id                    BIGSERIAL PRIMARY KEY,
    region_id             BIGINT NOT NULL REFERENCES shared.regions(id),
    week_start_date       DATE NOT NULL,
    ndwi_mean             DOUBLE PRECISION,
    mndwi_mean            DOUBLE PRECISION,
    water_area_km2        DOUBLE PRECISION,
    prev_water_area_km2   DOUBLE PRECISION,
    change_pct            DOUBLE PRECISION,
    cloud_pct             DOUBLE PRECISION,
    data_status           TEXT NOT NULL DEFAULT 'processed',
    source_version        TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (region_id, week_start_date)
);
