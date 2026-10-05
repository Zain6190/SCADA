"""Alert confidence must come from the prediction band (predict_weekly's
Gaussian-over-band formula), not the old boundary-margin heuristic - two
different confidence numbers for the same forecast confuse operators."""
import importlib.util
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[3] / "ml-pipeline"


def _load():
    spec = importlib.util.spec_from_file_location(
        "wai_run_risk_alerts_conf", ML_ROOT / "scripts" / "run_risk_alerts.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mod_with_thresholds():
    mod = _load()
    mod.th = {
        "wai_critical_min": 25.0,
        "wai_severe_min": 40.0,
        "wai_stressed_min": 55.0,
        "rainfall_deficit_pct": -30.0,
        "et_anomaly_high": 50.0,
    }
    return mod


def test_alert_confidence_is_the_band_confidence():
    mod = _mod_with_thresholds()
    rows = [
        dict(
            region_id=1, wai=30.0, rainfall_anomaly=-10.0, et_anomaly=10.0,
            anomaly_ratio=0.5, band_confidence=0.87,
        ),
        dict(
            region_id=2, wai=60.0, rainfall_anomaly=-40.0, et_anomaly=10.0,
            anomaly_ratio=0.5, band_confidence=0.62,
        ),
    ]
    alerts = mod.build_alert_rows(rows)
    by_region = {a["region_id"]: a for a in alerts}
    assert by_region[1]["alert_type"] == "WAI_SEVERE"
    assert by_region[1]["confidence"] == 0.87
    assert by_region[2]["alert_type"] == "RAINFALL_DEFICIT"
    assert by_region[2]["confidence"] == 0.62


def test_alert_confidence_is_not_recomputed_from_thresholds():
    mod = _mod_with_thresholds()
    rows = [
        dict(
            region_id=1, wai=30.0, rainfall_anomaly=-10.0, et_anomaly=10.0,
            anomaly_ratio=0.9, band_confidence=0.5,
        ),
    ]
    alerts = mod.build_alert_rows(rows)
    assert alerts[0]["confidence"] == 0.5
    assert not hasattr(mod, "_confidence")
