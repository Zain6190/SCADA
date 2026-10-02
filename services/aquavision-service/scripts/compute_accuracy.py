"""
Compute prediction accuracy by matching expired forecasts to observations.

Scores water_asset_forecasts (asset-level) — not water_predictions_weekly
(region WAI, no asset_id/horizon). Actuals must be REAL observations.

Run daily after predictions expire (scheduler job_compute_accuracy).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger("aquavision.compute_accuracy")


def _horizon_days(generated_at, target_time) -> int:
    delta = target_time - generated_at
    return max(1, int(round(delta.total_seconds() / 86400)))


FLOOD_CLASSIFIER_VERSION = "flood_classifier_h7"
FLOOD_LABEL_STATUSES = ("HIGH", "VERY_HIGH", "EXCEPTIONALLY_HIGH")


def _flood_outcome(db_session, asset_id: int, target_time):
    """0/1 flood outcome at target_time.

    FFD bulletin first (authoritative label); otherwise inflow above the
    trailing 90-day REAL p90 — the same percentile idea the classifier's
    training labels use when flood_status is absent.
    """
    ffd = db_session.execute(
        text("""
            SELECT flood_status FROM aquavision.water_ffd_observations
            WHERE asset_id = :asset_id
              AND observed_at BETWEEN :start AND :end
            ORDER BY ABS(extract(epoch FROM (observed_at - :target))) ASC
            LIMIT 1
        """),
        {
            "asset_id": asset_id,
            "start": target_time - timedelta(days=1),
            "end": target_time + timedelta(days=1),
            "target": target_time,
        },
    ).scalar()
    if ffd:
        return 1 if str(ffd).upper() in FLOOD_LABEL_STATUSES else 0

    p90 = db_session.execute(
        text("""
            SELECT percentile_cont(0.9) WITHIN GROUP (ORDER BY inflow_cusecs)
            FROM aquavision.water_observations
            WHERE asset_id = :asset_id
              AND inflow_cusecs IS NOT NULL
              AND data_origin = 'REAL'
              AND observed_at BETWEEN :start AND :end
        """),
        {
            "asset_id": asset_id,
            "start": target_time - timedelta(days=90),
            "end": target_time,
        },
    ).scalar()
    actual = db_session.execute(
        text("""
            SELECT inflow_cusecs FROM aquavision.water_observations
            WHERE asset_id = :asset_id
              AND inflow_cusecs IS NOT NULL
              AND data_origin = 'REAL'
              AND observed_at BETWEEN :start AND :end
            ORDER BY ABS(extract(epoch FROM (observed_at - :target))) ASC
            LIMIT 1
        """),
        {
            "asset_id": asset_id,
            "start": target_time - timedelta(days=1),
            "end": target_time + timedelta(days=1),
            "target": target_time,
        },
    ).scalar()
    if p90 is None or actual is None:
        return None
    return 1 if float(actual) > float(p90) else 0


def compute_accuracy(db_session, lookback_days: int = 60, dry_run: bool = False) -> dict:
    """Match expired water_asset_forecasts to REAL observations and write errors.

    Rows carrying a classifier flood_probability also get a binary outcome
    score (model_version 'flood_classifier_h7'); regression matching runs
    the same as before.

    Returns:
        {"matched": int, "errors": int, "skipped": int,
         "clf_scored": int, "clf_skipped": int}
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)

    expired = db_session.execute(
        text("""
            SELECT * FROM (
                SELECT p.id, p.asset_id, p.generated_at, p.target_time,
                       p.predicted_level_ft, p.predicted_inflow, p.predicted_outflow,
                       p.predicted_discharge, p.flood_probability,
                       p.model_version,
                       (NOT EXISTS (
                           SELECT 1 FROM aquavision.prediction_errors e
                           WHERE e.prediction_date = p.generated_at
                             AND e.asset_id = p.asset_id
                             AND e.model_version = p.model_version
                       )) AS needs_reg,
                       (p.flood_probability IS NOT NULL AND NOT EXISTS (
                           SELECT 1 FROM aquavision.prediction_errors ec
                           WHERE ec.prediction_date = p.generated_at
                             AND ec.asset_id = p.asset_id
                             AND ec.model_version = 'flood_classifier_h7'
                       )) AS needs_clf
                FROM aquavision.water_asset_forecasts p
                WHERE p.target_time < :now
                  AND p.target_time > :cutoff
            ) t
            WHERE t.needs_reg OR t.needs_clf
            ORDER BY t.target_time ASC
        """),
        {"now": now, "cutoff": cutoff},
    ).mappings().all()

    results = {"matched": 0, "errors": 0, "skipped": 0, "clf_scored": 0, "clf_skipped": 0}

    for pred in expired:
        try:
            asset_id = pred["asset_id"]
            target_time = pred["target_time"]
            generated_at = pred["generated_at"]
            horizon = _horizon_days(generated_at, target_time)

            if pred.get("needs_clf") and pred.get("flood_probability") is not None:
                outcome = _flood_outcome(db_session, asset_id, target_time)
                if outcome is None:
                    results["clf_skipped"] += 1
                else:
                    prob = float(pred["flood_probability"])
                    error = prob - outcome
                    if not dry_run:
                        db_session.execute(
                            text("""
                                INSERT INTO aquavision.prediction_errors
                                    (asset_id, model_version, prediction_date, target_date,
                                     horizon, predicted_value, actual_value, error, error_pct, data_origin)
                                VALUES
                                    (:asset_id, :model_version, :prediction_date, :target_date,
                                     :horizon, :predicted_value, :actual_value, :error, :error_pct, 'REAL')
                            """),
                            {
                                "asset_id": asset_id,
                                "model_version": FLOOD_CLASSIFIER_VERSION,
                                "prediction_date": generated_at,
                                "target_date": target_time,
                                "horizon": horizon,
                                "predicted_value": prob,
                                "actual_value": float(outcome),
                                "error": error,
                                "error_pct": abs(error) * 100,
                            },
                        )
                    results["clf_scored"] += 1

            if pred.get("needs_reg") is False:
                continue

            actual = db_session.execute(
                text("""
                    SELECT water_level_ft, inflow_cusecs, outflow_cusecs,
                           discharge_cusecs,
                           observed_at, data_origin
                    FROM aquavision.water_observations
                    WHERE asset_id = :asset_id
                      AND data_origin = 'REAL'
                      AND observed_at BETWEEN :start AND :end
                    ORDER BY ABS(extract(epoch FROM (observed_at - :target))) ASC
                    LIMIT 1
                """),
                {
                    "asset_id": asset_id,
                    "start": target_time - timedelta(days=1),
                    "end": target_time + timedelta(days=1),
                    "target": target_time,
                },
            ).mappings().first()

            if not actual or actual.get("data_origin") != "REAL":
                results["skipped"] += 1
                continue

            predicted_value = None
            actual_value = None

            if pred["predicted_inflow"] is not None and actual["inflow_cusecs"] is not None:
                predicted_value = float(pred["predicted_inflow"])
                actual_value = float(actual["inflow_cusecs"])
            elif pred["predicted_outflow"] is not None and actual["outflow_cusecs"] is not None:
                # Reservoir release forecasts (Tarbela/Mangla outflow models)
                predicted_value = float(pred["predicted_outflow"])
                actual_value = float(actual["outflow_cusecs"])
            elif pred["predicted_discharge"] is not None and actual["discharge_cusecs"] is not None:
                predicted_value = float(pred["predicted_discharge"])
                actual_value = float(actual["discharge_cusecs"])
            elif pred["predicted_level_ft"] is not None and actual["water_level_ft"] is not None:
                predicted_value = float(pred["predicted_level_ft"])
                actual_value = float(actual["water_level_ft"])
            else:
                results["skipped"] += 1
                continue

            if predicted_value is None or actual_value is None:
                results["skipped"] += 1
                continue

            error = predicted_value - actual_value
            error_pct = abs(error) / actual_value * 100 if actual_value > 0 else abs(error)

            if not dry_run:
                db_session.execute(
                    text("""
                        INSERT INTO aquavision.prediction_errors
                            (asset_id, model_version, prediction_date, target_date,
                             horizon, predicted_value, actual_value, error, error_pct, data_origin)
                        VALUES
                            (:asset_id, :model_version, :prediction_date, :target_date,
                             :horizon, :predicted_value, :actual_value, :error, :error_pct, 'REAL')
                    """),
                    {
                        "asset_id": asset_id,
                        "model_version": pred["model_version"],
                        "prediction_date": generated_at,
                        "target_date": target_time,
                        "horizon": horizon,
                        "predicted_value": predicted_value,
                        "actual_value": actual_value,
                        "error": error,
                        "error_pct": error_pct,
                    },
                )

            results["matched"] += 1
            logger.debug(
                "Asset %s %sd: predicted=%.1f actual=%.1f error=%.1f (%.1f%%)",
                asset_id, horizon, predicted_value, actual_value, error, error_pct,
            )

        except Exception as e:
            logger.warning("Error computing accuracy for pred %s: %s", pred.get("id"), e)
            results["errors"] += 1

    if not dry_run and (results["matched"] > 0 or results["clf_scored"] > 0):
        db_session.commit()

    logger.info("Accuracy computation: %s", results)
    return results


def get_accuracy_summary(db_session, asset_id: int = None, horizon: int = None) -> dict:
    """Get accuracy summary statistics from prediction_errors (REAL only)."""
    conditions = ["data_origin = 'REAL'", "model_version NOT LIKE 'flood_classifier%'"]
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
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    from infrastructure.db.engine import SessionLocal

    with SessionLocal() as db:
        results = compute_accuracy(db)
        print(f"\nAccuracy results: {results}")

        summary = get_accuracy_summary(db)
        print(f"Summary: {summary}")
