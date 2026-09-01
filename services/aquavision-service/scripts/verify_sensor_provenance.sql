-- scripts/verify_sensor_provenance.sql
-- Correctness gates for telemetry-class ingestion (SENSOR_API / SENSOR_REPLAY / USGS_NWIS).
--
-- Run after any replay:
--   docker exec -i ibcp-postgis psql -U postgres -d ibcp_scada \
--     < services/aquavision-service/scripts/verify_sensor_provenance.sql
--
-- GATE 1 and GATE 2 must pass before replayed data is used for anything.

\echo ''
\echo '=== GATE 1: IRSA must still hold priority 1 and dominate v_best_observations ==='
\echo 'PASS if IRSA is present at priority 1 and no sensor authority appears at priority < 4.'
SELECT source,
       priority,
       COUNT(*)            AS winning_rows,
       MIN(observed_at)    AS earliest,
       MAX(observed_at)    AS latest
FROM aquavision.v_best_observations
GROUP BY source, priority
ORDER BY priority, source;

\echo ''
\echo '=== GATE 2: no telemetry row may be stamped REAL unless it came from SENSOR_API ==='
\echo 'PASS if this returns ZERO rows.'
SELECT s.authority, o.data_origin, o.data_status, COUNT(*) AS offending_rows
FROM aquavision.water_observations o
JOIN aquavision.water_sources s ON s.id = o.source_id
WHERE s.authority IN ('SENSOR_REPLAY', 'USGS_NWIS')
  AND o.data_origin <> 'SYNTHETIC'
GROUP BY s.authority, o.data_origin, o.data_status;

\echo ''
\echo '=== GATE 3: every telemetry row sits at source_priority 4 ==='
\echo 'PASS if this returns ZERO rows.'
SELECT s.authority, o.source_priority, COUNT(*) AS offending_rows
FROM aquavision.water_observations o
JOIN aquavision.water_sources s ON s.id = o.source_id
WHERE s.authority IN ('SENSOR_API', 'SENSOR_REPLAY', 'USGS_NWIS')
  AND COALESCE(o.source_priority, 99) <> 4
GROUP BY s.authority, o.source_priority;

\echo ''
\echo '=== Coverage: what each feed actually contributed ==='
SELECT source,
       data_origin,
       SUM(row_count)      AS rows,
       MIN(earliest)       AS from_ts,
       MAX(latest)         AS to_ts,
       SUM(days_covered)   AS days
FROM aquavision.v_source_coverage
GROUP BY source, data_origin
ORDER BY source;

\echo ''
\echo '=== Cadence: median gap between readings, per source ==='
\echo 'IRSA/FFD should be ~1440 min (daily). SENSOR_REPLAY ~60. USGS_NWIS ~15.'
WITH gaps AS (
    SELECT s.authority,
           EXTRACT(EPOCH FROM (
               o.observed_at - LAG(o.observed_at) OVER (
                   PARTITION BY o.asset_id, o.source_id ORDER BY o.observed_at
               )
           )) / 60.0 AS gap_min
    FROM aquavision.water_observations o
    JOIN aquavision.water_sources s ON s.id = o.source_id
)
SELECT authority,
       COUNT(*)                                                     AS intervals,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gap_min)::numeric, 1)
                                                                    AS median_gap_min
FROM gaps
WHERE gap_min IS NOT NULL AND gap_min > 0
GROUP BY authority
ORDER BY median_gap_min;

\echo ''
\echo '=== RAPID_RISE alerts: are any now backed by a genuine sub-daily window? ==='
SELECT a.alert_type,
       a.severity,
       COUNT(*) AS alerts,
       MAX(a.created_at) AS latest
FROM aquavision.water_operational_alerts a
WHERE a.alert_type IN ('RAPID_RISE', 'RISING_LEVEL')
GROUP BY a.alert_type, a.severity
ORDER BY a.alert_type, a.severity;
