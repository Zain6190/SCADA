"""WAI feature contract: train, predict, risk, and anomaly scripts must feed
the model the exact same columns — a mismatch crashes serving with
feature_names ValueError (the bug that froze water_predictions_weekly)."""
import importlib.util
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[3] / "ml-pipeline"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ML_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_feature_contract_matches_across_scripts():
    if str(ML_ROOT) not in sys.path:
        sys.path.insert(0, str(ML_ROOT))
    from wai_features import FEATURE_COLS

    train = _load("wai_train_wai", "models/train_wai.py")
    predict = _load("wai_predict_weekly", "scripts/predict_weekly.py")
    risk = _load("wai_run_risk_alerts", "scripts/run_risk_alerts.py")
    anomaly = _load("wai_train_anomaly", "models/train_anomaly.py")

    for mod in (train, predict, risk, anomaly):
        assert mod.FEATURE_COLS == FEATURE_COLS, (
            f"{mod.__name__} FEATURE_COLS diverged from the shared contract"
        )
    assert FEATURE_COLS == [
        "rainfall_mm",
        "et_mm",
        "water_extent",
        "ndvi",
        "sm_rootzone",
        "sm_surface",
        "month_idx",
        "current_wai",
    ]
