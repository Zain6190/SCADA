"""Interval + honest confidence: quantile/conformal training, serving band
math, and the documented fallbacks (mirrors the flood-side CI tests)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ML_ROOT = Path(__file__).resolve().parents[3] / "ml-pipeline"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ML_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods():
    if str(ML_ROOT) not in sys.path:
        sys.path.insert(0, str(ML_ROOT))
    from wai_features import FEATURE_COLS

    train = _load("wai_train_interval", "models/train_wai.py")
    predict = _load("wai_predict_interval", "scripts/predict_weekly.py")
    return train, predict, FEATURE_COLS


def _frame(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    current = rng.uniform(20.0, 80.0, n)
    frame = pd.DataFrame(
        {
            "rainfall_mm": rng.normal(0.0, 1.0, n),
            "et_mm": rng.normal(0.0, 1.0, n),
            "water_extent": rng.normal(0.0, 1.0, n),
            "ndvi": rng.normal(0.0, 1.0, n),
            "sm_rootzone": rng.normal(0.0, 1.0, n),
            "sm_surface": rng.normal(0.0, 1.0, n),
            "month_idx": rng.integers(1, 13, n),
            "current_wai": current,
        }
    )
    delta = (
        0.4 * (55.0 - current)
        + 2.0 * frame["rainfall_mm"].to_numpy()
        + rng.normal(0.0, 3.0, n)
    )
    frame["wai_score"] = np.clip(current + delta, 0.0, 100.0)
    return frame


@pytest.fixture(scope="module")
def trained(mods):
    import xgboost as xgb

    train, predict, feature_cols = mods
    tr, va, te = _frame(240, 1), _frame(60, 2), _frame(60, 3)
    reg = xgb.XGBRegressor(n_estimators=80, max_depth=4, random_state=42)
    reg.fit(tr[feature_cols], tr["wai_score"] - tr["current_wai"])
    return train, predict, feature_cols, tr, va, te, reg


def test_interval_training_writes_artifact_with_coverage(trained, tmp_path):
    train, _, feature_cols, tr, va, te, reg = trained
    out = tmp_path / "wai_interval_test.joblib"
    payload = train.train_interval_models(tr, va, te, reg, out_path=out)

    assert out.exists()
    assert payload["method"] == "quantile_q10_q90_conformal"
    assert payload["inflation"] >= 0.0
    assert payload["residual_p80"] > 0.0
    assert 0.6 <= payload["coverage_calibrated"] <= 0.95, "conformal must reach ~0.80"
    assert payload["coverage_raw"] is not None
    assert payload["coverage_test"] is not None
    assert payload["feature_names"] == list(feature_cols)
    assert payload["calib_rows"] == len(va)


def test_quantile_failure_falls_back_to_residual_band(trained, tmp_path):
    train, _, feature_cols, _, va, te, reg = trained
    empty = va.iloc[:0].copy()
    payload = train.train_interval_models(
        empty, va.iloc[:10], te, reg, out_path=tmp_path / "fallback.joblib"
    )
    assert payload["method"] == "residual_p80"
    assert payload["q10"] is None and payload["q90"] is None
    assert payload["coverage_raw"] is None
    assert 0.5 <= payload["coverage_calibrated"] <= 1.0


def test_band_contains_prediction_and_confidence_in_range(trained, tmp_path):
    train, predict, feature_cols, tr, va, te, reg = trained
    payload = train.train_interval_models(
        tr, va, te, reg, out_path=tmp_path / "wai_interval_test.joblib"
    )
    current = te["current_wai"].to_numpy()
    delta = reg.predict(te[feature_cols])
    level = np.clip(current + delta, 0.0, 100.0)

    lo, hi, conf = predict.band_and_confidence(
        te, current, delta, level, payload
    )
    assert np.all(lo <= level + 1e-9)
    assert np.all(hi >= level - 1e-9)
    assert np.all(lo >= 0.0) and np.all(hi <= 100.0)
    assert np.all(conf >= 0.05) and np.all(conf <= 0.99)


def test_confidence_narrows_with_wider_band(mods):
    _, predict, feature_cols = mods
    n = 5
    X = pd.DataFrame({c: np.zeros(n) for c in feature_cols})
    current = np.full(n, 50.0)
    delta = np.zeros(n)
    level = np.full(n, 50.0)
    narrow = {"q10": None, "q90": None, "residual_p80": 4.0, "inflation": 0.0}
    wide = {"q10": None, "q90": None, "residual_p80": 40.0, "inflation": 0.0}

    _, _, conf_narrow = predict.band_and_confidence(X, current, delta, level, narrow)
    _, _, conf_wide = predict.band_and_confidence(X, current, delta, level, wide)
    assert np.all(conf_narrow > conf_wide), "wider band must mean lower confidence"


def test_missing_interval_gives_uninformative_confidence(mods):
    _, predict, feature_cols = mods
    n = 4
    X = pd.DataFrame({c: np.zeros(n) for c in feature_cols})
    lo, hi, conf = predict.band_and_confidence(
        X, np.full(n, 50.0), np.zeros(n), np.full(n, 50.0), None
    )
    assert all(v is None for v in lo) and all(v is None for v in hi)
    assert np.allclose(conf, 0.5)
