import sys; sys.path.insert(0, '/app')
from sqlalchemy import text
from infrastructure.db.engine import SessionLocal

db = SessionLocal()

# 1. Check existing forecasts
rows = db.execute(text("""
    SELECT asset_id, COUNT(*) as cnt, MIN(target_time) as first_t, MAX(target_time) as last_t
    FROM aquavision.water_asset_forecasts GROUP BY asset_id ORDER BY asset_id
""")).mappings().all()
print("=== Existing Forecasts ===")
for r in rows:
    print(f"  Asset {r['asset_id']:2d}: {r['cnt']} forecasts, {r['first_t']} to {r['last_t']}")

# 2. Offline evaluation: compare last 7d predictions to actual observations
# For each asset, get the most recent prediction, find the actual observation at target_time
print("\n=== Offline Accuracy: Last Prediction vs Actual ===")
print(f"{'Asset':>12} {'Target':>10} {'Predicted':>12} {'Actual':>12} {'Error%':>8} {'MAPE':>8}")
print("-" * 70)

for asset_id in range(1, 12):
    # Get latest prediction
    pred = db.execute(text("""
        SELECT predicted_level_ft, predicted_inflow, predicted_outflow,
               predicted_discharge, target_time
        FROM aquavision.water_asset_forecasts
        WHERE asset_id = :aid
        ORDER BY target_time DESC LIMIT 1
    """), {"aid": asset_id}).mappings().first()
    
    if not pred:
        continue
    
    # Resolve which field was predicted and read the MATCHING actual column —
    # comparing an outflow prediction to an inflow observation is meaningless.
    if pred['predicted_inflow'] is not None:
        target_field, predicted = "inflow", pred['predicted_inflow']
        actual_col = "inflow_cusecs"
    elif pred['predicted_outflow'] is not None:
        target_field, predicted = "outflow", pred['predicted_outflow']
        actual_col = "outflow_cusecs"
    elif pred['predicted_discharge'] is not None:
        target_field, predicted = "discharge", pred['predicted_discharge']
        actual_col = "discharge_cusecs"
    else:
        target_field, predicted = "level", pred['predicted_level_ft']
        actual_col = "water_level_ft"
    target_time = pred['target_time']
    
    # Find actual observation near target_time
    actual = db.execute(text(f"""
        SELECT {actual_col} AS val, observed_at
        FROM aquavision.water_observations
        WHERE asset_id = :aid 
          AND observed_at BETWEEN :t1 AND :t2
          AND {actual_col} IS NOT NULL
        ORDER BY EXTRACT(EPOCH FROM (observed_at - :t3)) LIMIT 1
    """), {"aid": asset_id, "t1": target_time, "t2": target_time, "t3": target_time}).mappings().first()
    
    if actual:
        actual_val = actual['val']
        if actual_val and predicted:
            error_pct = abs(predicted - actual_val) / actual_val * 100
            print(f"  Asset {asset_id:2d} {target_field:>10} {predicted:>12,.0f} {actual_val:>12,.0f} {error_pct:>7.1f}%")
    else:
        print(f"  Asset {asset_id:2d} {target_field:>10} {predicted:>12,.0f} {'N/A':>12} {'N/A':>8}")

# 3. Training metrics — read from the single canonical model_metadata.json
print("\n=== Training Metrics (data/models/model_metadata.json) ===")
import json
from pathlib import Path

meta_path = Path(__file__).resolve().parent.parent / "data" / "models" / "model_metadata.json"
if meta_path.exists():
    with open(meta_path) as f:
        meta = json.load(f)
    assets = meta.get("assets", {}) if isinstance(meta, dict) else {}
    if not assets and isinstance(meta, list):
        # legacy flat list
        for item in meta:
            aid = item.get("asset_id")
            assets.setdefault(str(aid), {"asset_name": item.get("asset_name", ""), "models": {}})
            key = item.get("model_type", "model")
            assets[str(aid)]["models"][key] = item
    print(f"{'Asset':>12} {'Model':>24} {'R2':>8} {'MAE':>12} {'Status':>12}")
    print("-" * 72)
    for aid, asset in sorted(assets.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
        name = asset.get("asset_name") or f"Asset {aid}"
        for key, m in (asset.get("models") or {}).items():
            r2 = m.get("r2")
            mae = m.get("mae")
            status = m.get("status") or m.get("model_status") or "?"
            r2_s = f"{float(r2):8.3f}" if r2 is not None else f"{'—':>8}"
            mae_s = f"{float(mae):12,.1f}" if mae is not None else f"{'—':>12}"
            print(f"  {str(name)[:10]:>10} {key[:24]:>24} {r2_s} {mae_s} {status:>12}")
else:
    print(f"  No model metadata at {meta_path} — run retrain_all_models.py first.")

db.close()
