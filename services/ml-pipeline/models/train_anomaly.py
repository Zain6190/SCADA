"""
models/train_anomaly.py
AquaVision - Train an IsolationForest anomaly detector on the GEE features.

Catches "deviations from normal" that a severity bucket alone would miss
(e.g. sudden ET spike, extreme rainfall deficit, NDVI collapse). The score
feeds the risk & alert workflow alongside the WAI prediction.

Artifacts -> models/artifacts/anomaly_if.joblib
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

ML_ROOT = Path(__file__).resolve().parent.parent
DSET_CSV = ML_ROOT / "Data" / "features" / "dataset.csv"
ARTIFACT_DIR = ML_ROOT / "models" / "artifacts"

sys.path.insert(0, str(ML_ROOT))
from wai_features import FEATURE_COLS  # noqa: E402

CONTAMINATION = 0.05


def main() -> None:
    df = pd.read_csv(DSET_CSV)
    for col in FEATURE_COLS:
        df[col] = df[col].fillna(df[col].median())

    model = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=42,
    )
    model.fit(df[FEATURE_COLS])

    scores = model.decision_function(df[FEATURE_COLS])
    labels = model.predict(df[FEATURE_COLS])  # 1 normal, -1 anomaly
    n_anom = int((labels == -1).sum())

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, ARTIFACT_DIR / "anomaly_if.joblib")
    with open(ARTIFACT_DIR / "anomaly_metrics.json", "w") as fh:
        json.dump(
            {
                "contamination": CONTAMINATION,
                "n_rows": int(len(df)),
                "n_anomalies": n_anom,
                "anomaly_rate": round(n_anom / len(df), 4),
                "score_min": round(float(scores.min()), 4),
                "score_max": round(float(scores.max()), 4),
            },
            fh,
            indent=2,
        )

    print(f"[train_anomaly] Fitted IsolationForest on {len(df)} rows")
    print(f"[train_anomaly] anomalies detected: {n_anom} ({100*n_anom/len(df):.1f}%)")
    print(f"[train_anomaly] artifact -> {ARTIFACT_DIR / 'anomaly_if.joblib'}")


if __name__ == "__main__":
    main()