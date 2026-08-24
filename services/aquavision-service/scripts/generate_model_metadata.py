"""Generate model_metadata.json from trained model files.
Run locally (where sklearn/xgboost are installed), then copy the JSON to the container.
"""
import pickle
import joblib
import json
from pathlib import Path

results = []

# Flood classifiers (.pkl)
clf_dir = Path("services/aquavision-service/data/models")
for f in sorted(clf_dir.glob("flood_classifier_asset_*.pkl")):
    with open(f, "rb") as fh:
        data = pickle.load(fh)
    metrics = data.get("metrics", {})
    fi = metrics.get("top_features", {})
    if isinstance(fi, list):
        fi = dict(fi[:10])
    elif isinstance(fi, dict):
        fi = dict(sorted(fi.items(), key=lambda x: abs(x[1]), reverse=True)[:10])
    results.append({
        "asset_id": data.get("asset_id", 0),
        "asset_name": data.get("asset_name", ""),
        "model_type": "flood_classifier",
        "model_status": "EXPERIMENTAL",
        "saved_at": data.get("saved_at"),
        "train_samples": metrics.get("train_samples"),
        "test_samples": metrics.get("test_samples"),
        "accuracy": metrics.get("accuracy"),
        "auc": metrics.get("auc"),
        "f1": metrics.get("f1"),
        "precision": metrics.get("precision"),
        "recall": metrics.get("recall"),
        "feature_importance": fi,
        "model_file": f.name,
    })

# Flood predictors (.joblib) — standard
pred_dir = Path("services/aquavision-service/models/flood_xgb")
for f in sorted(pred_dir.glob("*.joblib")):
    if "_hf" in f.name:
        continue
    try:
        data = joblib.load(f)
        metrics = data.get("metrics", {})
        fi = metrics.get("top_features", {})
        if isinstance(fi, list):
            fi = dict(fi[:10])
        elif isinstance(fi, dict):
            fi = dict(sorted(fi.items(), key=lambda x: abs(x[1]), reverse=True)[:10])
        parts = f.stem.split("_")
        results.append({
            "asset_id": metrics.get("asset_id", int(parts[0])),
            "asset_name": f"Asset {parts[0]}",
            "model_type": "flood_predictor",
            "model_status": data.get("model_status", "EXPERIMENTAL"),
            "trained_at": metrics.get("trained_at"),
            "saved_at": data.get("saved_at"),
            "samples": metrics.get("samples"),
            "train_samples": metrics.get("train_samples"),
            "test_samples": metrics.get("test_samples"),
            "r2": metrics.get("r2"),
            "mae": metrics.get("mae"),
            "rmse": metrics.get("rmse"),
            "mape": metrics.get("mape"),
            "feature_importance": fi,
            "horizon_days": int(parts[1]) if len(parts) > 1 else 7,
            "model_version": data.get("version"),
            "model_file": f.name,
        })
    except Exception as e:
        print(f"WARN: {f.name}: {e}")

# High-flow predictors (.joblib)
for f in sorted(pred_dir.glob("*_hf.joblib")):
    try:
        data = joblib.load(f)
        metrics = data.get("metrics", {})
        fi = metrics.get("top_features", {})
        if isinstance(fi, list):
            fi = dict(fi[:10])
        elif isinstance(fi, dict):
            fi = dict(sorted(fi.items(), key=lambda x: abs(x[1]), reverse=True)[:10])
        parts = f.stem.replace("_hf", "").split("_")
        results.append({
            "asset_id": metrics.get("asset_id", int(parts[0])),
            "asset_name": f"Asset {parts[0]}",
            "model_type": "high_flow_predictor",
            "model_status": data.get("model_status", "EXPERIMENTAL"),
            "trained_at": metrics.get("trained_at"),
            "saved_at": data.get("saved_at"),
            "samples": metrics.get("samples"),
            "train_samples": metrics.get("train_samples"),
            "test_samples": metrics.get("test_samples"),
            "r2": metrics.get("r2"),
            "mae": metrics.get("mae"),
            "rmse": metrics.get("rmse"),
            "mape": metrics.get("mape"),
            "feature_importance": fi,
            "horizon_days": int(parts[1]) if len(parts) > 1 else 7,
            "model_version": data.get("version"),
            "model_file": f.name,
        })
    except Exception as e:
        print(f"WARN: {f.name}: {e}")

# Anomaly detectors
anom_dir = Path("services/aquavision-service/models/anomaly_if")
for f in sorted(anom_dir.glob("*.joblib")):
    try:
        data = joblib.load(f)
        aid = int(f.stem.replace("anomaly_", ""))
        results.append({
            "asset_id": aid,
            "asset_name": f"Asset {aid}",
            "model_type": "anomaly_detector",
            "model_status": data.get("model_status", "EXPERIMENTAL"),
            "trained_at": data.get("trained_at"),
            "samples": data.get("training_samples"),
            "model_version": data.get("model_version"),
            "model_file": f.name,
        })
    except Exception as e:
        print(f"WARN: {f.name}: {e}")

results.sort(key=lambda r: (r["asset_id"], {"flood_predictor": 0, "flood_classifier": 1, "anomaly_detector": 2}.get(r["model_type"], 9)))

out_path = Path("services/aquavision-service/data/model_metadata.json")
with open(out_path, "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"Generated metadata for {len(results)} models -> {out_path}")
for r in results[:10]:
    r2 = f"R2={r['r2']:.3f}" if r.get("r2") else ""
    auc = f"AUC={r['auc']:.3f}" if r.get("auc") else ""
    acc = f"Acc={r['accuracy']:.3f}" if r.get("accuracy") else ""
    print(f"  {r['asset_name']:25s} [{r['model_type']:20s}] {r2} {auc} {acc}")
