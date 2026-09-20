import sys; sys.path.insert(0, '/app')
import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from infrastructure.db.engine import SessionLocal
from ml.features.feature_engineering import FloodFeatureBuilder

db = SessionLocal()

print("=== MODEL Backtest: Raw XGBoost on 30-day holdout ===")
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
            
            # Train model
            import xgboost as xgb
            from sklearn.preprocessing import StandardScaler
            
            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_test_s = scaler.transform(X_test)
            
            model = xgb.XGBRegressor(
                n_estimators=300, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.7,
                reg_alpha=0.5, reg_lambda=2.0, min_child_weight=5,
            )
            
            # Log transform
            y_train_log = np.log1p(np.maximum(y_train, 0))
            
            model.fit(X_train_s, y_train_log, eval_set=[(X_test_s, np.log1p(np.maximum(y_test, 0)))], verbose=False)
            
            y_pred_log = model.predict(X_test_s)
            y_pred = np.expm1(y_pred_log)
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
            print(f"  {name:>10} {horizon:>5}d {mae:>10,.0f} {mape:>7.1f}% {r2:>8.3f} {len(X_test):>5} {quality:>10}")
            
        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")

db.close()
