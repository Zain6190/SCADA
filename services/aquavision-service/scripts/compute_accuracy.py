"""
Compute prediction accuracy by matching expired predictions to observations.

For each prediction in water_predictions_weekly whose target_time has passed:
1. Find the actual observation closest to target_time
2. Compute error metrics (absolute, percentage, direction)
3. Store in prediction_errors table

Run daily after predictions expire (e.g., 7-day predictions expire after 7 days).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger("aquavision.compute_accuracy")


def compute_accuracy(db_session, lookback_days: int = 30, dry_run: bool = False) -> dict:
    """Match expired predictions to observations and compute errors.
    
    Args:
        db_session: SQLAlchemy session
        lookback_days: How far back to look for expired predictions
        dry_run: If True, don't write to DB
    
    Returns:
        {"matched": int, "errors": int, "skipped": int}
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)
    
    # Find expired predictions not yet matched
    expired = db_session.execute(
        text("""
            SELECT p.id, p.asset_id, p.generated_at, p.target_time,
                   p.predicted_level_ft, p.predicted_inflow, p.model_version,
                   p.horizon_days
            FROM aquavision.water_predictions_weekly p
            WHERE p.target_time < :now
              AND p.target_time > :cutoff
              AND NOT EXISTS (
                  SELECT 1 FROM aquavision.prediction_errors e 
                  WHERE e.prediction_date = p.generated_at 
                    AND e.asset_id = p.asset_id
                    AND e.horizon = p.horizon_days
              )
            ORDER BY p.target_time ASC
        """),
        {"now": now, "cutoff": cutoff},
    ).mappings().all()
    
    results = {"matched": 0, "errors": 0, "skipped": 0}
    
    for pred in expired:
        try:
            asset_id = pred["asset_id"]
            target_time = pred["target_time"]
            horizon = pred["horizon_days"]
            predicted_level = pred["predicted_level_ft"]
            predicted_inflow = pred["predicted_inflow"]
            
            # Find actual observation closest to target_time
            actual = db_session.execute(
                text("""
                    SELECT water_level_ft, inflow_cusecs, discharge_cusecs, 
                           observed_at, data_origin
                    FROM aquavision.water_observations
                    WHERE asset_id = :asset_id
                      AND observed_at BETWEEN :start AND :end
                    ORDER BY ABS(observed_at - :target) ASC
                    LIMIT 1
                """),
                {
                    "asset_id": asset_id,
                    "start": target_time - timedelta(days=1),
                    "end": target_time + timedelta(days=1),
                    "target": target_time,
                },
            ).mappings().first()
            
            if not actual:
                results["skipped"] += 1
                continue
            
            # Determine which value to compare
            actual_value = None
            predicted_value = None
            match_column = None
            
            if predicted_level is not None and actual["water_level_ft"] is not None:
                predicted_value = predicted_level
                actual_value = float(actual["water_level_ft"])
                match_column = "level"
            elif predicted_inflow is not None and actual["inflow_cusecs"] is not None:
                predicted_value = predicted_inflow
                actual_value = float(actual["inflow_cusecs"])
                match_column = "inflow"
            elif predicted_level is not None and actual["discharge_cusecs"] is not None:
                # Fallback: compare level prediction to discharge (not ideal but better than nothing)
                results["skipped"] += 1
                continue
            
            if predicted_value is None or actual_value is None:
                results["skipped"] += 1
                continue
            
            # Compute error
            error = predicted_value - actual_value
            error_pct = abs(error) / actual_value * 100 if actual_value > 0 else 0
            
            if not dry_run:
                db_session.execute(
                    text("""
                        INSERT INTO aquavision.prediction_errors
                            (asset_id, model_version, prediction_date, target_date,
                             horizon, predicted_value, actual_value, error, error_pct, data_origin)
                        VALUES
                            (:asset_id, :model_version, :prediction_date, :target_date,
                             :horizon, :predicted_value, :actual_value, :error, :error_pct, :data_origin)
                    """),
                    {
                        "asset_id": asset_id,
                        "model_version": pred["model_version"],
                        "prediction_date": pred["generated_at"],
                        "target_date": target_time,
                        "horizon": horizon,
                        "predicted_value": predicted_value,
                        "actual_value": actual_value,
                        "error": error,
                        "error_pct": error_pct,
                        "data_origin": getattr(actual, "data_origin", "REAL"),
                    },
                )
            
            results["matched"] += 1
            logger.debug(
                f"Asset {asset_id} {horizon}d: predicted={predicted_value:.1f}, "
                f"actual={actual_value:.1f}, error={error:.1f} ({error_pct:.1f}%)"
            )
        
        except Exception as e:
            logger.warning(f"Error computing accuracy for pred {pred.get('id')}: {e}")
            results["errors"] += 1
    
    if not dry_run and results["matched"] > 0:
        db_session.commit()
    
    logger.info(f"Accuracy computation: {results}")
    return results


def get_accuracy_summary(db_session, asset_id: int = None, horizon: int = None) -> dict:
    """Get accuracy summary statistics."""
    conditions = ["1=1"]
    params = {}
    
    if asset_id:
        conditions.append("asset_id = :asset_id")
        params["asset_id"] = asset_id
    if horizon:
        conditions.append("horizon = :horizon")
        params["horizon"] = horizon
    
    where = " AND ".join(conditions)
    
    row = db_session.execute(
        text(f"""
            SELECT 
                COUNT(*) as total_predictions,
                AVG(ABS(error)) as mae,
                SQRT(AVG(error * error)) as rmse,
                AVG(error_pct) as mape,
                AVG(CASE WHEN error > 0 THEN 1.0 ELSE 0.0 END) as overprediction_rate,
                AVG(CASE WHEN error < 0 THEN 1.0 ELSE 0.0 END) as underprediction_rate,
                MIN(target_date) as earliest,
                MAX(target_date) as latest
            FROM aquavision.prediction_errors
            WHERE {where}
        """),
        params,
    ).mappings().first()
    
    return dict(row) if row else {}


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    from infrastructure.db.engine import SessionLocal
    
    with SessionLocal() as db:
        results = compute_accuracy(db)
        print(f"\nAccuracy results: {results}")
        
        summary = get_accuracy_summary(db)
        print(f"Summary: {summary}")
