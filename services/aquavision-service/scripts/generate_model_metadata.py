"""Generate model_metadata.json from trained model files.

Writes the canonical nested format to data/models/model_metadata.json
(same path as retrain_all_models.py and /ml/model-metadata).
Run locally (where sklearn/xgboost are installed), then copy the JSON to the container.
"""
import pickle
import joblib
import json
import re
from datetime import datetime
from pathlib import Path

results = []

_BASE = Path(__file__).resolve().parent.parent


def _db_facts():
    """Best-effort asset names + registry lifecycle status; empty when offline."""
    names: dict = {}
    exact: dict = {}
    by_asset: dict = {}
    try:
        from sqlalchemy import text as sql_text
        from infrastructure.db.engine import engine

        with engine.connect() as conn:
            for row in conn.execute(sql_text(
                "SELECT id, canonical_name FROM aquavision.water_assets"
            )).mappings():
                names[int(row["id"])] = row["canonical_name"]
            for row in conn.execute(sql_text(
                "SELECT model_type, asset_id, version, status FROM aquavision.model_versions"
            )).mappings():
                match = re.search(r"-h(\d+)$", str(row["version"] or ""))
                horizon = int(match.group(1)) if match else None
                key = (row["model_type"], int(row["asset_id"]))
                exact[(row["model_type"], int(row["asset_id"]), horizon)] = row["status"]
                by_asset.setdefault(key, set()).add(row["status"])
    except Exception as exc:
        print(f"WARN: DB facts unavailable ({exc}); falling back to file defaults")
    return names, exact, by_asset


ASSET_NAMES, REGISTRY_EXACT, REGISTRY_BY_ASSET = _db_facts()
_REG_TYPE = {"high_flow": "high_flow_predictor"}


def _status(model_type: str, asset_id, horizon, default: str) -> str:
    reg_type = _REG_TYPE.get(model_type, model_type)
    if horizon is not None:
        found = REGISTRY_EXACT.get((reg_type, int(asset_id), int(horizon)))
        if found:
            return found
    statuses = REGISTRY_BY_ASSET.get((reg_type, int(asset_id)))
    if statuses and len(statuses) == 1:
        return next(iter(statuses))
    return default


def _name(asset_id, fallback: str) -> str:
    return ASSET_NAMES.get(int(asset_id)) or fallback

# Flood classifiers (.pkl)
clf_dir = _BASE / "data" / "models"
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
        "asset_name": _name(data.get("asset_id", 0), data.get("asset_name", "")),
        "model_type": "flood_classifier",
        "model_status": _status("flood_classifier", data.get("asset_id", 0), 7, "EXPERIMENTAL"),
        "saved_at": data.get("saved_at"),
        "horizon_days": 7,
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

# Flood predictors (.joblib) — standard (interval companions lack metrics)
pred_dir = _BASE / "models" / "flood_xgb"
for f in sorted(pred_dir.glob("*.joblib")):
    if "_hf" in f.name or "_interval" in f.name:
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
        _aid = metrics.get("asset_id", int(parts[0]))
        _horizon = int(parts[1]) if len(parts) > 1 else 7
        results.append({
            "asset_id": _aid,
            "asset_name": _name(_aid, f"Asset {parts[0]}"),
            "model_type": "flood_predictor",
            "model_status": _status("flood_predictor", _aid, _horizon, data.get("model_status", "EXPERIMENTAL")),
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
        _aid = metrics.get("asset_id", int(parts[0]))
        _horizon = int(parts[1]) if len(parts) > 1 else 7
        results.append({
            "asset_id": _aid,
            "asset_name": _name(_aid, f"Asset {parts[0]}"),
            "model_type": "high_flow",
            "model_status": _status("high_flow", _aid, _horizon, data.get("model_status", "EXPERIMENTAL")),
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
anom_dir = _BASE / "models" / "anomaly_if"
for f in sorted(anom_dir.glob("*.joblib")):
    try:
        data = joblib.load(f)
        aid = int(f.stem.replace("anomaly_", ""))
        results.append({
            "asset_id": aid,
            "asset_name": _name(aid, f"Asset {aid}"),
            "model_type": "anomaly_detector",
            "model_status": _status("anomaly_detector", aid, None, data.get("model_status", "EXPERIMENTAL")),
            "trained_at": data.get("trained_at"),
            "samples": data.get("training_samples"),
            "model_version": data.get("model_version"),
            "model_file": f.name,
        })
    except Exception as e:
        print(f"WARN: {f.name}: {e}")

def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and not (obj == obj and obj not in (float("inf"), float("-inf"))):
        return None
    return obj


results = [r for r in results if r.get("asset_id") is not None]
results.sort(key=lambda r: (r["asset_id"], {"flood_predictor": 0, "flood_classifier": 1, "anomaly_detector": 2}.get(r["model_type"], 9)))

# Nest into the canonical single-file format used by /ml/model-metadata and /ml/model-performance
assets: dict = {}
for r in results:
    aid = r["asset_id"]
    if aid not in assets:
        assets[aid] = {
            "asset_id": aid,
            "asset_name": r.get("asset_name", ""),
            "models": {},
        }
    horizon = r.get("horizon_days")
    model_type = r.get("model_type", "model")
    key = f"{model_type}_{horizon}" if horizon else model_type
    entry = dict(r)
    entry["status"] = r.get("model_status", "EXPERIMENTAL")
    entry["horizon"] = horizon
    assets[aid]["models"][key] = entry

nested = {
    "generated_at": datetime.utcnow().isoformat(),
    "model_version": "xgb-flood-v1.2",
    "features_enriched": True,
    "weather_features": True,
    "log_transform": True,
    "smote_classifier": True,
    "assets": assets,
}

out_path = _BASE / "data" / "models" / "model_metadata.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(_sanitize(nested), f, indent=2, default=str)

print(f"Generated metadata for {len(results)} models -> {out_path}")
for r in results[:10]:
    r2 = f"R2={r['r2']:.3f}" if r.get("r2") else ""
    auc = f"AUC={r['auc']:.3f}" if r.get("auc") else ""
    acc = f"Acc={r['accuracy']:.3f}" if r.get("accuracy") else ""
    print(f"  {r['asset_name']:25s} [{r['model_type']:20s}] {r2} {auc} {acc}")
