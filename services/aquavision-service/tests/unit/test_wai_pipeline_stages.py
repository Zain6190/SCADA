"""WAI pipeline stage contract: validate_preds must stay wired into STAGES.

It was documented as an optional stage in run_pipeline.py's docstring but
missing from the STAGES list, so closed-week forecasts were never scored
against actuals (silent loss of the feedback loop). These guards make that
regression impossible without a failing test.
"""
import importlib.util
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[3] / "ml-pipeline"


def _load_run_pipeline():
    spec = importlib.util.spec_from_file_location(
        "wai_run_pipeline", ML_ROOT / "scripts" / "run_pipeline.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_validate_preds_is_a_pipeline_stage():
    mod = _load_run_pipeline()
    assert "validate_preds" in mod.STAGES, (
        "validate_preds fell out of STAGES - closed forecasts will never "
        "be scored against actuals"
    )
    # must run after predictions exist
    assert mod.STAGES.index("validate_preds") > mod.STAGES.index("predict_weekly")


def test_validate_preds_module_override_points_at_real_script():
    mod = _load_run_pipeline()
    override = mod.MODULE_OVERRIDES.get("validate_preds")
    assert override == "scripts.validate_predictions", (
        f"validate_preds module override is {override!r}; the script lives "
        "at scripts/validate_predictions.py (default would look for "
        "scripts/validate_preds.py and fail)"
    )
    assert (ML_ROOT / "scripts" / "validate_predictions.py").is_file()


def test_validate_preds_output_parsed_into_stage_counts():
    mod = _load_run_pipeline()
    out = "[validate_predictions] Validated 7 predictions | MAE=4.11 RMSE=5.02"
    summary = mod._parse_stage("validate_preds", out, 0)
    assert summary["records_written"] == 7
    assert summary["status"] == "SUCCESS"

    noop = "[validate_predictions] No closed forecast periods to validate yet"
    summary = mod._parse_stage("validate_preds", noop, 0)
    assert summary["records_written"] == 0
    assert summary["status"] == "SUCCESS"
