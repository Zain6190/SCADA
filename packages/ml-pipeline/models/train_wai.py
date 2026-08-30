"""
models/train_wai.py
AquaVision - Train WAI regressor + severity classifier (XGBoost).

- Reads Data/features/dataset.csv (from build_dataset.py)
- CHRONOLOGICAL split (first 80% of time = train, last 20% = test) to avoid leakage
- Trains XGBoost regressor for wai_score and XGBoost classifier for severity
- Writes metrics.json + artifacts/*.joblib

Usage:
    python -m models.train_wai   (run from packages/ml-pipeline)
"""
from __future__ import annotations

import json
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

DATASET_CSV = Path(__file__).resolve().parent.parent / "Data" / "features" / "dataset.csv"
ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "models" / "artifacts"

FEATURE_COLS = ["rainfall_mm", "et_mm", "water_extent", "ndvi", "sm_rootzone", "sm_surface", "month_idx"]
TARGET_COL = "wai_score"
SEVERITY_COL = "severity"
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

    X_tr, y_tr = train[FEATURE_COLS], train[TARGET_COL]
    X_te, y_te = test[FEATURE_COLS], test[TARGET_COL]

    # ---- Regressor: wai_score ----
    reg = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        early_stopping_rounds=20,
        random_state=42,
    )
    reg.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
    pred_reg = reg.predict(X_te)

    rmse = float(np.sqrt(mean_squared_error(y_te, pred_reg)))
    mae = float(mean_absolute_error(y_te, pred_reg))
    r2 = float(r2_score(y_te, pred_reg))

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
    clf.fit(X_tr, y_sev_tr)
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
        "n_train": len(train),
        "n_test": len(test),
        "regressor": {"rmse": round(rmse, 4), "mae": round(mae, 4), "r2": round(r2, 4)},
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
    print(f"Severity accuracy: {acc:.3f}")
    print(f"Confusion matrix:\n{cm}")
    print(f"Artifacts -> {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
