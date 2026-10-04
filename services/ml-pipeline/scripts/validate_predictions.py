"""
scripts/validate_predictions.py
AquaVision - Score past forecasts against now-closed actuals.

For every row in aquavision.water_predictions_weekly whose target period now has
a COMPLETE observed indicator (water_indicators_weekly), fill in:

    actual_value, error, validated_at

and report MAE / RMSE plus a confidence-calibration check: the |error|<=10
hit-rate vs the mean stored confidence, and lower/upper band coverage vs the
80% target. Scores every model version present (historical rows and current
rows share the table); set GEE_MODEL_VERSION to restrict to one version.
No-op (0 validated) until a forecast period closes - e.g. a 2026-08-01
prediction becomes scoreable in Sep 2026.

Usage:
    python -m scripts.validate_predictions   (run from services/ml-pipeline)
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
MODEL_VERSION = os.getenv("GEE_MODEL_VERSION") or None

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
                       p.model_version,
                       p.predicted_wai_score, p.confidence,
                       p.lower_bound, p.upper_bound,
                       i.wai_score AS actual
                FROM aquavision.water_predictions_weekly p
                LEFT JOIN aquavision.water_indicators_weekly i
                       ON i.region_id = p.region_id
                      AND i.week_start_date = p.target_week_start_date
                      AND i.quality_status = 'VALID'
                WHERE (:model_version IS NULL OR p.model_version = :model_version)
                  AND p.actual_value IS NULL
                """
            ),
            {"model_version": MODEL_VERSION},
        ).mappings().all()

    updated = 0
    preds: list[dict] = []
    confs: list[float] = []
    band_hits: list[bool] = []
    if rows:
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["model_version"]] = counts.get(r["model_version"], 0) + 1
        print(
            "[validate_predictions] candidates by model_version: "
            + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        )
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
        if r["confidence"] is not None:
            confs.append(float(r["confidence"]))
        if r["lower_bound"] is not None and r["upper_bound"] is not None:
            band_hits.append(
                float(r["lower_bound"]) <= float(r["actual"]) <= float(r["upper_bound"])
            )
        updated += 1

    if preds:
        df = pd.DataFrame(preds)
        mae = df["error"].abs().mean()
        rmse = (df["error"] ** 2).mean() ** 0.5
        print(f"[validate_predictions] Validated {updated} predictions "
              f"| MAE={mae:.2f} RMSE={rmse:.2f}")
        hit10 = float((df["error"].abs() <= 10.0).mean())
        if confs:
            mean_conf = sum(confs) / len(confs)
            print(
                f"[validate_predictions] calibration: |error|<=10 hit-rate "
                f"{hit10:.2f} vs mean confidence {mean_conf:.2f} "
                f"(gap {hit10 - mean_conf:+.2f}; positive = model too modest)"
            )
        if band_hits:
            print(
                f"[validate_predictions] 80% band coverage on scored rows: "
                f"{sum(band_hits) / len(band_hits):.2f} ({len(band_hits)} rows)"
            )
    else:
        print("[validate_predictions] No closed forecast periods to validate yet")

    return {"records_read": len(rows), "records_written": updated,
            "records_skipped": 0, "warning_count": 0}


def main() -> None:
    validate()


if __name__ == "__main__":
    main()
