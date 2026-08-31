# domain/services/channel_condition_service.py
# Module 6.4: classify river and canal condition.
#
# Pure logic - no database, no network - so the classification rules can be
# tested directly and reused by both producers:
#
#   GAUGE_DISCHARGE  official IRSA canal withdrawals (available today)
#   NDWI_MASK        Sentinel-2 water mask sampled along the channel (needs GEE)
#
# Both write aquavision.water_channel_condition. The `method` column keeps them
# distinguishable so a gauge reading is never presented as a satellite estimate.

from __future__ import annotations

from statistics import median
from typing import Final, List, Optional, Sequence

# Condition bands, worst first.
CONDITION_DRY: Final = "DRY"
CONDITION_LOW: Final = "LOW"
CONDITION_REDUCED: Final = "REDUCED"
CONDITION_FLOWING: Final = "FLOWING"
CONDITION_UNKNOWN: Final = "UNKNOWN"

CONDITION_ORDER: Final[dict] = {
    CONDITION_UNKNOWN: -1,
    CONDITION_FLOWING: 0,
    CONDITION_REDUCED: 1,
    CONDITION_LOW: 2,
    CONDITION_DRY: 3,
}

# Percentage shortfall against baseline that defines each band.
THRESHOLD_LOW_PCT: Final = -60.0
THRESHOLD_REDUCED_PCT: Final = -25.0

# A baseline computed from too few weeks is not a baseline.
MIN_BASELINE_SAMPLES: Final = 4

# Satellite path: fraction of the channel buffer classified as water.
WET_DRY_MAX: Final = 0.10
WET_LOW_MAX: Final = 0.35
WET_REDUCED_MAX: Final = 0.65


def rolling_baseline(history: Sequence[float]) -> Optional[float]:
    """Normal discharge for a channel, as the median of prior observations.

    Median rather than mean: canal operation is rotational, so a few scheduled
    closures at zero would drag a mean down and make a genuinely dry week look
    normal.
    """
    values = [v for v in history if v is not None]
    if len(values) < MIN_BASELINE_SAMPLES:
        return None
    return float(median(values))


def change_pct(current: float, baseline: Optional[float]) -> Optional[float]:
    """Percentage change against baseline. None when there is no baseline."""
    if baseline is None or baseline <= 0:
        return None
    return round((current - baseline) / baseline * 100.0, 2)


def classify_gauge(discharge: Optional[float], baseline: Optional[float]) -> str:
    """Classify a canal from its measured discharge.

    A canal at zero is DRY regardless of baseline - that is an observation, not
    an inference, and it is exactly the "low-water section" the module exists to
    surface. Whether the closure is a scheduled rotation is an operational
    question for the reviewer, not something to hide by suppressing the signal.
    """
    if discharge is None:
        return CONDITION_UNKNOWN
    if discharge <= 0:
        return CONDITION_DRY

    pct = change_pct(discharge, baseline)
    if pct is None:
        # Flow is present but there is no baseline to judge it against.
        return CONDITION_UNKNOWN
    if pct <= THRESHOLD_LOW_PCT:
        return CONDITION_LOW
    if pct <= THRESHOLD_REDUCED_PCT:
        return CONDITION_REDUCED
    return CONDITION_FLOWING


def classify_ndwi(wet_fraction: Optional[float]) -> str:
    """Classify a channel from the wet fraction of its buffered geometry.

    Absolute bands rather than a baseline comparison: a channel's wet fraction
    is already normalised by its own length, and a historical baseline needs
    JRC data that ends in 2021.
    """
    if wet_fraction is None:
        return CONDITION_UNKNOWN
    if wet_fraction <= WET_DRY_MAX:
        return CONDITION_DRY
    if wet_fraction <= WET_LOW_MAX:
        return CONDITION_LOW
    if wet_fraction <= WET_REDUCED_MAX:
        return CONDITION_REDUCED
    return CONDITION_FLOWING


def worst_condition(conditions: Sequence[str]) -> str:
    """Most severe condition in a set - used to roll a river up from segments."""
    known = [c for c in conditions if c in CONDITION_ORDER and c != CONDITION_UNKNOWN]
    if not known:
        return CONDITION_UNKNOWN
    return max(known, key=lambda c: CONDITION_ORDER[c])


def needs_attention(condition: str) -> bool:
    """Whether this condition should raise an operational alert."""
    return condition in (CONDITION_LOW, CONDITION_DRY)


def assess_gauge_series(readings: List[tuple]) -> List[dict]:
    """Turn a channel's dated discharge readings into condition rows.

    Args:
        readings: (observed_week, discharge_cusecs) in ascending date order.

    Each week is judged against the weeks BEFORE it only - never the full
    series, which would leak future observations into a past classification.
    """
    out = []
    history: List[float] = []

    for week, discharge in readings:
        baseline = rolling_baseline(history)
        condition = classify_gauge(discharge, baseline)
        out.append({
            "observed_week": week,
            "method": "GAUGE_DISCHARGE",
            "discharge_cusecs": discharge,
            "baseline": baseline,
            "change_pct": change_pct(discharge, baseline) if discharge is not None else None,
            "condition": condition,
            "sample_count": len(history),
        })
        if discharge is not None:
            history.append(discharge)

    return out
