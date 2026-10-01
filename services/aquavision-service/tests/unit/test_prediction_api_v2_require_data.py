from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ml.prediction_api_v2 import _require_data, mean_wai, partition_real_forecasts


def test_require_data_raises_for_no_data_placeholder():
    result = SimpleNamespace(asset_id=7, model_metadata={"status": "NO_DATA"})
    with pytest.raises(HTTPException) as exc:
        _require_data(result)
    assert exc.value.status_code == 404
    assert "asset 7" in exc.value.detail


def test_require_data_allows_trained_model():
    result = SimpleNamespace(
        asset_id=7, model_metadata={"status": "TRAINED", "model_version": "xgb-v1.0"}
    )
    assert _require_data(result) is None


def test_require_data_tolerates_missing_metadata_status():
    result = SimpleNamespace(asset_id=7, model_metadata={})
    assert _require_data(result) is None


def _forecast(value, category, alerts=None, status=None):
    metadata = {"model_version": "2.0"}
    if status:
        metadata["status"] = status
    return SimpleNamespace(
        model_metadata=metadata,
        predictions={
            "7_day": SimpleNamespace(
                water_stress=SimpleNamespace(value=value, category=category),
            ),
        },
        alerts=alerts or [],
    )


def test_partition_skips_no_data_placeholder():
    placeholder = _forecast(50, "Moderate", alerts=[{"level": "CRITICAL"}], status="NO_DATA")
    real = _forecast(72, "Moderate", alerts=[{"level": "HIGH"}])

    kept, scores, alerts = partition_real_forecasts([placeholder, real])

    assert kept == [real]
    assert scores == [72]
    assert alerts == [{"level": "HIGH"}]


def test_empty_overview_does_not_default_wai_to_50():
    placeholder = _forecast(50, "Moderate", status="NO_DATA")
    kept, scores, alerts = partition_real_forecasts([placeholder])

    assert kept == []
    assert scores == []
    assert alerts == []
    assert mean_wai(scores) is None
    assert mean_wai([]) is None


def test_unscored_stress_is_not_averaged_as_zero():
    unscored = _forecast(0, "No Data")
    scored = _forecast(80, "Abundant")

    kept, scores, _alerts = partition_real_forecasts([unscored, scored])

    assert len(kept) == 2
    assert scores == [80]
    assert mean_wai(scores) == 80
