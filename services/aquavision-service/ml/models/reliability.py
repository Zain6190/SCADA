"""Per-asset forecast reliability, scored from REAL prediction_errors.

A model with one scored forecast or a 700% MAPE must never render with the
same confidence as a validated one — the dashboard badges come from here.
Tiers are deliberately conservative: without a track record a model is
"not yet validated", not "good".
"""
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

VALIDATED = "VALIDATED"
TRACKING = "TRACKING"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
UNRELIABLE = "UNRELIABLE"
UNPROVEN = "UNPROVEN"

MIN_FOR_TIERS = 5
MIN_FOR_VALIDATED = 14
LOW_MAPE = 40.0
HIGH_MAPE = 100.0

VALID_TONES = {"neutral", "info", "ok", "warn", "crit"}


def assess_reliability(n: int, mape: Optional[float]) -> Dict[str, str]:
    """Tier one asset's scored-forecast history (pure).

    Args:
        n: number of REAL scored forecasts on record.
        mape: mean absolute percentage error, or None when unscored.

    Returns:
        dict with tier, label and badge tone (tone matches ui/badge TONES).
    """
    if n < MIN_FOR_TIERS or mape is None:
        return {"tier": UNPROVEN, "label": "Not yet validated", "tone": "neutral"}
    if mape > HIGH_MAPE:
        return {"tier": UNRELIABLE, "label": "High error", "tone": "crit"}
    if mape > LOW_MAPE:
        return {"tier": LOW_CONFIDENCE, "label": "Low accuracy", "tone": "warn"}
    if n < MIN_FOR_VALIDATED:
        return {"tier": TRACKING, "label": "Early tracking", "tone": "info"}
    return {"tier": VALIDATED, "label": "Validated", "tone": "ok"}


def fetch_reliability(session: Session) -> Dict[str, dict]:
    """Reliability record for every active asset, keyed by asset id string.

    Only REAL scored forecasts count — reanalysis or synthetic rows never
    enter the accuracy history.
    """
    rows = session.execute(
        text(
            """
            SELECT a.id, a.canonical_name,
                   COUNT(e.id) AS n,
                   AVG(e.error_pct) AS mape,
                   MIN(e.target_date) AS first_scored,
                   MAX(e.target_date) AS last_scored
            FROM aquavision.water_assets a
            LEFT JOIN aquavision.prediction_errors e
              ON e.asset_id = a.id AND e.data_origin = 'REAL'
            WHERE a.is_active
            GROUP BY a.id, a.canonical_name
            ORDER BY a.id
            """
        )
    ).mappings().all()

    assets: Dict[str, dict] = {}
    for row in rows:
        n = int(row["n"])
        mape = round(float(row["mape"]), 1) if row["mape"] is not None else None
        first = row["first_scored"]
        last = row["last_scored"]
        entry = {
            "asset_id": int(row["id"]),
            "asset_name": row["canonical_name"],
            "n": n,
            "mape_pct": mape,
            "first_scored": first.strftime("%Y-%m-%d") if first else None,
            "last_scored": last.strftime("%Y-%m-%d") if last else None,
        }
        entry.update(assess_reliability(n, mape))
        assets[str(row["id"])] = entry
    return assets
