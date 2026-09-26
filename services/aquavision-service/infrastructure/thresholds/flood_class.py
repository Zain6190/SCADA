"""Unit-aware flood classification from operational thresholds.

Single source of truth for comparing an observation against the rows in
aquavision.water_asset_thresholds. A level reading is only ever compared
against level thresholds, a discharge reading only against discharge
thresholds, and inflow alone never classifies. With no usable thresholds
the result is None: no classification rather than a guess.
"""

from __future__ import annotations

from typing import Optional, Tuple


def classify_flood(
    *,
    level: Optional[float],
    discharge: Optional[float],
    warning_level_ft: Optional[float] = None,
    critical_level_ft: Optional[float] = None,
    warning_discharge: Optional[float] = None,
    danger_discharge: Optional[float] = None,
) -> Optional[Tuple[float, str, str]]:
    """Classify a reading against its own unit's thresholds.

    Returns (probability, severity, recommendation) or None when no
    matching threshold pair exists for the reading's unit.
    """
    if level is not None:
        classified = _classify_level(
            level,
            warning_level_ft=warning_level_ft,
            critical_level_ft=critical_level_ft,
        )
        if classified is not None:
            return classified

    if discharge is not None:
        return _classify_discharge(
            discharge,
            warning_discharge=warning_discharge,
            danger_discharge=danger_discharge,
        )

    return None


def _classify_level(
    level: float,
    *,
    warning_level_ft: Optional[float],
    critical_level_ft: Optional[float],
) -> Optional[Tuple[float, str, str]]:
    if not warning_level_ft or not critical_level_ft:
        return None
    warn = float(warning_level_ft)
    crit = float(critical_level_ft)
    if crit <= warn or level < warn:
        return None
    ratio = min((level - warn) / (crit - warn), 1.0)
    probability = round(0.05 + ratio * 0.85, 4)
    if ratio > 0.8:
        severity = "CRITICAL"
    elif ratio > 0.5:
        severity = "HIGH"
    elif ratio > 0.2:
        severity = "MODERATE"
    else:
        severity = "LOW"
    return probability, severity, f"Level at {ratio * 100:.0f}% of critical threshold"


def _classify_discharge(
    discharge: float,
    *,
    warning_discharge: Optional[float],
    danger_discharge: Optional[float],
) -> Optional[Tuple[float, str, str]]:
    if not warning_discharge or not danger_discharge:
        return None
    warn = float(warning_discharge)
    danger = float(danger_discharge)
    if danger <= warn or discharge < warn:
        return None
    ratio = min((discharge - warn) / (danger - warn), 1.0)
    probability = round(0.05 + ratio * 0.85, 4)
    if ratio >= 1.0:
        severity = "CRITICAL"
    elif ratio >= 0.5:
        severity = "HIGH"
    else:
        severity = "MODERATE"
    return probability, severity, f"Discharge at {ratio * 100:.0f}% of danger threshold"
