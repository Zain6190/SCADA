# infrastructure/ingestion/validators.py
# Data validation layer for ingestion pipeline.
# Validates observations against physical sanity ranges before storage.
# Separates data_status (source type) from quality_status (validity).

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("aquavision.ingestion.validators")


# ─── Sanity Ranges (catch parser/unit errors) ────────────────────────────
# These are NOT operational thresholds. They only detect impossible values.

SANITY_RANGES: Dict[str, Dict[str, float]] = {
    "water_level_ft": {"min": 0, "max": 2000},
    "inflow_cusecs": {"min": 0, "max": 2_000_000},
    "outflow_cusecs": {"min": 0, "max": 2_000_000},
    "discharge_cusecs": {"min": 0, "max": 2_000_000},
    "upstream_discharge_cusecs": {"min": 0, "max": 2_000_000},
    "downstream_discharge_cusecs": {"min": 0, "max": 2_000_000},
    "gauge_level_ft": {"min": 0, "max": 2000},
}


@dataclass
class ValidationResult:
    """Result of validating a single observation."""
    is_valid: bool
    quality_status: str  # VALID, SUSPECT, INVALID, MISSING
    violations: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class QuarantineRecord:
    """Record to store in quarantine table for invalid observations."""
    asset_id: int
    raw_payload: dict
    parsed_values: dict
    failure_reason: str
    field_name: Optional[str] = None
    raw_value: Optional[float] = None
    parser_version: Optional[str] = None
    data_status: Optional[str] = None


def validate_observation(
    obs: dict,
    asset_id: int,
    observed_at: Optional[datetime] = None,
    source_date: Optional[datetime] = None,
) -> ValidationResult:
    """Validate a single observation against sanity checks.

    Checks performed:
    1. Field presence (at least one value)
    2. Negative value check
    3. Range check against sanity bounds
    4. Timestamp validation (not in future)
    5. Staleness check (if source_date provided)
    6. Cross-field consistency

    Args:
        obs: Dictionary with observation values
        asset_id: Asset ID for logging
        observed_at: When the observation was made
        source_date: Date of the source data (for staleness check)

    Returns:
        ValidationResult with quality_status and violations
    """
    violations = []
    warnings = []

    # Check 1: At least one value must be present
    value_fields = [
        "water_level_ft", "inflow_cusecs", "outflow_cusecs",
        "discharge_cusecs", "upstream_discharge_cusecs", "downstream_discharge_cusecs"
    ]
    has_any_value = any(obs.get(f) is not None for f in value_fields)
    if not has_any_value:
        return ValidationResult(
            is_valid=False,
            quality_status="MISSING",
            violations=[{"check": "FIELD_PRESENCE", "detail": "No numeric values present"}],
        )

    # Check 2-3: Range and negative checks
    for field_name, limits in SANITY_RANGES.items():
        value = obs.get(field_name)
        if value is None:
            continue

        try:
            value = float(value)
        except (TypeError, ValueError):
            violations.append({
                "check": "TYPE_ERROR",
                "field": field_name,
                "detail": f"Cannot convert {value} to float",
            })
            continue

        if value < 0:
            violations.append({
                "check": "NEGATIVE_VALUE",
                "field": field_name,
                "detail": f"{field_name}={value} is negative",
                "raw_value": str(value),
            })
        elif value > limits["max"]:
            violations.append({
                "check": "OUT_OF_RANGE",
                "field": field_name,
                "detail": f"{field_name}={value} exceeds max {limits['max']}",
                "raw_value": str(value),
                "range_max": str(limits["max"]),
            })

    # Check 4: Timestamp not in future
    if observed_at and observed_at > datetime.now(timezone.utc):
        violations.append({
            "check": "FUTURE_TIMESTAMP",
            "field": "observed_at",
            "detail": f"observed_at={observed_at} is in the future",
        })

    # Check 5: Staleness (if source_date provided)
    if source_date:
        age_hours = (datetime.now(timezone.utc) - source_date).total_seconds() / 3600
        if age_hours > 48:
            warnings.append(f"Data is {age_hours:.1f}h old (stale)")

    # Check 6: Cross-field consistency
    inflow = obs.get("inflow_cusecs")
    outflow = obs.get("outflow_cusecs")
    if inflow is not None and outflow is not None:
        try:
            inflow_f = float(inflow)
            outflow_f = float(outflow)
            if outflow_f > inflow_f * 2 and inflow_f > 0:
                warnings.append(f"Outflow ({outflow_f}) > 2x inflow ({inflow_f})")
        except (TypeError, ValueError):
            pass

    # Determine quality status
    if violations:
        quality_status = "INVALID"
        is_valid = False
    elif warnings and any("stale" in w.lower() for w in warnings):
        quality_status = "STALE"
        is_valid = True
    elif warnings:
        quality_status = "SUSPECT"
        is_valid = True
    else:
        quality_status = "VALID"
        is_valid = True

    return ValidationResult(
        is_valid=is_valid,
        quality_status=quality_status,
        violations=violations,
        warnings=warnings,
    )


def build_quarantine_record(
    obs: dict,
    asset_id: int,
    validation_result: ValidationResult,
    source_record_id: Optional[int] = None,
    parser_version: Optional[str] = None,
) -> Optional[QuarantineRecord]:
    """Build a quarantine record for an invalid observation.

    Returns None if the observation is valid.
    """
    if validation_result.quality_status != "INVALID":
        return None

    # Find the primary violating field
    field_name = None
    raw_value = None
    failure_reasons = []

    for v in validation_result.violations:
        failure_reasons.append(f"{v.get('check', 'UNKNOWN')}: {v.get('detail', '')}")
        if "field" in v and field_name is None:
            field_name = v["field"]
            raw_value = v.get("raw_value")

    return QuarantineRecord(
        asset_id=asset_id,
        raw_payload=obs,
        parsed_values={k: v for k, v in obs.items() if v is not None},
        failure_reason="; ".join(failure_reasons),
        field_name=field_name,
        raw_value=float(raw_value) if raw_value else None,
        parser_version=parser_version,
        data_status=obs.get("data_status", "OBSERVED_OFFICIAL"),
    )


def validate_batch(
    observations: List[dict],
    asset_id: int,
    parser_version: Optional[str] = None,
) -> Tuple[List[dict], List[dict], List[QuarantineRecord]]:
    """Validate a batch of observations.

    Returns:
        (valid_obs, suspect_obs, quarantine_records)
    """
    valid_obs = []
    suspect_obs = []
    quarantine_records = []

    for obs in observations:
        result = validate_observation(obs, asset_id)

        if result.quality_status == "INVALID":
            quarantine = build_quarantine_record(obs, asset_id, result, parser_version=parser_version)
            if quarantine:
                quarantine_records.append(quarantine)
            logger.warning(
                f"Asset {asset_id}: INVALID observation quarantined - "
                f"{[v['detail'] for v in result.violations]}"
            )
        elif result.quality_status in ("SUSPECT", "STALE"):
            obs["quality_status"] = result.quality_status
            suspect_obs.append(obs)
        else:
            obs["quality_status"] = "VALID"
            valid_obs.append(obs)

    return valid_obs, suspect_obs, quarantine_records
