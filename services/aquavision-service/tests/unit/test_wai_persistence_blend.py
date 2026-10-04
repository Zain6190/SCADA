"""Persistence blend for WAI (rec: persistence MAE beat raw XGBoost): a
closed-form convex weight blends the model with 'hold current_wai' so on the
test window the blend can't lose to either side, and serving applies the
same stamped alpha (1.0 = legacy pure-model path)."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ML_ROOT = Path(__file__).resolve().parents[3] / "ml-pipeline"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ML_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_blend_alpha_matches_brute_force_optimum():
    train = _load("wai_train_blend", "models/train_wai.py")
    rng = np.random.default_rng(0)
    actual = rng.normal(50, 10, 300)
    persist = actual + rng.normal(0, 8, 300)
    model = actual + rng.normal(0, 15, 300)
    alpha = train.blend_alpha(model, persist, actual)
    assert 0.0 <= alpha <= 1.0

    def mae(w: float) -> float:
        return float(np.mean(np.abs(persist + w * (model - persist) - actual)))

    grid = np.linspace(0.0, 1.0, 101)
    assert mae(alpha) <= min(mae(w) for w in grid) + 1e-12
    assert mae(alpha) <= min(mae(0.0), mae(1.0)) + 1e-12


def test_blend_alpha_edges():
    train = _load("wai_train_blend2", "models/train_wai.py")
    actual = np.array([10.0, 20.0, 30.0])
    perfect = actual.copy()
    assert train.blend_alpha(perfect, actual + 5.0, actual) == pytest.approx(1.0)
    same = actual + 5.0
    assert train.blend_alpha(same, same, actual) == 1.0
    worse_than_persistence = actual + 30.0
    alpha = train.blend_alpha(worse_than_persistence, actual, actual)
    assert alpha == pytest.approx(0.0)


def test_apply_blend_endpoints_and_convexity():
    predict = _load("wai_predict_blend", "scripts/predict_weekly.py")
    current = np.array([40.0, 60.0])
    delta = np.array([10.0, -20.0])
    assert predict.apply_blend(current, delta, 1.0).tolist() == [50.0, 40.0]
    assert predict.apply_blend(current, delta, 0.0).tolist() == [40.0, 60.0]
    half = predict.apply_blend(current, delta, 0.5)
    assert half.tolist() == [45.0, 50.0]


def test_load_blend_alpha_defaults_and_reads_stamped_value(tmp_path):
    predict = _load("wai_predict_blend2", "scripts/predict_weekly.py")
    predict.ARTIFACT_DIR = tmp_path
    assert predict.load_blend_alpha() == 1.0

    (tmp_path / "metrics.json").write_text(
        json.dumps({"model_version": "x", "blend": {"alpha": 0.55}}),
        encoding="utf-8",
    )
    assert predict.load_blend_alpha() == pytest.approx(0.55)

    (tmp_path / "metrics.json").write_text(
        json.dumps({"model_version": "x"}), encoding="utf-8"
    )
    assert predict.load_blend_alpha() == 1.0

    (tmp_path / "metrics.json").write_text("{not json", encoding="utf-8")
    assert predict.load_blend_alpha() == 1.0
