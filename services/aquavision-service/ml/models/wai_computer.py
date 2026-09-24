"""Real-time Water Availability Index (WAI) from live observations.

Replaces reliance on static water_indicators_weekly rows (stale after
GEE sync stops). Computes a transparent 0-100 composite per asset from
REAL hydrology only — no dummy defaults, no synthetic rows.

Components (renormalized when a piece is missing):
  flow     0.50  current discharge/inflow percentile vs trailing history
  storage  0.30  storage_percent (reservoirs; omitted for barrages)
  trend    0.20  7-day mean vs prior 7-day mean (higher = more water)

rainfall_anomaly / et_anomaly stay None without weather observations —
callers must not invent them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger("aquavision.ml.wai_computer")

# Trailing window used for percentile + trend baselines
HISTORY_DAYS = 90
TREND_DAYS = 7

WEIGHTS = {
    "flow": 0.50,
    "storage": 0.30,
    "trend": 0.20,
}


def _percentile_rank(history: list[float], current: float) -> Optional[float]:
    """0-100 rank of current within history (inclusive). None if no baseline."""
    if not history:
        return None
    below = sum(1 for v in history if v <= current)
    return 100.0 * below / len(history)


def compute_realtime_wai(
    session,
    asset_id: int,
    as_of: Optional[datetime] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (wai, rainfall_anomaly, et_anomaly) for one asset.

    wai is None when there is no REAL observation history to score against.
    rainfall_anomaly and et_anomaly are always None here (no weather feed).
    """
    if session is None:
        return None, None, None

    as_of = as_of or datetime.utcnow()
    start = as_of - timedelta(days=HISTORY_DAYS)

    rows = session.execute(
        text(
            """
            SELECT observed_at,
                   COALESCE(discharge_cusecs, inflow_cusecs, outflow_cusecs) AS flow,
                   storage_percent
            FROM aquavision.water_observations
            WHERE asset_id = :aid
              AND data_origin = 'REAL'
              AND observed_at >= :start
              AND observed_at <= :as_of
            ORDER BY observed_at
            """
        ),
        {"aid": asset_id, "start": start, "as_of": as_of},
    ).mappings().all()

    if not rows:
        logger.debug("No REAL observations for asset %s in %sd window", asset_id, HISTORY_DAYS)
        return None, None, None

    flows = [float(r["flow"]) for r in rows if r["flow"] is not None]
    if not flows:
        return None, None, None

    current_flow = flows[-1]
    history = flows[:-1] if len(flows) > 1 else []
    flow_score = _percentile_rank(history, current_flow)
    if flow_score is None:
        # Single sample: treat as midpoint rather than inventing 0/100
        flow_score = 50.0

    # Storage: latest non-null storage_percent in window
    storage_score = None
    for r in reversed(rows):
        if r["storage_percent"] is not None:
            storage_score = max(0.0, min(100.0, float(r["storage_percent"])))
            break

    # Trend: mean of last TREND_DAYS vs prior TREND_DAYS of flow
    trend_score = None
    if len(flows) >= 4:
        recent = flows[-TREND_DAYS:]
        prior = flows[-2 * TREND_DAYS : -TREND_DAYS]
        if prior:
            prior_mean = sum(prior) / len(prior)
            recent_mean = sum(recent) / len(recent)
            if prior_mean > 0:
                pct = (recent_mean - prior_mean) / prior_mean * 100.0
                # Map ±50% change onto 0-100 with 50 = flat
                trend_score = max(0.0, min(100.0, 50.0 + pct))
            else:
                trend_score = 50.0

    parts = {
        "flow": flow_score,
        "storage": storage_score,
        "trend": trend_score,
    }
    present = {k: v for k, v in parts.items() if v is not None}
    if not present:
        return None, None, None

    weight_sum = sum(WEIGHTS[k] for k in present)
    wai = sum(present[k] * WEIGHTS[k] for k in present) / weight_sum
    wai = round(max(0.0, min(100.0, wai)), 2)

    return wai, None, None


def get_wai_for_prediction(
    session,
    asset_id: int,
    stale_indicator_wai: Optional[float] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Prefer real-time composite; fall back to a weekly indicator only if
    real-time scoring is impossible. Never invent a default score."""
    realtime, rain, et = compute_realtime_wai(session, asset_id)
    if realtime is not None:
        return realtime, rain, et
    if stale_indicator_wai is not None:
        logger.debug(
            "asset %s: no REAL history, using weekly indicator wai=%s",
            asset_id,
            stale_indicator_wai,
        )
        return stale_indicator_wai, None, None
    return None, None, None
