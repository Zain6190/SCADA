"""Persistence blend (rec #2 — Mangla): a single closed-form convex weight
blends the XGBoost output with the current observed value so the served
forecast can never do worse (holdout MSE) than either the raw model or
naive "hold today's value" persistence. alpha=1 = pure model (legacy path).
"""
import numpy as np
import pytest

from ml.models.flood_predictor import FloodPredictor

FEATURES = ["level", "inflow", "outflow", "discharge", "month"]


def _walk_table(n=400, horizon=7, seed=0):
    """Positive random walk target + noise features.

    'outflow' carries the current observed value (the persistence baseline);
    every other feature is noise, so the model can add little and alpha
    stays meaningful. y must be >= 0 so the log-transform path is exercised
    consistently with production.
    """
    rng = np.random.default_rng(seed)
    walk = 50000.0 + np.cumsum(rng.normal(0, 1000, size=n + horizon))
    current = walk[:n]
    y = walk[horizon : horizon + n]
    X = np.column_stack(
        [
            rng.normal(100, 1, n),
            rng.normal(200, 1, n),
            current,
            rng.normal(50, 1, n),
            rng.integers(1, 13, n).astype(float),
        ]
    )
    return X.astype(np.float32), y.astype(np.float32)


class TestPersistenceBlend:
    def test_blended_holdout_never_worse_than_either_side(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ml.models.flood_predictor.MODEL_DIR", str(tmp_path))
        X, y = _walk_table()
        p = FloodPredictor()
        m = p.train(
            asset_id=99, X=X, y=y, feature_names=FEATURES,
            horizon=7, target_field="outflow", persist=False,
        )
        assert 0.0 <= m["blend_alpha"] <= 1.0
        assert m["r2_persistence"] is not None
        # r2 = 1 - SS_res/SS_tot on the same holdout, and the blend
        # minimises SS_res over the convex hull => never below either side.
        assert m["r2"] >= max(m["r2_xgb_raw"], m["r2_persistence"]) - 1e-6

    def test_auto_target_skips_blend(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ml.models.flood_predictor.MODEL_DIR", str(tmp_path))
        X, y = _walk_table()
        p = FloodPredictor()
        m = p.train(
            asset_id=99, X=X, y=y, feature_names=FEATURES,
            horizon=7, target_field="auto", persist=False,
        )
        # 'auto' is not a feature -> no persistence column, legacy path
        assert m["blend_alpha"] == 1.0
        assert m["r2_persistence"] is None
        assert m["r2"] == m["r2_xgb_raw"]

    def test_predict_applies_trained_alpha(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ml.models.flood_predictor.MODEL_DIR", str(tmp_path))
        X, y = _walk_table()
        p = FloodPredictor()
        p.train(
            asset_id=99, X=X, y=y, feature_names=FEATURES,
            horizon=7, target_field="outflow", persist=False,
        )
        x_now = X[-1:].copy()
        current = float(x_now[0, FEATURES.index("outflow")])

        p.training_metrics["99_7"]["blend_alpha"] = 1.0
        raw = p.predict(99, "synthetic", x_now, FEATURES, horizon=7)
        p.training_metrics["99_7"]["blend_alpha"] = 0.25
        blended = p.predict(99, "synthetic", x_now, FEATURES, horizon=7)

        v_raw = raw.predicted_outflow
        v_blend = blended.predicted_outflow
        expected = 0.25 * v_raw + 0.75 * current
        assert v_blend == pytest.approx(expected, rel=1e-4)
        # residual band keeps its width, centre moves to the blend
        width_raw = raw.upper_bound - raw.lower_bound
        width_blend = blended.upper_bound - blended.lower_bound
        assert width_blend == pytest.approx(width_raw, rel=1e-6)
        assert blended.lower_bound == pytest.approx(v_blend - width_blend / 2, rel=1e-4)

    def test_missing_blend_key_defaults_to_pure_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ml.models.flood_predictor.MODEL_DIR", str(tmp_path))
        X, y = _walk_table()
        p = FloodPredictor()
        p.train(
            asset_id=99, X=X, y=y, feature_names=FEATURES,
            horizon=7, target_field="outflow", persist=False,
        )
        x_now = X[-1:].copy()
        p.training_metrics["99_7"].pop("blend_alpha", None)
        legacy = p.predict(99, "synthetic", x_now, FEATURES, horizon=7)
        p.training_metrics["99_7"]["blend_alpha"] = 1.0
        reference = p.predict(99, "synthetic", x_now, FEATURES, horizon=7)
        assert legacy.predicted_outflow == reference.predicted_outflow
