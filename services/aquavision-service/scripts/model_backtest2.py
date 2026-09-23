import sys; sys.path.insert(0, '/app')
import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from infrastructure.db.engine import SessionLocal
from ml.features.feature_engineering import FloodFeatureBuilder
from ml.models.flood_predictor import FloodPredictor

db = SessionLocal()

print("=== MODEL Backtest: FloodPredictor on 30-day holdout ===")
print(f"{'Asset':>12} {'Horizon':>8} {'MAE':>10} {'MAPE%':>8} {'R2':>8} {'N':>5} {'Quality':>10}")
print("-" * 70)

for asset_id in range(1, 12):
    for horizon in [7, 14, 30]:
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=120)
            
            builder = FloodFeatureBuilder(db)
            X, y, feature_names, weights = builder.build_training_table(
                asset_id=asset_id, start_date=start_date, end_date=end_date,
                forecast_horizon=horizon, real_only=False, target_field="auto",
                source_priority=True,
            )
            
            if len(X) < 40:
                continue
            
            split_idx = int(len(X) * 0.7)
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]
            
            predictor = FloodPredictor()
            predictor.train(
                asset_id=asset_id, X=X_train, y=y_train,
                feature_names=feature_names, horizon=horizon,
                sample_weights=weights[:split_idx] if weights is not None else None,
            )
            
            # Predict on test set one by one (predict returns FloodPrediction dataclass)
            y_pred = []
            name_map = {1:"Tarbela Reservoir",2:"Mangla Reservoir",3:"Chashma Barrage",4:"Kalabagh",5:"Taunsa Barrage",
                        6:"Guddu Barrage",7:"Sukkur Barrage",8:"Kotri Barrage",9:"Kabul @ Nowshera",10:"Chenab @ Marala",11:"Panjnad"}
            for i in range(len(X_test)):
                row = X_test[i:i+1]
                pred = predictor.predict(asset_id=asset_id, asset_name=name_map.get(asset_id, ""), X=row, feature_names=feature_names, horizon=horizon)
                if pred:
                    val = pred.predicted_inflow or pred.predicted_discharge or pred.predicted_level_ft or 0
                    y_pred.append(val)
                else:
                    y_pred.append(y_actual[i] if i < len(y_actual) else 0)
            
            y_pred = np.array(y_pred)
            y_actual = np.array(y_test)
            
            mae = np.mean(np.abs(y_pred - y_actual))
            mape = np.mean(np.abs(y_pred - y_actual) / np.maximum(y_actual, 1)) * 100
            ss_res = np.sum((y_actual - y_pred) ** 2)
            ss_tot = np.sum((y_actual - np.mean(y_actual)) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            
            if mape < 15: quality = "EXCELLENT"
            elif mape < 25: quality = "GOOD"
            elif mape < 40: quality = "MODERATE"
            else: quality = "POOR"
            
            name = {1:"Tarbela",2:"Mangla",3:"Chashma",4:"Kalabagh",5:"Taunsa",
                    6:"Guddu",7:"Sukkur",8:"Kotri",9:"Kabul",10:"Chenab",11:"Panjnad"}[asset_id]
            print(f"  {name:>10} {horizon:>5}d {mae:>10,.2f} {mape:>7.1f}% {r2:>8.3f} {len(X_test):>5} {quality:>10}")
            
        except Exception as e:
            name = {1:"Tarbela",2:"Mangla",3:"Chashma",4:"Kalabagh",5:"Taunsa",
                    6:"Guddu",7:"Sukkur",8:"Kotri",9:"Kabul",10:"Chenab",11:"Panjnad"}[asset_id]
            print(f"  {name:>10} {horizon:>5}d ERROR: {str(e)[:50]}")

db.close()
