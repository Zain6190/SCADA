-- migrations/007_grdc_ingest.sql
-- GAP 2: Global Runoff Data Centre discharge archives (data/raw/grdc).
--
-- Why its own tables instead of water_observations: of 41 GRDC stations on
-- disk only ONE (Jhelum @ Chinari) is even arguably the gauge of an asset, and
-- the old ingest_grdc_useful.py mapped all four Kabul tributaries onto asset 9
-- as if upstream sub-basins were the Nowshera gauge. Station identity must be
-- preserved for the intended use - routing validation against physics-routed
-- reaches and long-history upstream features - so observations keep their
-- GRDC station number and are never written into the asset observation series.
--
-- Coverage: 33 stations with data (1959-1982), ~86k daily rows. The 8
-- mainstem gauges (Indus @ Attock/Kotri, Chenab @ Panjnad, ...) have EMPTY
-- daily files but populated MONTHLY ones - hence freq ('D'/'M') in the key.

CREATE TABLE IF NOT EXISTS aquavision.grdc_stations (
    grdc_no                 TEXT PRIMARY KEY,
    river                   TEXT NOT NULL,
    station                 TEXT NOT NULL,
    country                 TEXT,
    latitude                DOUBLE PRECISION,
    longitude               DOUBLE PRECISION,
    catchment_km2           DOUBLE PRECISION,
    altitude_m              DOUBLE PRECISION,
    next_downstream_grdc_no TEXT,
    owner                   TEXT,
    period_daily_start      DATE,
    period_daily_end        DATE,
    period_monthly_start    DATE,
    period_monthly_end      DATE,
    file_generated          DATE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS aquavision.grdc_observations (
    grdc_no       TEXT NOT NULL REFERENCES aquavision.grdc_stations(grdc_no) ON DELETE CASCADE,
    obs_date      DATE NOT NULL,
    freq          TEXT NOT NULL CHECK (freq IN ('D', 'M')),
    discharge_m3s DOUBLE PRECISION NOT NULL,
    source_id     INTEGER REFERENCES aquavision.water_sources(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Monthly means are dated to day 01 by the export format; D and M for the
    -- same month coexist by design (daily data and its monthly aggregate are
    -- different facts).
    PRIMARY KEY (grdc_no, obs_date, freq)
);

-- Cross-station queries: "all stations on date X", per-date validation joins.
CREATE INDEX IF NOT EXISTS idx_grdc_obs_date ON aquavision.grdc_observations (obs_date);
CREATE INDEX IF NOT EXISTS idx_grdc_obs_freq ON aquavision.grdc_observations (freq);

COMMENT ON TABLE aquavision.grdc_stations IS
    'GRDC station registry parsed from data/raw/grdc headers; never merged into water_observations';
COMMENT ON TABLE aquavision.grdc_observations IS
    'GRDC mean daily (D) and mean monthly (M) discharge in m3/s, one row per station/date/freq';
