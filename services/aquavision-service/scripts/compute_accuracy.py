"""
Accuracy Computation Job.
Finds expired predictions, matches them to observations, computes metrics,
writes to prediction_accuracy, refreshes materialized view.

Run daily after persist_predictions (03:00 UTC).
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

logger = logging.getLogger("accuracy_computation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_BASE_DIR = os.environ.get("AQUAVISION_BASE_DIR", "/app")


def get_db():
    from infrastructure.db.engine import engine
    return engine


# ── Core SQL: Match predictions to observations and compute metrics ──────

MATCH_AND_COMPUTE_SQL = """
WITH unmatched AS (
    SELECT
        wp.id              AS prediction_id,
        wp.asset_id,
        wp.horizon,
        wp.predicted_value,
        wp.predicted_lower,
        wp.predicted_upper,
        wp.model_version,
        wp.generated_at    AS predicted_at,
        wp.valid_from,
        wp.valid_to,
        wp.valid_to        AS target_date
    FROM aquavision.water_predictions wp
    WHERE wp.valid_to < now() - INTERVAL '48 hours'
      AND wp.id NOT IN (
          SELECT prediction_id
          FROM aquavision.prediction_accuracy
          WHERE prediction_id IS NOT NULL
      )
),
best_observation AS (
    SELECT DISTINCT ON (u.prediction_id)
        u.prediction_id,
        u.asset_id,
        u.horizon,
        u.predicted_value,
        u.predicted_lower,
        u.predicted_upper,
        u.model_version,
        u.predicted_at,
        u.target_date,
        wo.observed_at                                   AS actual_at,
        COALESCE(wo.inflow_cusecs, wo.discharge_cusecs)  AS actual_value,
        CASE
            WHEN wo.inflow_cusecs IS NOT NULL THEN 'inflow_cusecs'
            WHEN wo.discharge_cusecs IS NOT NULL THEN 'discharge_cusecs'
            ELSE 'water_level_ft'
        END                                               AS matched_column,
        wo.data_origin
    FROM unmatched u
    JOIN aquavision.water_observations wo
        ON wo.asset_id = u.asset_id
       AND wo.observed_at BETWEEN u.target_date - INTERVAL '48 hours'
                              AND u.target_date + INTERVAL '48 hours'
       AND COALESCE(wo.inflow_cusecs, wo.discharge_cusecs) IS NOT NULL
    ORDER BY u.prediction_id,
             ABS(EXTRACT(EPOCH FROM (wo.observed_at - u.target_date))) ASC
)
INSERT INTO aquavision.prediction_accuracy (
    asset_id, horizon, prediction_id, predicted_value, actual_value,
    error, abs_error, squared_error, pct_error,
    within_interval, direction_correct, data_origin, matched_column,
    predicted_at, actual_at, model_version, matched_at
)
SELECT
    bo.asset_id,
    bo.horizon,
    bo.prediction_id,
    bo.predicted_value,
    bo.actual_value,
    bo.actual_value - bo.predicted_value                           AS error,
    ABS(bo.actual_value - bo.predicted_value)                      AS abs_error,
    (bo.actual_value - bo.predicted_value) ^ 2                     AS squared_error,
    ABS(bo.actual_value - bo.predicted_value)
        / NULLIF(bo.actual_value, 0) * 100                         AS pct_error,
    (bo.predicted_lower <= bo.actual_value
     AND bo.actual_value <= bo.predicted_upper)                     AS within_interval,
    CASE
        WHEN prev.actual_value IS NOT NULL THEN
            (bo.actual_value > prev.actual_value AND bo.predicted_value > prev.actual_value)
            OR (bo.actual_value < prev.actual_value AND bo.predicted_value < prev.actual_value)
            OR (bo.actual_value = prev.actual_value)
        ELSE NULL
    END                                                             AS direction_correct,
    bo.data_origin,
    bo.matched_column,
    bo.predicted_at,
    bo.actual_at,
    bo.model_version,
    now()                                                          AS matched_at
FROM best_observation bo
LEFT JOIN LATERAL (
    SELECT pa.actual_value
    FROM aquavision.prediction_accuracy pa
    WHERE pa.asset_id = bo.asset_id
      AND pa.horizon = bo.horizon
      AND pa.actual_at < bo.actual_at
    ORDER BY pa.actual_at DESC
    LIMIT 1
) prev ON TRUE;
"""

# Mark predictions that have no matching observation
EXPIRED_SQL = """
INSERT INTO aquavision.prediction_accuracy (
    asset_id, horizon, prediction_id, predicted_value,
    actual_value, error, abs_error, squared_error, pct_error,
    predicted_at, actual_at, model_version, matched_at
)
SELECT
    wp.asset_id, wp.horizon, wp.id, wp.predicted_value,
    NULL, NULL, NULL, NULL, NULL,
    wp.generated_at, wp.valid_to, wp.model_version, now()
FROM aquavision.water_predictions wp
WHERE wp.valid_to < now() - INTERVAL '48 hours'
  AND wp.id NOT IN (
      SELECT prediction_id
      FROM aquavision.prediction_accuracy
      WHERE prediction_id IS NOT NULL
  );
"""


def compute_accuracy():
    """Main entry: match expired predictions to observations, compute metrics."""
    engine = get_db()
    from sqlalchemy import text

    start_time = datetime.now(timezone.utc)
    stats = {"matched": 0, "expired_no_data": 0, "errors": []}

    # Step 1: Match and insert accuracy rows
    with engine.begin() as conn:
        try:
            result = conn.execute(text(MATCH_AND_COMPUTE_SQL))
            stats["matched"] = result.rowcount
            logger.info(f"Matched {stats['matched']} predictions to observations")
        except Exception as e:
            logger.error(f"Matching query failed: {e}")
            stats["errors"].append(str(e))

    # Step 2: Mark expired predictions (no observation found)
    with engine.begin() as conn:
        try:
            result = conn.execute(text(EXPIRED_SQL))
            stats["expired_no_data"] = result.rowcount
            logger.info(f"Marked {stats['expired_no_data']} predictions as expired (no observation)")
        except Exception as e:
            logger.error(f"Expired query failed: {e}")
            stats["errors"].append(str(e))

    # Step 3: Refresh materialized view
    with engine.begin() as conn:
        try:
            conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY aquavision.mv_accuracy_snapshot"))
            logger.info("Refreshed accuracy snapshot view")
        except Exception:
            try:
                conn.execute(text("REFRESH MATERIALIZED VIEW aquavision.mv_accuracy_snapshot"))
                logger.info("Refreshed accuracy snapshot view (non-concurrent)")
            except Exception as e:
                logger.warning(f"Could not refresh materialized view: {e}")

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"Accuracy computation complete: {stats['matched']} matched, "
        f"{stats['expired_no_data']} expired, {duration:.1f}s"
    )
    return stats


# ── Read functions for API ───────────────────────────────────────────────

def get_accuracy_summary(asset_id=None, horizon=None):
    """Read from the materialized view for API responses."""
    engine = get_db()
    from sqlalchemy import text

    query = """
        SELECT asset_id, horizon, model_version,
               mae_30d, rmse_30d, mape_30d, bias_30d,
               coverage_30d, direction_30d, sample_count_30d,
               mae_90d, rmse_90d, mape_90d, bias_90d,
               coverage_90d, direction_90d, sample_count_90d,
               last_evaluated_at::text
        FROM aquavision.mv_accuracy_snapshot
        WHERE 1=1
    """
    params = {}
    if asset_id is not None:
        query += " AND asset_id = :asset_id"
        params["asset_id"] = asset_id
    if horizon is not None:
        query += " AND horizon = :horizon"
        params["horizon"] = horizon
    query += " ORDER BY asset_id, horizon"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(r) for r in rows]


def get_accuracy_timeline(asset_id, horizon, days=90):
    """Get time-series of accuracy for charts."""
    from datetime import timedelta
    engine = get_db()
    from sqlalchemy import text

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = engine.connect().execute(text("""
        SELECT
            actual_at::date AS date,
            predicted_value,
            actual_value,
            error,
            abs_error,
            pct_error,
            within_interval,
            direction_correct,
            model_version
        FROM aquavision.prediction_accuracy
        WHERE asset_id = :asset_id
          AND horizon = :horizon
          AND actual_value IS NOT NULL
          AND actual_at >= :cutoff
        ORDER BY actual_at ASC
    """), {"asset_id": asset_id, "horizon": horizon, "cutoff": cutoff}).mappings().all()

    return [dict(r) for r in rows]


def get_pending_predictions():
    """Get predictions awaiting evaluation."""
    engine = get_db()
    from sqlalchemy import text

    rows = engine.connect().execute(text("""
        SELECT wp.id, wp.asset_id, wp.horizon, wp.predicted_value,
               wp.predicted_lower, wp.predicted_upper,
               wp.model_version, wp.risk_category,
               wp.valid_from::text, wp.valid_to::text,
               wp.generated_at::text,
               EXTRACT(DAY FROM wp.valid_to + INTERVAL '48 hours' - now()) AS days_until_evaluation,
               wa.canonical_name AS asset_name
        FROM aquavision.water_predictions wp
        LEFT JOIN aquavision.water_assets wa ON wa.id = wp.asset_id
        WHERE wp.id NOT IN (
            SELECT prediction_id FROM aquavision.prediction_accuracy
            WHERE prediction_id IS NOT NULL
        )
        ORDER BY wp.valid_to ASC
    """)).mappings().all()

    return [dict(r) for r in rows]


def get_accuracy_by_model(asset_id, horizon):
    """Compare accuracy across model versions."""
    engine = get_db()
    from sqlalchemy import text

    rows = engine.connect().execute(text("""
        SELECT
            model_version,
            COUNT(*)                                              AS n,
            AVG(abs_error)                                        AS mae,
            SQRT(AVG(squared_error))                              AS rmse,
            AVG(pct_error)                                        AS mape,
            AVG(error)                                            AS bias,
            AVG(CASE WHEN within_interval THEN 1.0 ELSE 0 END)   AS coverage,
            AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0 END) AS direction,
            MIN(actual_at)::text                                  AS first_evaluated,
            MAX(actual_at)::text                                  AS last_evaluated
        FROM aquavision.prediction_accuracy
        WHERE asset_id = :asset_id
          AND horizon = :horizon
          AND actual_value IS NOT NULL
        GROUP BY model_version
        ORDER BY n DESC
    """), {"asset_id": asset_id, "horizon": horizon}).mappings().all()

    return {"asset_id": asset_id, "horizon": horizon, "models": [dict(r) for r in rows]}


if __name__ == "__main__":
    result = compute_accuracy()
    print(json.dumps(result, indent=2))
