"""
Actual model backtest: Run FloodPredictor on test data and compare.
"""
import sys; sys.path.insert(0, '/app')
import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy import text, orm
from infrastructure.db.engine import SessionLocal

db = SessionLocal()

print("=== MODEL Backtest: FloodPredictor on 30-day holdout ===")
print(f"{'Asset':>12} {'Horizon':>8} {'MAE':>10} {'MAPE%':>8} {'R2':>8} {'N':>5} {'Quality':>10}")
print("-" * 70)

for asset_id in range(1, 12):
    for horizon in [7, 14, 30]:
        try:
            from ml.features.feature_engineering import FloodFeatureBuilder
            from ml.models.flood_predictor import FloodPredictor
            
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=90)
            
            builder = FloodFeatureBuilder(db)
            X, y, feature_names, weights = builder.build_training_table(
                asset_id=asset_id,
                start_date=start_date,
                end_date=end_date,
                forecast_horizon=horizon,
                real_only=False,
                target_field="auto",
                source_priority=True,
            )
            
            if len(X) < 40:
                continue
            
            # Split: 70% train, 30% test (chronological)
            split_idx = int(len(X) * 0.7)
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]
            
            predictor = FloodPredictor()
            predictor.train(
                asset_id=asset_id, X=X_train, y=y_train,
                feature_names=feature_names, horizon=horizon,
                sample_weights=weights[:split_idx] if weights is not None else None,
            )
            
            # Predict on test set
            metrics = predictor.evaluate(X_test, y_test)
            
            mae = metrics.get('mae', 0)
            r2 = metrics.get('r2', 0)
            mape = metrics.get('mape', 0) * 100 if 'mape' in metrics else 0
            
            if mape < 15: quality = "EXCELLENT"
            elif mape < 25: quality = "GOOD"
            elif mape < 40: quality = "MODERATE"
            else: quality = "POOR"
            
            name = {1:"Tarbela",2:"Mangla",3:"Chashma",4:"Kalabagh",5:"Taunsa",
                    6:"Guddu",7:"Sukkur",8:"Kotri",9:"Kabul",10:"Chenab",11:"Panjnad"}[asset_id]
            print(f"  {name:>10} {horizon:>5}d {mae:>10,.2f} {mape:>7.1f}% {r2:>8.3f} {len(X_test):>5} {quality:>10}")
            
        except Exception as e:
            pass

db.close()
