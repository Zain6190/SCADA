from types import SimpleNamespace
from datetime import datetime, timezone

import numpy as np
import pytest

from ml.features import feature_engineering as fe
from ml.features.feature_engineering import FloodFeatureBuilder


def _obs(days: int) -> list[dict]:
    return [
        {
            "date": datetime(2026, 8, 1).replace(day=(i % 28) + 1),
            "level": 1000.0 + i,
            "inflow": 500.0 + i,
            "outflow": 480.0 + i,
            "discharge": 900.0 + i,
            "data_origin": "REAL",
            "source": "IRSA",
        }
        for i in range(days)
    ]


@pytest.fixture
def pure_builder(monkeypatch):
    monkeypatch.setattr(FloodFeatureBuilder, "_get_threshold", lambda self, aid: None)
    monkeypatch.setattr(FloodFeatureBuilder, "_get_ffd_status", lambda self, aid, d: None)
    monkeypatch.setattr(
        FloodFeatureBuilder, "_get_weather_forecast", lambda self, aid, dt: None
    )
    monkeypatch.setattr(FloodFeatureBuilder, "_get_gee_row", lambda self, aid, dt: None)
    return FloodFeatureBuilder(session=None)


def test_serving_features_default_to_training_policy(pure_builder, monkeypatch):
    calls = []

    def fake_get(self, asset_id, start, end, real_only=False, source_priority=False):
        calls.append({"real_only": real_only, "source_priority": source_priority})
        return _obs(40)

    monkeypatch.setattr(FloodFeatureBuilder, "_get_observations", fake_get)

    X, names = pure_builder.build_prediction_features(
        asset_id=1, as_of_date=datetime.now(timezone.utc)
    )

    assert X is not None
    assert X.shape == (1, len(names))
    assert calls == [{"real_only": True, "source_priority": True}]


def test_serving_features_fallback_to_raw_when_view_masks_real_rows(
    pure_builder, monkeypatch
):
    calls = []

    def fake_get(self, asset_id, start, end, real_only=False, source_priority=False):
        calls.append(source_priority)
        return _obs(40) if not source_priority else _obs(4)

    monkeypatch.setattr(FloodFeatureBuilder, "_get_observations", fake_get)

    X, names = pure_builder.build_prediction_features(
        asset_id=10, as_of_date=datetime.now(timezone.utc)
    )

    assert X is not None
    assert calls == [True, False]
    assert X.shape == (1, len(names))


def test_serving_features_return_none_when_no_real_data(pure_builder, monkeypatch):
    monkeypatch.setattr(
        FloodFeatureBuilder, "_get_observations",
        lambda self, asset_id, start, end, real_only=False, source_priority=False: _obs(3),
    )

    X, names = pure_builder.build_prediction_features(
        asset_id=4, as_of_date=datetime.now(timezone.utc)
    )

    assert X is None


def test_prediction_pipeline_uses_single_row_features(monkeypatch):
    import infrastructure.thresholds.engine as engine

    build_calls = []

    class FakeBuilder:
        def __init__(self, session):
            pass

        def build_prediction_features(
            self, asset_id, as_of_date, real_only=False, source_priority=False
        ):
            build_calls.append((asset_id, real_only, source_priority))
            return np.zeros((1, 49), dtype=np.float32), [f"f{i}" for i in range(49)]

        def build_training_table(self, **kwargs):
            raise AssertionError("serving path must not build a training table")

    class FakePredictor:
        def __init__(self):
            self.models = {}
            self.training_metrics = {}

        def _load_model(self, key):
            return True

        def predict(self, **kwargs):
            return SimpleNamespace(
                target_field="discharge",
                predicted_level_ft=None,
                predicted_inflow=None,
                predicted_outflow=12345.0,
                predicted_discharge=None,
                risk_score=10.0,
            )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [SimpleNamespace(id=1, canonical_name="Test Asset", asset_type="reservoir")]

    class FakeDB:
        def execute(self, *args, **kwargs):
            return FakeResult()

        def commit(self):
            pass

        def close(self):
            pass

    stored = []
    monkeypatch.setattr(
        "ml.features.feature_engineering.FloodFeatureBuilder", FakeBuilder
    )
    monkeypatch.setattr("ml.models.flood_predictor.FloodPredictor", FakePredictor)
    monkeypatch.setattr(
        engine, "store_prediction",
        lambda **kwargs: stored.append(kwargs),
    )
    monkeypatch.setattr(engine, "check_prediction_alerts", lambda db, asset_id: [])
    monkeypatch.setattr(
        "ml.targets.resolve_target_field", lambda db, asset_id: "outflow"
    )
    monkeypatch.setattr(
        __import__("pathlib").Path, "exists", lambda self: True
    )

    result = engine.run_prediction_pipeline(db=FakeDB())

    assert result == {"predictions_stored": 4, "alerts_generated": 0}
    assert build_calls == [(1, True, True)]
    assert len(stored) == 4
    assert {s["horizon_days"] for s in stored} == {3, 7, 14, 30}
