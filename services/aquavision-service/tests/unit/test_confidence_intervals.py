"""Unit tests for Step 4: calibrated confidence intervals.

Covers:
- FloodPredictor quantile q10/q90 interval training (>=100 samples, persist)
- predict() CI chain: quantile -> residual_p90 -> r2_band with ci_method labels
- lazy interval loading from disk; graceful fallback when file missing
- HighFlowPredictor residual-band intervals + ci_method
- prediction_v2 ci_method passthrough (_get_ml_predictions, _compute_discharge_prediction)
- API schema exposes ci_method
"""
from __future__ import annotations

import os

import numpy as np
import pytest


def _synth(n: int, seed: int = 42):
    """Synthetic positive flow series with a learnable signal + noise."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 4))
    y = 5000 + 800 * X[:, 0] - 400 * X[:, 1] + rng.normal(0, 600, size=n)
    y = np.maximum(y, 50.0)
    return X, y, [f"f{i}" for i in range(4)]


@pytest.fixture
def model_dir(tmp_path, monkeypatch):
    """Redirect model persistence to a temp dir — never touch production files."""
    import ml.models.flood_predictor as fp

    monkeypatch.setattr(fp, "MODEL_DIR", str(tmp_path))
    return tmp_path


# ─── quantile interval training ─────────────────────────────────────────────

class TestQuantileIntervalTraining:
    def test_large_data_trains_quantiles_and_reports_coverage(self, model_dir):
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        X, y, feats = _synth(150)
        metrics = p.train(
            asset_id=1, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=True,
        )

        assert metrics["ci_method"] == "quantile_q10_q90"
        assert metrics["ci_coverage_80"] is not None
        assert 0.0 <= metrics["ci_coverage_80"] <= 1.0
        assert 0.0 <= metrics["ci_coverage_90"] <= 1.0
        assert (model_dir / "1_7.joblib").exists()
        assert (model_dir / "1_7_interval.joblib").exists()

    def test_small_data_skips_quantiles(self, model_dir):
        """Barrages train on ~30-60 rows — no quantile models, honest label."""
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        X, y, feats = _synth(60)
        metrics = p.train(
            asset_id=5, X=X, y=y, feature_names=feats,
            horizon=7, target_field="inflow", persist=True,
        )

        assert metrics["ci_method"] == "residual_p90"
        assert metrics["ci_coverage_80"] is None
        assert not (model_dir / "5_7_interval.joblib").exists()
        assert (model_dir / "5_7.joblib").exists()

    def test_persist_false_writes_no_files(self, model_dir):
        """Holdout backtests/seed scripts must not write model files."""
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        X, y, feats = _synth(150)
        metrics = p.train(
            asset_id=1, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=False,
        )

        assert metrics["ci_method"] == "residual_p90"
        assert list(model_dir.glob("*.joblib")) == []


# ─── conformal calibration (rec #1) ─────────────────────────────────────────

class TestConformalCalibration:
    def test_calibrated_coverage_reaches_target(self, model_dir):
        """Shipped band must cover >= ~0.80 on the holdout it was calibrated on."""
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        X, y, feats = _synth(150)
        metrics = p.train(
            asset_id=1, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=True,
        )

        assert metrics["ci_coverage_80"] is not None
        assert metrics["ci_coverage_80"] >= 0.78
        # raw band never beats the calibrated one (inflation >= 0)
        assert metrics["ci_coverage_80_raw"] <= metrics["ci_coverage_80"]
        assert metrics["ci_inflation"] is not None
        assert metrics["ci_inflation"] >= 0

    def test_interval_file_stores_inflation(self, model_dir):
        import joblib

        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        X, y, feats = _synth(150)
        p.train(
            asset_id=9, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=True,
        )

        data = joblib.load(model_dir / "9_7_interval.joblib")
        assert data["conformal_inflation"] >= 0
        assert data["coverage_80_calibrated"] >= 0.78
        assert data["coverage_80_holdout"] <= data["coverage_80_calibrated"] + 1e-9

    def test_predict_applies_inflation(self, model_dir):
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        X, y, feats = _synth(150)
        p.train(
            asset_id=10, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=True,
        )
        pred = p.predict(
            asset_id=10, asset_name="Indus", X=X[:1],
            feature_names=feats, horizon=7,
        )

        import joblib

        data = joblib.load(model_dir / "10_7_interval.joblib")
        s = data["conformal_inflation"]
        x_scaled = p.scalers["10_7"].transform(X[:1])
        q10 = float(data["q10"].predict(x_scaled)[0])
        q90 = float(data["q90"].predict(x_scaled)[0])
        if p.log_transform.get("10_7"):
            import numpy as np

            q10 = float(np.expm1(q10))
            q90 = float(np.expm1(q90))
        raw_lo, raw_hi = min(q10, q90), max(q10, q90)

        assert abs(pred.upper_bound - (raw_hi + s)) < 0.01
        assert pred.lower_bound <= raw_lo + 0.01

    def test_legacy_interval_file_without_conformal(self, model_dir):
        """Pre-conformal interval files load with inflation=0, no crash."""
        import joblib

        from ml.models.flood_predictor import FloodPredictor

        p1 = FloodPredictor()
        X, y, feats = _synth(150)
        p1.train(
            asset_id=1, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=True,
        )
        path = model_dir / "1_7_interval.joblib"
        data = joblib.load(path)
        data.pop("conformal_inflation", None)
        data.pop("coverage_80_calibrated", None)
        joblib.dump(data, path)

        p2 = FloodPredictor()
        pred = p2.predict(
            asset_id=1, asset_name="Tarbela", X=X[:1],
            feature_names=feats, horizon=7,
        )
        assert pred is not None
        assert pred.ci_method == "quantile_q10_q90"
        assert 0 <= pred.lower_bound <= pred.upper_bound


# ─── predict() CI chain ─────────────────────────────────────────────────────

class TestPredictCIChain:
    def test_quantile_bounds_used_when_trained(self, model_dir):
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        X, y, feats = _synth(150)
        p.train(
            asset_id=9, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=True,
        )
        pred = p.predict(
            asset_id=9, asset_name="Kabul", X=X[:1],
            feature_names=feats, horizon=7,
        )

        assert pred is not None
        assert pred.ci_method == "quantile_q10_q90"
        assert 0 <= pred.lower_bound <= pred.upper_bound
        assert pred.upper_bound > 0

    def test_residual_band_when_no_quantiles(self, model_dir):
        from ml.models.flood_predictor import FloodPredictor

        p = FloodPredictor()
        X, y, feats = _synth(60)
        p.train(
            asset_id=3, X=X, y=y, feature_names=feats,
            horizon=7, target_field="inflow", persist=True,
        )
        pred = p.predict(
            asset_id=3, asset_name="Jhelum", X=X[:1],
            feature_names=feats, horizon=7,
        )

        assert pred is not None
        assert pred.ci_method == "residual_p90"
        assert 0 <= pred.lower_bound <= pred.upper_bound

    def test_disk_load_uses_quantile_interval(self, model_dir):
        """Fresh predictor instance must lazily load the interval file."""
        from ml.models.flood_predictor import FloodPredictor

        p1 = FloodPredictor()
        X, y, feats = _synth(150)
        p1.train(
            asset_id=10, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=True,
        )

        p2 = FloodPredictor()  # empty memory — everything from disk
        pred = p2.predict(
            asset_id=10, asset_name="Indus", X=X[:1],
            feature_names=feats, horizon=7,
        )

        assert pred is not None
        assert pred.ci_method == "quantile_q10_q90"

    def test_missing_interval_file_falls_back_to_residual(self, model_dir):
        from ml.models.flood_predictor import FloodPredictor

        p1 = FloodPredictor()
        X, y, feats = _synth(150)
        p1.train(
            asset_id=1, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge", persist=True,
        )
        os.remove(model_dir / "1_7_interval.joblib")

        p2 = FloodPredictor()
        pred = p2.predict(
            asset_id=1, asset_name="Tarbela", X=X[:1],
            feature_names=feats, horizon=7,
        )

        assert pred is not None
        assert pred.ci_method == "residual_p90"
        assert 0 <= pred.lower_bound <= pred.upper_bound

    def test_r2_band_last_resort_when_no_residual(self, model_dir):
        """No quantiles, no residual record → legacy heuristic, honest label."""
        from ml.models.flood_predictor import FloodPredictor
        from sklearn.preprocessing import StandardScaler

        class _FakeModel:
            feature_importances_ = np.array([0.5, 0.3, 0.2])

            def predict(self, X):
                return np.array([1234.0])

        p = FloodPredictor()
        scaler = StandardScaler().fit(np.array([[0.0] * 3, [1.0] * 3]))
        p.models["1_7"] = _FakeModel()
        p.scalers["1_7"] = scaler
        p.feature_names["1_7"] = ["f0", "f1", "f2"]
        p.training_metrics["1_7"] = {"target_field": "outflow", "r2": 0.75}
        # residual_p90 / training_mae intentionally empty

        pred = p.predict(
            asset_id=1, asset_name="Tarbela", X=np.array([[1.0, 2.0, 3.0]]),
            feature_names=["f0", "f1", "f2"], horizon=7,
        )

        assert pred is not None
        assert pred.ci_method == "r2_band"
        assert 0 <= pred.lower_bound <= pred.upper_bound


# ─── HighFlowPredictor ──────────────────────────────────────────────────────

class TestHighFlowCI:
    def test_highflow_uses_residual_band(self, model_dir):
        from ml.models.flood_predictor import HighFlowPredictor

        p = HighFlowPredictor()
        X, y, feats = _synth(200, seed=7)
        metrics = p.train(
            asset_id=9, X=X, y=y, feature_names=feats,
            horizon=7, target_field="discharge",
        )
        assert metrics["residual_p90"] > 0

        pred = p.predict(
            asset_id=9, asset_name="Kabul", X=X[:1],
            feature_names=feats, horizon=7,
        )
        assert pred is not None
        assert pred.ci_method == "residual_p90"
        assert 0 <= pred.lower_bound <= pred.upper_bound


# ─── prediction_v2 passthrough ──────────────────────────────────────────────

class TestPredictionV2CiPassthrough:
    def test_compute_discharge_prediction_passthrough(self):
        from ml.models.prediction_v2 import _compute_discharge_prediction

        d = _compute_discharge_prediction(
            1000, 900, 1100, ci_method="quantile_q10_q90",
        )
        assert d.ci_method == "quantile_q10_q90"
        assert d.confidence_lower_cusecs == 900
        assert d.confidence_upper_cusecs == 1100

    def test_compute_discharge_prediction_default_none(self):
        from ml.models.prediction_v2 import _compute_discharge_prediction

        d = _compute_discharge_prediction(1000, 900, 1100)
        assert d.ci_method is None

    def test_get_ml_predictions_passes_ci_method(self, monkeypatch):
        from ml.models.prediction_v2 import AquaVisionPredictionModel

        class _FakePred:
            def __init__(self):
                self.predicted_level_ft = None
                self.predicted_inflow = None
                self.predicted_outflow = 32000.0
                self.predicted_discharge = None
                self.target_field = "outflow"
                self.lower_bound = 28000.0
                self.upper_bound = 36000.0
                self.ci_method = "quantile_q10_q90"
                self.risk_score = 10.0
                self.risk_level = "NORMAL"

        class _FakePredictor:
            training_metrics = {}

            def __init__(self):
                pass

            def predict(self, asset_id, asset_name, X, feature_names, horizon, **kw):
                return _FakePred() if horizon == 7 else None

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
        out = model._get_ml_predictions(1)

        assert out[7]["ci_method"] == "quantile_q10_q90"
        assert out[7]["lower_bound"] == 28000.0
        assert out[7]["upper_bound"] == 36000.0


# ─── API schema ─────────────────────────────────────────────────────────────

class TestApiResponseSchema:
    def test_discharge_response_exposes_ci_method(self):
        from ml.prediction_api_v2 import DischargeResponse

        r = DischargeResponse(
            value_m3s=100.0, confidence_lower_m3s=90.0,
            confidence_upper_m3s=110.0, value_cusecs=3531.0,
            confidence_lower_cusecs=3178.0, confidence_upper_cusecs=3884.0,
            ci_method="quantile_q10_q90",
        )
        assert r.ci_method == "quantile_q10_q90"
        assert r.model_dump()["ci_method"] == "quantile_q10_q90"

    def test_discharge_response_ci_method_defaults_none(self):
        from ml.prediction_api_v2 import DischargeResponse

        r = DischargeResponse(
            value_m3s=100.0, confidence_lower_m3s=90.0,
            confidence_upper_m3s=110.0, value_cusecs=3531.0,
            confidence_lower_cusecs=3178.0, confidence_upper_cusecs=3884.0,
        )
        assert r.ci_method is None

    def test_v1_prediction_response_exposes_ci_method(self):
        from ml.prediction_api import PredictionResponse

        r = PredictionResponse(
            asset_id=1, asset_name="Tarbela", prediction_date="2026-09-25",
            horizon_days=7, predicted_level_ft=None,
            lower_bound=1000.0, upper_bound=2000.0,
            risk_score=10.0, risk_level="NORMAL",
            exceeds_warning=False, exceeds_danger=False,
            model_version="xgb-flood-v1.2", model_status="EXPERIMENTAL",
            feature_importance={}, target_field="discharge",
            ci_method="residual_p90",
        )
        assert r.ci_method == "residual_p90"
