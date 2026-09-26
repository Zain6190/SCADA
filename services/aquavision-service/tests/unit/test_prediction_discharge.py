"""Unit tests for Steps 1-2: discharge targeting + discharge logic.

Covers:
- ml/targets.py canonical target map (reservoirs=outflow, headwaters=discharge)
- FloodPredictor / HighFlowPredictor output-field routing (never level-as-flow)
- prediction_v2._get_ml_predictions (outflow branch; level models excluded)
- prediction_v2._get_prediction_method provenance labels
- flow_baseline_cusecs target-aware ordering
- compute_accuracy outflow matching
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

from ml.targets import EXPLICIT_TARGETS, PHYSICS_ASSETS, flow_baseline_cusecs, resolve_target_field


# ─── ml/targets ──────────────────────────────────────────────────────────────

class TestResolveTargetField:
    def test_reservoirs_map_to_outflow(self):
        assert resolve_target_field(None, 1) == "outflow"
        assert resolve_target_field(None, 2) == "outflow"

    def test_headwaters_map_to_discharge(self):
        assert resolve_target_field(None, 9) == "discharge"
        assert resolve_target_field(None, 10) == "discharge"

    def test_never_returns_auto(self):
        # Explicit assets must not touch the session at all
        for aid in EXPLICIT_TARGETS:
            assert resolve_target_field(None, aid) != "auto"

    def test_barrage_fallback_uses_data(self):
        session = MagicMock()
        session.execute.return_value.mappings.return_value.one.return_value = {
            "total": 100, "n_inflow": 80, "n_discharge": 5,
        }
        assert resolve_target_field(session, 5) == "inflow"

    def test_discharge_fallback_when_no_inflow(self):
        session = MagicMock()
        session.execute.return_value.mappings.return_value.one.return_value = {
            "total": 100, "n_inflow": 2, "n_discharge": 90,
        }
        assert resolve_target_field(session, 99) == "discharge"


class TestFlowBaseline:
    def test_outflow_target_prefers_outflow(self):
        obs = {"outflow_cusecs": 5000, "inflow_cusecs": 9000, "discharge_cusecs": 100}
        assert flow_baseline_cusecs(obs, "outflow") == 5000

    def test_discharge_target_prefers_discharge(self):
        obs = {"outflow_cusecs": 5000, "inflow_cusecs": 9000, "discharge_cusecs": 100}
        assert flow_baseline_cusecs(obs, "discharge") == 100

    def test_inflow_target_prefers_inflow(self):
        obs = {"outflow_cusecs": 5000, "inflow_cusecs": 9000}
        assert flow_baseline_cusecs(obs, "inflow") == 9000

    def test_falls_through_when_target_missing(self):
        obs = {"inflow_cusecs": 9000, "outflow_cusecs": 5000}
        assert flow_baseline_cusecs(obs, "discharge") == 9000

    def test_zero_when_no_data(self):
        assert flow_baseline_cusecs({}, "outflow") == 0.0


# ─── FloodPredictor output-field routing ────────────────────────────────────

def _inject_model(predictor, key: str, target_field: str, n_features: int = 3):
    """Put a fake trained model in memory so predict() takes the in-memory path."""
    from sklearn.preprocessing import StandardScaler

    class _FakeModel:
        feature_importances_ = np.array([0.5, 0.3, 0.2][:n_features])

        def predict(self, X):
            return np.array([1234.0])

    class _FakeQuantile:
        feature_importances_ = np.array([0.5, 0.3, 0.2][:n_features])

        def predict(self, X):
            # Deterministic interval bounds, independent of X shape
            return np.array([1000.0])

    scaler = StandardScaler().fit(np.array([[0.0] * n_features, [1.0] * n_features]))
    predictor.models[key] = _FakeModel()
    predictor.scalers[key] = scaler
    predictor.feature_names[key] = [f"f{i}" for i in range(n_features)]
    predictor.training_mae[key] = 10.0
    if hasattr(predictor, "log_transform"):
        predictor.log_transform[key] = False
    # Keep predict() off disk — production interval files may exist in MODEL_DIR
    if hasattr(predictor, "quantile_models"):
        predictor.quantile_models[key] = {"q10": _FakeQuantile(), "q90": _FakeQuantile()}
    predictor.training_metrics[key] = {"target_field": target_field}


class TestFloodPredictorFieldRouting:
    def test_outflow_target_sets_predicted_outflow_only(self):
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        _inject_model(p, "1_7", "outflow")
        X = np.array([[1.0, 2.0, 3.0]])
        pred = p.predict(asset_id=1, asset_name="Tarbela", X=X,
                         feature_names=["f0", "f1", "f2"], horizon=7)
        assert pred is not None
        assert pred.predicted_outflow == 1234.0
        assert pred.predicted_level_ft is None
        assert pred.predicted_discharge is None
        assert pred.target_field == "outflow"

    def test_discharge_target_sets_predicted_discharge(self):
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        _inject_model(p, "9_7", "discharge")
        pred = p.predict(asset_id=9, asset_name="Kabul", X=np.array([[1.0, 2.0, 3.0]]),
                         feature_names=["f0", "f1", "f2"], horizon=7)
        assert pred.predicted_discharge == 1234.0
        assert pred.predicted_level_ft is None

    def test_level_target_never_sets_flow_fields(self):
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        _inject_model(p, "5_7", "level")
        pred = p.predict(asset_id=5, asset_name="Taunsa", X=np.array([[1.0, 2.0, 3.0]]),
                         feature_names=["f0", "f1", "f2"], horizon=7)
        assert pred.predicted_level_ft == 1234.0
        assert pred.predicted_discharge is None
        assert pred.predicted_outflow is None
        assert pred.predicted_inflow is None


class TestHighFlowPredictorFieldRouting:
    def test_outflow_target_sets_outflow_field(self):
        from ml.models.flood_predictor import HighFlowPredictor

        p = HighFlowPredictor()
        _inject_model(p, "2_7_hf", "outflow")
        pred = p.predict(asset_id=2, asset_name="Mangla", X=np.array([[1.0, 2.0, 3.0]]),
                         feature_names=["f0", "f1", "f2"], horizon=7)
        assert pred.predicted_outflow == 1234.0
        assert pred.predicted_level_ft is None
        assert pred.target_field == "outflow"


# ─── prediction_v2 discharge logic ───────────────────────────────────────────

class _FakePred:
    def __init__(self, **kw):
        self.predicted_level_ft = kw.get("level")
        self.predicted_inflow = kw.get("inflow")
        self.predicted_outflow = kw.get("outflow")
        self.predicted_discharge = kw.get("discharge")
        self.target_field = kw.get("target_field", "auto")
        self.lower_bound = kw.get("lower", 100.0)
        self.upper_bound = kw.get("upper", 200.0)
        self.ci_method = kw.get("ci_method", "r2_band")
        self.risk_score = kw.get("risk_score", 10.0)
        self.risk_level = kw.get("risk_level", "NORMAL")


@pytest.fixture
def v2_env(monkeypatch):
    """AquaVisionPredictionModel with FloodPredictor + FeatureBuilder stubbed."""
    from ml.models.prediction_v2 import AquaVisionPredictionModel

    fake_preds = {}

    class _FakePredictor:
        training_metrics = {}

        def predict(self, asset_id, asset_name, X, feature_names, horizon, **kw):
            return fake_preds.get(horizon)

    class _FakeBuilder:
        def __init__(self, session):
            pass

        def build_prediction_features(self, asset_id, as_of_date):
            return np.array([[1.0, 2.0, 3.0]]), ["f0", "f1", "f2"]

    import ml.models.flood_predictor as fp_mod
    import ml.features.feature_engineering as fe_mod

    monkeypatch.setattr(fp_mod, "FloodPredictor", _FakePredictor)
    monkeypatch.setattr(fe_mod, "FloodFeatureBuilder", _FakeBuilder)

    model = AquaVisionPredictionModel(session=None)
    return model, fake_preds


class TestGetMlPredictions:
    def test_discharge_model_contributes_flow(self, v2_env):
        model, fake = v2_env
        fake[3] = _FakePred(discharge=5000.0, target_field="discharge")
        out = model._get_ml_predictions(9)
        assert out[3]["predicted_cusecs"] == 5000.0
        assert out[3]["target_field"] == "discharge"

    def test_outflow_model_contributes_flow(self, v2_env):
        model, fake = v2_env
        fake[7] = _FakePred(outflow=32000.0, target_field="outflow")
        out = model._get_ml_predictions(2)
        assert out[7]["predicted_cusecs"] == 32000.0
        assert out[7]["target_field"] == "outflow"

    def test_level_only_model_excluded(self, v2_env):
        """Level (feet) must never be fed into the discharge pipeline."""
        model, fake = v2_env
        fake[14] = _FakePred(level=1450.0, target_field="level")
        out = model._get_ml_predictions(5)
        assert 14 not in out

    def test_records_target_for_method_label(self, v2_env):
        model, fake = v2_env
        fake[3] = _FakePred(outflow=100.0, target_field="outflow")
        model._get_ml_predictions(1)
        assert model._get_prediction_method(1) == "ml_xgboost_outflow"

    def test_physics_assets_labelled(self, v2_env):
        model, _ = v2_env
        assert model._get_prediction_method(5) == "physics_routing"
        assert model._get_prediction_method(3) in ("physics_routing",) or \
               model._get_prediction_method(3).startswith(("physics", "ml_"))


# ─── compute_accuracy outflow matching ──────────────────────────────────────

class _FakeResult:
    def __init__(self, rows=None, one=None, scalar=None):
        self._rows = rows or []
        self._one = one
        self._scalar = scalar

    class _Mappings:
        def __init__(self, rows, one):
            self._rows = rows
            self._one = one

        def all(self):
            return self._rows

        def first(self):
            return self._one

        def one(self):
            return self._one

    def mappings(self):
        return _FakeResult._Mappings(self._rows, self._one)

    def scalar(self):
        return self._scalar


class TestComputeAccuracyOutflow:
    def _run(self, monkeypatch, pred_row, actual_row):
        from scripts.compute_accuracy import compute_accuracy

        session = MagicMock()
        calls = {"n": 0}

        def _execute(query, params=None):
            sql = str(query)
            calls["n"] += 1
            if "water_asset_forecasts" in sql:
                return _FakeResult(rows=[pred_row])
            if "water_observations" in sql:
                return _FakeResult(one=actual_row)
            return _FakeResult()  # INSERT

        session.execute.side_effect = _execute
        return compute_accuracy(session, dry_run=False), calls

    def test_outflow_forecast_scores_against_outflow_actual(self, monkeypatch):
        now = datetime.now(timezone.utc)
        pred = {
            "id": 1, "asset_id": 1,
            "generated_at": now - timedelta(days=7),
            "target_time": now - timedelta(hours=1),
            "predicted_level_ft": None, "predicted_inflow": None,
            "predicted_outflow": 45000.0, "predicted_discharge": None,
            "model_version": "xgb_1_7d",
        }
        actual = {
            "water_level_ft": None, "inflow_cusecs": 50000.0,
            "outflow_cusecs": 45000.0, "discharge_cusecs": None,
            "observed_at": now, "data_origin": "REAL",
        }
        results, _ = self._run(monkeypatch, pred, actual)
        assert results["matched"] == 1
        assert results["skipped"] == 0

    def test_mismatched_fields_skip(self, monkeypatch):
        """Forecast has outflow but observation has no outflow → honest skip."""
        now = datetime.now(timezone.utc)
        pred = {
            "id": 2, "asset_id": 1,
            "generated_at": now - timedelta(days=7),
            "target_time": now - timedelta(hours=1),
            "predicted_level_ft": None, "predicted_inflow": None,
            "predicted_outflow": 45000.0, "predicted_discharge": None,
            "model_version": "xgb_1_7d",
        }
        actual = {
            "water_level_ft": 1500.0, "inflow_cusecs": None,
            "outflow_cusecs": None, "discharge_cusecs": None,
            "observed_at": now, "data_origin": "REAL",
        }
        results, _ = self._run(monkeypatch, pred, actual)
        assert results["matched"] == 0
        assert results["skipped"] == 1


# ─── seed target detection ──────────────────────────────────────────────────

class TestSeedTargetDetection:
    def test_reservoirs_seed_outflow(self):
        from scripts.seed_prediction_errors import _detect_target_field

        assert _detect_target_field(None, 1) == "outflow"
        assert _detect_target_field(None, 2) == "outflow"

    def test_headwaters_seed_discharge(self):
        from scripts.seed_prediction_errors import _detect_target_field

        assert _detect_target_field(None, 9) == "discharge"
        assert _detect_target_field(None, 10) == "discharge"


# ─── provenance constants ───────────────────────────────────────────────────

def test_physics_assets_constant():
    assert PHYSICS_ASSETS == frozenset({3, 4, 5, 6, 7, 8, 11})
