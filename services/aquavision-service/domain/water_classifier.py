# domain/water_classifier.py
# Pure logic: maps a WAI score (0-100) to a severity class.
from typing import Final

SEVERITY_ORDER: Final[list[str]] = [
    "Normal",
    "Moderate",
    "Stressed",
    "Critical",
    "Severe",
]

# Ascending order of risk (used to pick the worst severity).
RISK_RANK: Final[dict[str, int]] = {
    "Normal": 0,
    "Moderate": 1,
    "Stressed": 2,
    "Critical": 3,
    "Severe": 4,
}

# Default thresholds - mirror DB seed values (aquavision.water_thresholds).
DEFAULT_THRESHOLDS: Final[dict[str, float]] = {
    "wai_critical_min": 25.0,
    "wai_severe_min": 40.0,
    "wai_stressed_min": 55.0,
    "rainfall_deficit_pct": -30.0,
    "et_anomaly_high": 25.0,
}


def classify_severity(wai: float, thresholds: dict[str, float] | None = None) -> str:
    """Classify a 0-100 WAI into a severity band (low score == high stress)."""
    t = thresholds or DEFAULT_THRESHOLDS
    if wai < t["wai_critical_min"]:
        return "Critical"
    if wai < t["wai_severe_min"]:
        return "Severe"
    if wai < t["wai_stressed_min"]:
        return "Stressed"
    if wai < 70:
        return "Moderate"
    return "Normal"


def worst_severity(severities: list[str]) -> str:
    """Return the most severe entry from a list (used by overview KPIs)."""
    if not severities:
        return "Unknown"
    return max(severities, key=lambda s: RISK_RANK.get(s, -1))


def is_critical_or_severe(severity: str) -> bool:
    return severity in ("Critical", "Severe")
