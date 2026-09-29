from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ml.prediction_api_v2 import _require_data


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
