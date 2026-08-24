-- Source-aware views for AquaVision ML pipeline
-- Created: 2026-08-24
-- These were originally created via psql and not tracked in code.

-- v_best_observations: Best value per (asset_id, date, parameter) using source priority
-- Priority: IRSA=1 > FFD/PMD=2 > KAGGLE=3 > SENSOR_API=4 > GEE=5
-- Used by ML feature engineering when source_priority=True
CREATE OR REPLACE VIEW aquavision.v_best_observations AS
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
FROM ranked WHERE rn = 1;

-- v_unified_observations: Wide-format with source info
CREATE OR REPLACE VIEW aquavision.v_unified_observations AS
SELECT o.id, o.asset_id, o.observed_at, o.water_level_ft, o.inflow_cusecs,
       o.outflow_cusecs, o.discharge_cusecs, o.data_status, o.data_origin,
       o.quality_status, s.authority AS source, o.source_priority,
       a.canonical_name AS asset_name, a.river
FROM aquavision.water_observations o
JOIN aquavision.water_sources s ON s.id = o.source_id
JOIN aquavision.water_assets a ON a.id = o.asset_id;

-- v_source_coverage: Data coverage summary per source per asset
CREATE OR REPLACE VIEW aquavision.v_source_coverage AS
SELECT o.asset_id, a.canonical_name, s.authority AS source, s.id AS source_id,
       COUNT(*) AS row_count, MIN(o.observed_at) AS earliest,
       MAX(o.observed_at) AS latest, COUNT(DISTINCT o.observed_at::date) AS days_covered,
       o.data_origin
FROM aquavision.water_observations o
JOIN aquavision.water_sources s ON s.id = o.source_id
JOIN aquavision.water_assets a ON a.id = o.asset_id
GROUP BY o.asset_id, a.canonical_name, s.authority, s.id, o.data_origin;

-- v_irsa_observations: IRSA-specific
CREATE OR REPLACE VIEW aquavision.v_irsa_observations AS
SELECT * FROM aquavision.v_unified_observations WHERE source = 'IRSA';

-- v_kaggle_observations: Kaggle-specific
CREATE OR REPLACE VIEW aquavision.v_kaggle_observations AS
SELECT * FROM aquavision.v_unified_observations WHERE source = 'KAGGLE';
