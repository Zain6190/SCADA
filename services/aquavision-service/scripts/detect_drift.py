"""
Data Quality & Drift Detection Job.
Checks: data staleness, missing sources, outlier detection, source coverage gaps.
"""
import json
import logging
import sys
from datetime import datetime, timedelta

import numpy as np

logger = logging.getLogger("drift_detection")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_db():
    from infrastructure.db.engine import engine
    return engine


def check_staleness(engine):
    """Check if any asset has no observations in the last 7 days."""
    from sqlalchemy import text
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

    with engine.connect() as conn:
        stale = conn.execute(text("""
            SELECT wa.id as asset_id, wa.canonical_name,
                   MAX(wo.observed_at) as last_observation,
                   EXTRACT(DAY FROM now() - MAX(wo.observed_at)) as days_stale
            FROM aquavision.water_assets wa
            LEFT JOIN aquavision.water_observations wo ON wo.asset_id = wa.id
            WHERE wa.is_active = true
            GROUP BY wa.id, wa.canonical_name
            HAVING MAX(wo.observed_at) IS NULL OR MAX(wo.observed_at) < :cutoff
            ORDER BY days_stale DESC NULLS FIRST
        """), {"cutoff": cutoff}).mappings().all()

    alerts = []
    for row in stale:
        alerts.append({
            "type": "STALENESS",
            "severity": "SEVERE" if (row["days_stale"] or 999) > 14 else "MODERATE",
            "asset_id": row["asset_id"],
            "asset_name": row["canonical_name"],
            "last_observation": str(row["last_observation"]) if row["last_observation"] else None,
            "days_stale": int(row["days_stale"]) if row["days_stale"] else None,
            "message": f"{row['canonical_name']} has no data for {int(row['days_stale'] or 999)} days",
        })

    return alerts


def check_outliers(engine):
    """Flag observations that are 3+ std deviations from rolling mean."""
    from sqlalchemy import text
    cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()

    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH stats AS (
                SELECT asset_id,
                       AVG(discharge_cusecs) as mean_d,
                       STDDEV(discharge_cusecs) as std_d
                FROM aquavision.water_observations
                WHERE observed_at >= :cutoff
                  AND discharge_cusecs IS NOT NULL
                  AND discharge_cusecs > 0
                GROUP BY asset_id
                HAVING COUNT(*) > 10
            )
            SELECT wo.id, wo.asset_id, wa.canonical_name,
                   wo.discharge_cusecs, wo.observed_at::text as observed_at,
                   s.mean_d, s.std_d,
                   ABS(wo.discharge_cusecs - s.mean_d) / NULLIF(s.std_d, 0) as z_score
            FROM aquavision.water_observations wo
            JOIN stats s ON s.asset_id = wo.asset_id
            LEFT JOIN aquavision.water_assets wa ON wa.id = wo.asset_id
            WHERE wo.observed_at >= :cutoff
              AND wo.discharge_cusecs IS NOT NULL
              AND wo.discharge_cusecs > 0
              AND ABS(wo.discharge_cusecs - s.mean_d) / NULLIF(s.std_d, 0) > 3
            ORDER BY z_score DESC
            LIMIT 20
        """), {"cutoff": cutoff}).mappings().all()

    alerts = []
    for row in rows:
        alerts.append({
            "type": "OUTLIER",
            "severity": "MODERATE",
            "asset_id": row["asset_id"],
            "asset_name": row["canonical_name"],
            "observation_id": row["id"],
            "value": row["discharge_cusecs"],
            "mean": round(row["mean_d"], 2),
            "z_score": round(row["z_score"], 2),
            "observed_at": row["observed_at"],
            "message": f"{row['canonical_name']}: {row['discharge_cusecs']:.0f} cusecs (z={row['z_score']:.1f})",
        })

    return alerts


def check_source_coverage(engine):
    """Check which data sources are reporting and which are missing."""
    from sqlalchemy import text
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT ds.authority as source_name, ds.source_type,
                   COUNT(DISTINCT wo.asset_id) as asset_count,
                   COUNT(*) as obs_count,
                   MAX(wo.observed_at)::text as last_obs
            FROM aquavision.water_sources ds
            LEFT JOIN aquavision.water_observations wo ON wo.source_id = ds.id
              AND wo.observed_at >= :cutoff
            GROUP BY ds.authority, ds.source_type
            ORDER BY ds.source_type
        """), {"cutoff": cutoff}).mappings().all()

    alerts = []
    for row in rows:
        if row["obs_count"] == 0:
            alerts.append({
                "type": "SOURCE_DOWN",
                "severity": "SEVERE",
                "source_name": row["source_name"],
                "source_type": row["source_type"],
                "message": f"Source '{row['source_name']}' has no observations in 7 days",
            })
        elif row["asset_count"] < 3:
            alerts.append({
                "type": "SOURCE_THIN",
                "severity": "MODERATE",
                "source_name": row["source_name"],
                "asset_count": row["asset_count"],
                "message": f"Source '{row['source_name']}' covers only {row['asset_count']} assets",
            })

    return alerts


def check_model_data_gaps(engine):
    """Check if training data has recent gaps that could affect models."""
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT wa.id as asset_id, wa.canonical_name,
                   COUNT(wo.id) as total_obs,
                   MIN(wo.observed_at)::text as first_obs,
                   MAX(wo.observed_at)::text as last_obs,
                   EXTRACT(DAY FROM MAX(wo.observed_at) - MIN(wo.observed_at)) as span_days
            FROM aquavision.water_assets wa
            JOIN aquavision.water_observations wo ON wo.asset_id = wa.id
            WHERE wa.is_active = true
            GROUP BY wa.id, wa.canonical_name
            ORDER BY total_obs DESC
        """)).mappings().all()

    alerts = []
    for row in rows:
        if row["total_obs"] < 30:
            alerts.append({
                "type": "INSUFFICIENT_DATA",
                "severity": "SEVERE",
                "asset_id": row["asset_id"],
                "asset_name": row["canonical_name"],
                "total_observations": row["total_obs"],
                "message": f"{row['canonical_name']}: only {row['total_obs']} observations (need 30+)",
            })
        elif row["span_days"] and row["span_days"] < 180:
            alerts.append({
                "type": "SHORT_HISTORY",
                "severity": "MODERATE",
                "asset_id": row["asset_id"],
                "asset_name": row["canonical_name"],
                "span_days": int(row["span_days"]),
                "message": f"{row['canonical_name']}: only {int(row['span_days'])} days of history",
            })

    return alerts


def store_alerts(engine, alerts):
    """Store alerts in drift_alerts table."""
    from sqlalchemy import text
    stored = 0
    with engine.begin() as conn:
        for alert in alerts:
            try:
                conn.execute(text("""
                    INSERT INTO aquavision.drift_alerts
                        (asset_id, horizon, drift_level, mae, rmse, mape,
                         bias_ratio, mean_error, n_samples, reasons, detected_at)
                    VALUES
                        (:asset_id, 0, :drift_level, 0, 0, 0,
                         0, 0, :n_samples, :reasons, now())
                """), {
                    "asset_id": alert.get("asset_id", 0),
                    "drift_level": alert["severity"],
                    "n_samples": alert.get("total_observations", 0),
                    "reasons": json.dumps([alert["message"]]),
                })
                stored += 1
            except Exception as e:
                logger.error(f"Failed to store alert: {e}")

    return stored


def main():
    engine = get_db()
    from sqlalchemy import text

    # Create table if needed
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS aquavision.drift_alerts (
                id SERIAL PRIMARY KEY,
                asset_id INTEGER DEFAULT 0,
                horizon INTEGER DEFAULT 0,
                drift_level VARCHAR(20) NOT NULL,
                mae FLOAT DEFAULT 0,
                rmse FLOAT DEFAULT 0,
                mape FLOAT DEFAULT 0,
                bias_ratio FLOAT DEFAULT 0,
                mean_error FLOAT DEFAULT 0,
                n_samples INTEGER DEFAULT 0,
                reasons JSONB DEFAULT '[]'::jsonb,
                detected_at TIMESTAMPTZ DEFAULT now(),
                acknowledged BOOLEAN DEFAULT false,
                acknowledged_by VARCHAR(100),
                acknowledged_at TIMESTAMPTZ
            );
            CREATE INDEX IF NOT EXISTS idx_drift_alerts_asset ON aquavision.drift_alerts(asset_id);
            CREATE INDEX IF NOT EXISTS idx_drift_alerts_level ON aquavision.drift_alerts(drift_level);
            CREATE INDEX IF NOT EXISTS idx_drift_alerts_date ON aquavision.drift_alerts(detected_at);
        """))

    logger.info("Running data quality checks...")

    all_alerts = []

    # 1. Staleness check
    stale = check_staleness(engine)
    all_alerts.extend(stale)
    logger.info(f"  Staleness: {len(stale)} alerts")

    # 2. Outlier check
    outliers = check_outliers(engine)
    all_alerts.extend(outliers)
    logger.info(f"  Outliers: {len(outliers)} alerts")

    # 3. Source coverage
    sources = check_source_coverage(engine)
    all_alerts.extend(sources)
    logger.info(f"  Source coverage: {len(sources)} alerts")

    # 4. Model data gaps
    gaps = check_model_data_gaps(engine)
    all_alerts.extend(gaps)
    logger.info(f"  Data gaps: {len(gaps)} alerts")

    # Store all alerts
    stored = store_alerts(engine, all_alerts)

    result = {
        "total_alerts": len(all_alerts),
        "stored": stored,
        "by_type": {},
        "by_severity": {},
    }

    for a in all_alerts:
        t = a["type"]
        s = a["severity"]
        result["by_type"][t] = result["by_type"].get(t, 0) + 1
        result["by_severity"][s] = result["by_severity"].get(s, 0) + 1

    logger.info(f"Data quality check complete: {len(all_alerts)} alerts ({stored} stored)")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
