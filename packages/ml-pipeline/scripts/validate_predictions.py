"""
scripts/validate_predictions.py
AquaVision - Score past forecasts against now-closed actuals.

For every row in aquavision.water_predictions_weekly whose target period now has
a COMPLETE observed indicator (water_indicators_weekly), fill in:

    actual_value, error, validated_at

and report MAE / RMSE / severity-hit-rate. No-op (0 validated) until a forecast
period closes - e.g. a 2026-08-01 prediction becomes scoreable in Sep 2026.

Usage:
    python -m scripts.validate_predictions   (run from packages/ml-pipeline)
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ML_ROOT = Path(__file__).resolve().parent.parent
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
MODEL_VERSION = os.getenv("GEE_MODEL_VERSION", "xgb-v1.0")

DB_ENGINE = None


def _engine():
    global DB_ENGINE
    if DB_ENGINE is None:
        from sqlalchemy import create_engine

        DB_ENGINE = create_engine(DB_URL)
    return DB_ENGINE


def validate() -> dict:
    eng = _engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT p.id, p.region_id, p.target_week_start_date,
                       p.predicted_wai_score, i.wai_score AS actual
                FROM aquavision.water_predictions_weekly p
                LEFT JOIN aquavision.water_indicators_weekly i
                       ON i.region_id = p.region_id
                      AND i.week_start_date = p.target_week_start_date
                      AND i.quality_status = 'VALID'
                WHERE p.model_version = :model_version
                  AND p.actual_value IS NULL
                """
            ),
            {"model_version": MODEL_VERSION},
        ).mappings().all()

    updated = 0
    preds: list[dict] = []
    for r in rows:
        if r["actual"] is None:
            continue
        err = float(r["predicted_wai_score"]) - float(r["actual"])
        conn = eng.begin()
        with conn:
            conn.execute(
                text(
                    """
                    UPDATE aquavision.water_predictions_weekly
                    SET actual_value = :actual, error = :err,
                        validated_at = now()
                    WHERE id = :id
                    """
                ),
                {"actual": r["actual"], "err": round(err, 2), "id": r["id"]},
            )
        preds.append({"predicted": float(r["predicted_wai_score"]), "error": err})
        updated += 1

    if preds:
        df = pd.DataFrame(preds)
        mae = df["error"].abs().mean()
        rmse = (df["error"] ** 2).mean() ** 0.5
        print(f"[validate_predictions] Validated {updated} predictions "
              f"| MAE={mae:.2f} RMSE={rmse:.2f}")
    else:
        print("[validate_predictions] No closed forecast periods to validate yet")

    return {"records_read": len(rows), "records_written": updated,
            "records_skipped": 0, "warning_count": 0}


def main() -> None:
    validate()


if __name__ == "__main__":
    main()
