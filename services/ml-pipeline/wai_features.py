"""Shared WAI feature contract for train / predict / risk stages.

Training and serving must feed the model the exact same columns, and every
input must be reproducible at serving time:
  - rainfall/ET/water extent/NDVI/soil moisture: predict_weekly and
    run_risk_alerts read the same Data/raw/region_features.csv the trainer
    uses, so all raw GEE columns are servable.
  - month_idx: derived from the input month.
  - current_wai: latest observed WAI for the input month from
    aquavision.water_indicators_weekly (always present once any label
    exists for the region).

The regressor predicts the month-over-month DELTA of WAI; serving computes
level = current_wai + delta. Tree models cannot extrapolate past the training
range, so predicting the bounded delta keeps serving sane in record regimes
(see models/train_wai.py).
"""
from __future__ import annotations

FEATURE_COLS = [
    "rainfall_mm",
    "et_mm",
    "water_extent",
    "ndvi",
    "sm_rootzone",
    "sm_surface",
    "month_idx",
    "current_wai",
]
TARGET_COL = "wai_score"
SEVERITY_COL = "severity"


def fetch_known_regions(engine) -> set[int]:
    """Region IDs registered in shared.regions — predictions/alerts for
    anything else would violate the FK on water_* tables (the GEE CSV carries
    feature rows for regions the app never registered)."""
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM shared.regions")).fetchall()
    return {int(r.id) for r in rows}


def fetch_current_wai(engine, month) -> dict[int, float]:
    """Most recent observed WAI per region up to (not past) the given month —
    how serving supplies current_wai. Regions whose latest row predates the
    month fall back to that older observation instead of feeding NaN."""
    import pandas as pd
    from sqlalchemy import text

    nxt = (pd.Timestamp(month) + pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT ON (region_id) region_id, wai_score
                FROM aquavision.water_indicators_weekly
                WHERE week_start_date < :nxt
                  AND wai_score IS NOT NULL
                ORDER BY region_id, week_start_date DESC
                """
            ),
            {"nxt": nxt},
        ).fetchall()
    return {int(r.region_id): float(r.wai_score) for r in rows}
