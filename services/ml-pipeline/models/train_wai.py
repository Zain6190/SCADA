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
