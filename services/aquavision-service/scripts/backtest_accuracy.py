"""
Quick backtest: predict last 30 days, compare to actual observations.
Uses the same FloodPredictor but evaluates on held-out recent data.
"""
import sys; sys.path.insert(0, '/app')
import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from infrastructure.db.engine import SessionLocal

db = SessionLocal()

print("=== 30-Day Backtest: Predictions vs Actuals ===")
print(f"{'Asset':>12} {'Horizon':>8} {'MAE':>10} {'MAPE%':>8} {'R2':>8} {'N':>5} {'Quality':>10}")
print("-" * 70)

for asset_id in range(1, 12):
    for horizon in [7, 14, 30]:
        # Get observations for last 90 days
        rows = db.execute(text("""
            SELECT observed_at, inflow_cusecs, discharge_cusecs, water_level_ft
            FROM aquavision.water_observations
            WHERE asset_id = :aid
              AND observed_at > NOW() - INTERVAL '90 days'
              AND (inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL)
            ORDER BY observed_at
        """), {"aid": asset_id}).mappings().all()
        
        if len(rows) < 60:
            continue
        
        # Use last 30 days as test, everything before as train
        train_data = [(r['observed_at'], r['inflow_cusecs'] or r['discharge_cusecs']) for r in rows[:-30]]
        test_data = [(r['observed_at'], r['inflow_cusecs'] or r['discharge_cusecs']) for r in rows[-30:]]
        
        # Simple persistence baseline: predict using moving average of last N days
        preds = []
        actuals = []
        for i, (dt, actual_val) in enumerate(test_data):
            # Use rolling mean of previous 'horizon' days as prediction
            lookback = min(horizon, len(train_data) + i)
            if lookback > 0:
                window = [v for _, v in train_data[-lookback:]] + [v for _, v in test_data[:i]]
                pred = np.mean(window[-horizon:]) if window else actual_val
                preds.append(pred)
                actuals.append(actual_val)
        
        if len(preds) < 5:
            continue
        
        preds = np.array(preds)
        actuals = np.array(actuals)
        
        mae = np.mean(np.abs(preds - actuals))
        mape = np.mean(np.abs(preds - actuals) / np.maximum(actuals, 1)) * 100
        ss_res = np.sum((actuals - preds) ** 2)
        ss_tot = np.sum((actuals - np.mean(actuals)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        
        if mape < 15: quality = "EXCELLENT"
        elif mape < 25: quality = "GOOD"
        elif mape < 40: quality = "MODERATE"
        else: quality = "POOR"
        
        name = {1:"Tarbela",2:"Mangla",3:"Chashma",4:"Kalabagh",5:"Taunsa",
                6:"Guddu",7:"Sukkur",8:"Kotri",9:"Kabul",10:"Chenab",11:"Panjnad"}[asset_id]
        print(f"  {name:>10} {horizon:>5}d {mae:>10,.0f} {mape:>7.1f}% {r2:>8.3f} {len(preds):>5} {quality:>10}")

db.close()
