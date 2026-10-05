# tests/unit/test_ingestion_quality.py
# P3 data-quality gates: FFD rows are validated against sanity ranges before
# store, with INVALID rows quarantined + logged to aquavision.data_quality_log.
from datetime import datetime, timedelta, timezone

from infrastructure.ingestion.validators import (
    build_quarantine_record, validate_observation,
)


def ffd_row(gauge=None, discharge=None):
    return {"water_level_ft": gauge, "discharge_cusecs": discharge}


def test_valid_ffd_reading_passes():
    result = validate_observation(ffd_row(gauge=25.4, discharge=13_400), asset_id=9)
    assert result.is_valid
    assert result.quality_status == "VALID"
    assert result.violations == []
    assert build_quarantine_record(ffd_row(gauge=25.4, discharge=13_400), 9, result) is None


def test_negative_discharge_is_invalid_and_quarantined():
    row = ffd_row(gauge=20.0, discharge=-500)
    result = validate_observation(row, asset_id=10)
    assert not result.is_valid
    assert result.quality_status == "INVALID"
    assert any(v["check"] == "NEGATIVE_VALUE" for v in result.violations)

    quarantine = build_quarantine_record(row, 10, result, source_record_id=77)
    assert quarantine is not None
    assert quarantine.asset_id == 10
    assert quarantine.field_name == "discharge_cusecs"
    assert quarantine.source_record_id == 77
    assert "NEGATIVE_VALUE" in quarantine.failure_reason


def test_gauge_above_sanity_max_is_invalid():
    result = validate_observation(ffd_row(gauge=5000, discharge=1000), asset_id=1)
    assert result.quality_status == "INVALID"
    assert any(v["check"] == "OUT_OF_RANGE" for v in result.violations)


def test_future_timestamp_is_invalid():
    future = datetime.now(timezone.utc) + timedelta(days=2)
    result = validate_observation(ffd_row(gauge=20, discharge=1000), asset_id=1, observed_at=future)
    assert result.quality_status == "INVALID"
    assert any(v["check"] == "FUTURE_TIMESTAMP" for v in result.violations)


def test_empty_reading_is_missing_not_invalid():
    result = validate_observation(ffd_row(), asset_id=1)
    assert result.quality_status == "MISSING"
    assert not result.is_valid
    assert build_quarantine_record(ffd_row(), 1, result) is None


def test_outflow_over_twice_inflow_is_suspect_not_invalid():
    result = validate_observation(
        {"inflow_cusecs": 10_000, "outflow_cusecs": 30_000}, asset_id=2
    )
    assert result.is_valid
    assert result.quality_status == "SUSPECT"
    assert result.warnings
