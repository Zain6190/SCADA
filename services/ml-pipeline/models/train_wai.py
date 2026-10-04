"""
models/train_wai.py
AquaVision - Train WAI regressor + severity classifier (XGBoost).

- Reads Data/features/dataset.csv (from build_dataset.py), whose rows are
  (features at t) -> (WAI at t+1) with current_wai = observed WAI at t.
- CHRONOLOGICAL split (first 80% of time = train, last 20% = test).
- Early stopping runs on a validation tail carved from TRAIN so the test
  window stays untouched for the final report.
- The regressor learns the month-over-month DELTA (wai(t+1) - current_wai);
  reported metrics are on the reconstructed LEVEL (current_wai + delta).
  Predicting the bounded delta instead of the level keeps tree models from
  collapsing to the training mean when the test period leaves the training
  range (record-wet months previously capped all predictions below 54).
- metrics.json also records the persistence baseline (level = current_wai)
  on the same test rows for an honest comparison.
- Writes metrics.json + artifacts/*.joblib

Usage:
    python -m models.train_wai   (run from services/ml-pipeline)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.preprocessing import LabelEncoder

ML_ROOT = Path(__file__).resolve().parent.parent
DATASET_CSV = ML_ROOT / "Data" / "features" / "dataset.csv"
ARTIFACT_DIR = ML_ROOT / "models" / "artifacts"

sys.path.insert(0, str(ML_ROOT))
from wai_features import FEATURE_COLS, SEVERITY_COL, TARGET_COL  # noqa: E402

SEVERITY_ORDER = ["Normal", "Moderate", "Stressed", "Severe", "Critical"]
MODEL_VERSION = "xgb-v1.0"

TEST_FRACTION = 0.2


def train_interval_models(tr, va, te, reg, out_path=None) -> dict:
    """q10/q90 delta quantile models + split-conformal calibration.

    Mirrors the flood-side CI chain (flood_predictor._train_interval_models):
    quantile regressors fit ONLY on `tr` (fixed rounds, no early stopping so
    `va` stays unseen), an additive inflation in delta units calibrated on
    `va` to an 80% coverage target, and coverage on the untouched test
    window recorded for an honest report — it can fall below target under
    regime shift (standard conformal caveat, documented not hidden).

    A residual-P80 fallback (80th percentile of |point-model residuals| on
    `va`; slightly optimistic because early stopping saw `va`) keeps serving
    possible if quantile training fails. The payload is dumped to
    wai_interval_<version>.joblib (or `out_path`) for predict_weekly.
    """
    from datetime import datetime, timezone

    d_va = (va[TARGET_COL] - va["current_wai"]).to_numpy()
    delta_hat_va = reg.predict(va[FEATURE_COLS])
    residual_p80 = float(np.percentile(np.abs(d_va - delta_hat_va), 80))

    fitted: dict = {}
    try:
        for alpha, name in ((0.10, "q10"), (0.90, "q90")):
            qm = xgb.XGBRegressor(
                objective="reg:quantileerror",
                quantile_alpha=alpha,
                n_estimators=300,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.5,
                reg_lambda=2.0,
                min_child_weight=5,
                random_state=42,
            )
            qm.fit(tr[FEATURE_COLS], tr[TARGET_COL] - tr["current_wai"])
            fitted[name] = qm
    except Exception as exc:
        print(
            f"[train_wai] quantile interval training failed ({exc}); "
            f"falling back to residual band"
        )
        fitted = {}

    d_te = (te[TARGET_COL] - te["current_wai"]).to_numpy()
    delta_hat_te = reg.predict(te[FEATURE_COLS])
    if fitted:
        q10_va = fitted["q10"].predict(va[FEATURE_COLS])
        q90_va = fitted["q90"].predict(va[FEATURE_COLS])
        scores = np.maximum(q10_va - d_va, d_va - q90_va)
        inflation = max(0.0, float(np.percentile(scores, 80)))
        coverage_raw = float(np.mean((d_va >= q10_va) & (d_va <= q90_va)))
        coverage_cal = float(
            np.mean((d_va >= q10_va - inflation) & (d_va <= q90_va + inflation))
        )
        q10_te = fitted["q10"].predict(te[FEATURE_COLS])
        q90_te = fitted["q90"].predict(te[FEATURE_COLS])
        coverage_test = float(
            np.mean((d_te >= q10_te - inflation) & (d_te <= q90_te + inflation))
        )
        method = "quantile_q10_q90_conformal"
    else:
        fitted = {"q10": None, "q90": None}
        inflation = 0.0
        coverage_raw = None
        coverage_cal = float(np.mean(np.abs(d_va - delta_hat_va) <= residual_p80))
        coverage_test = float(np.mean(np.abs(d_te - delta_hat_te) <= residual_p80))
        method = "residual_p80"

    payload = {
        "method": method,
        "q10": fitted.get("q10"),
        "q90": fitted.get("q90"),
        "inflation": inflation,
        "residual_p80": residual_p80,
        "coverage_raw": coverage_raw,
        "coverage_calibrated": coverage_cal,
        "coverage_test": coverage_test,
        "calib_rows": int(len(va)),
        "calib_months": (
            [str(va["month"].min()), str(va["month"].max())]
            if "month" in va.columns else None
        ),
        "feature_names": list(FEATURE_COLS),
        "model_version": MODEL_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    path = Path(out_path) if out_path else (
        ARTIFACT_DIR / f"wai_interval_{MODEL_VERSION}.joblib"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, path)
    print(
        f"[train_wai] interval [{method}] coverage 80%: "
        f"raw={coverage_raw if coverage_raw is None else round(coverage_raw, 3)} "
        f"calibrated(va)={round(coverage_cal, 3)} test={round(coverage_test, 3)} "
        f"inflation={inflation:.2f} residual_p80={residual_p80:.2f} -> {path.name}"
    )
    return payload


def main() -> None:
    df = pd.read_csv(DATASET_CSV)
    # Impute missing features (JRC ends ~2021 -> water_extent mostly NaN; the
    # current month's rainfall may be pending). Median imputation keeps rows usable.
    for col in FEATURE_COLS:
        df[col] = df[col].fillna(df[col].median())
    df = df.dropna(subset=[TARGET_COL, SEVERITY_COL])

    # PURELY chronological split: sort by month only, then take last 20% as test.
    df = df.sort_values("month").reset_index(drop=True)
    print(f"[train_wai] {len(df)} rows loaded")
    cutoff = int(len(df) * (1 - TEST_FRACTION))
    train, test = df.iloc[:cutoff].copy(), df.iloc[cutoff:].copy()
    print(
        f"[train_wai] chrono split -> train={len(train)} test={len(test)} "
        f"(train months {train['month'].min()}..{train['month'].max()}; "
        f"test months {test['month'].min()}..{test['month'].max()})"
    )
    # Validation tail from TRAIN for early stopping: the test window is only
    # ever read for the final metrics.
    vcut = int(len(train) * 0.85)
    tr, va = train.iloc[:vcut].copy(), train.iloc[vcut:].copy()
    print(
        f"[train_wai] early-stop validation = last 15% of train "
        f"({len(va)} rows, months {va['month'].min()}..{va['month'].max()})"
    )

    y_tr, y_te = train[TARGET_COL], test[TARGET_COL]

    # ---- Regressor: month-over-month WAI DELTA; metrics reported on LEVEL ----
    reg = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        early_stopping_rounds=20,
        random_state=42,
    )
    reg.fit(
        tr[FEATURE_COLS],
        tr[TARGET_COL] - tr["current_wai"],
        eval_set=[(va[FEATURE_COLS], va[TARGET_COL] - va["current_wai"])],
        verbose=False,
    )
    pred_reg = test["current_wai"].to_numpy() + reg.predict(test[FEATURE_COLS])

    rmse = float(np.sqrt(mean_squared_error(y_te, pred_reg)))
    mae = float(mean_absolute_error(y_te, pred_reg))
    r2 = float(r2_score(y_te, pred_reg))

    # Persistence baseline on the identical test rows (level = current_wai).
    pers = test["current_wai"].to_numpy()
    pers_rmse = float(np.sqrt(mean_squared_error(y_te, pers)))
    pers_mae = float(mean_absolute_error(y_te, pers))
    pers_r2 = float(r2_score(y_te, pers))

    # ---- Classifier: severity ----
    # Encoder fit on TRAIN only so classes are contiguous for XGBoost.
    le = LabelEncoder()
    y_sev_tr = le.fit_transform(train[SEVERITY_COL].astype(str))

    # Evaluate only on test rows whose label the model has seen.
    known = test[SEVERITY_COL].isin(le.classes_)
    test_clf = test[known].copy()
    y_sev_te = le.transform(test_clf[SEVERITY_COL].astype(str))
    X_te_clf = test_clf[FEATURE_COLS]
    print(
        f"[train_wai] classifier evaluated on {len(test_clf)}/{len(test)} "
        f"test rows (labels known to train)"
    )

    clf = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        num_class=len(le.classes_),
        random_state=42,
    )
    clf.fit(train[FEATURE_COLS], y_sev_tr)
    pred_clf = clf.predict(X_te_clf)
    pred_clf_names = le.inverse_transform(pred_clf.astype(int))
    acc = float(accuracy_score(test_clf[SEVERITY_COL], pred_clf_names))

    cm = confusion_matrix(
        test_clf[SEVERITY_COL],
        pred_clf_names,
        labels=le.classes_.tolist(),
    )
    report = classification_report(
        test_clf[SEVERITY_COL], pred_clf_names, zero_division=0, output_dict=True
    )

    metrics = {
        "model_version": MODEL_VERSION,
        "target": "wai_delta_vs_current_wai (level = current_wai + delta)",
        "n_train": len(train),
        "n_test": len(test),
        "regressor": {"rmse": round(rmse, 4), "mae": round(mae, 4), "r2": round(r2, 4)},
        "persistence_baseline": {
            "rmse": round(pers_rmse, 4),
            "mae": round(pers_mae, 4),
            "r2": round(pers_r2, 4),
        },
        "classifier": {
            "accuracy": round(acc, 4),
            "classification_report": report,
        },
        "confusion_matrix": cm.tolist(),
        "test_month_range": [test["month"].min(), test["month"].max()],
    }

    interval = train_interval_models(tr, va, test, reg)
    metrics["interval"] = {
        "ci_method": interval["method"],
        "ci_inflation": round(float(interval["inflation"]), 4),
        "ci_coverage_80": round(float(interval["coverage_calibrated"]), 4),
        "ci_coverage_80_raw": (
            None if interval["coverage_raw"] is None
            else round(float(interval["coverage_raw"]), 4)
        ),
        "ci_coverage_80_test": round(float(interval["coverage_test"]), 4),
        "residual_p80": round(float(interval["residual_p80"]), 4),
        "calib_rows": interval["calib_rows"],
        "calib_months": interval["calib_months"],
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(reg, ARTIFACT_DIR / f"wai_reg_{MODEL_VERSION}.joblib")
    joblib.dump(clf, ARTIFACT_DIR / f"wai_clf_{MODEL_VERSION}.joblib")
    joblib.dump(le, ARTIFACT_DIR / f"severity_encoder_{MODEL_VERSION}.joblib")
    with open(ARTIFACT_DIR / "metrics.json", "w") as fh:
        json.dump(metrics, fh, indent=2, default=str)

    print("\n================== RESULTS ==================")
    print(f"RMSE: {rmse:.3f}   MAE: {mae:.3f}   R2: {r2:.3f}")
    print(
        f"Persistence baseline: RMSE {pers_rmse:.3f}  MAE {pers_mae:.3f}  "
        f"R2 {pers_r2:.3f}"
    )
    print(
        f"vs persistence: model {'BEATS' if mae < pers_mae else 'trails'} "
        f"baseline (MAE delta {mae - pers_mae:+.3f})"
    )
    print(f"Severity accuracy: {acc:.3f}")
    print(f"Confusion matrix:\n{cm}")
    print(f"Artifacts -> {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
