# ml/train_flood_model.py
# Train flood prediction models for all assets.
# Usage: python -m ml.train_flood_model

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from datetime import datetime, timedelta

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterAsset
from ml.features.feature_engineering import FloodFeatureBuilder
from ml.models.flood_predictor import FloodPredictor, HighFlowPredictor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aquavision.ml.train")


def train_all_assets(horizons=[7, 14, 30]):
    """Train flood prediction models for all active assets."""
    predictor = FloodPredictor()
    hf_predictor = HighFlowPredictor()
    results = []
    
    with SessionLocal() as session:
        assets = session.execute(
            select(WaterAsset).where(WaterAsset.is_active == True)
        ).scalars().all()
        
        for asset in assets:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training for: {asset.canonical_name} (ID: {asset.id})")
            logger.info(f"{'='*60}")
            
            builder = FloodFeatureBuilder(session)
            
            # Use all available data
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=400)  # Get all available data
            
            for horizon in horizons:
                logger.info(f"\n--- Horizon: {horizon} days ---")
                
                X, y, feature_names, weights = builder.build_training_table(
                    asset_id=asset.id,
                    start_date=start_date,
                    end_date=end_date,
                    forecast_horizon=horizon,
                )
                
                if len(X) == 0:
                    logger.warning(f"  No training data for {asset.canonical_name} horizon={horizon}")
                    continue
                
                # Train standard model
                metrics = predictor.train(
                    asset_id=asset.id,
                    X=X,
                    y=y,
                    feature_names=feature_names,
                    horizon=horizon,
                )
                results.append(metrics)
                
                # Train high-flow model
                if len(X) >= 20:
                    hf_metrics = hf_predictor.train(
                        asset_id=asset.id,
                        X=X,
                        y=y,
                        feature_names=feature_names,
                        horizon=horizon,
                    )
                    results.append(hf_metrics)
                    logger.info(f"  High-flow model: R2={hf_metrics.get('r2', 'N/A')}")
    
    return results


def test_prediction(asset_id: int = 1, horizon: int = 7):
    """Test prediction for a single asset."""
    predictor = FloodPredictor()
    
    with SessionLocal() as session:
        asset = session.get(WaterAsset, asset_id)
        if not asset:
            logger.error(f"Asset {asset_id} not found")
            return
        
        builder = FloodFeatureBuilder(session)
        
        X, feature_names = builder.build_prediction_features(
            asset_id=asset_id,
            as_of_date=datetime.utcnow(),
        )
        
        if X is None:
            logger.error(f"Insufficient data for prediction")
            return
        
        prediction = predictor.predict(
            asset_id=asset_id,
            asset_name=asset.canonical_name,
            X=X,
            feature_names=feature_names,
            horizon=horizon,
            warning_level=float(asset.warning_level_ft) if asset.warning_level_ft else None,
            danger_level=float(asset.critical_level_ft) if asset.critical_level_ft else None,
        )
        
        if prediction:
            logger.info(f"\n{'='*60}")
            logger.info(f"PREDICTION: {asset.canonical_name}")
            logger.info(f"{'='*60}")
            logger.info(f"  Horizon: {prediction.horizon_days} days")
            logger.info(f"  Predicted Level: {prediction.predicted_level_ft} ft")
            logger.info(f"  Prediction Interval: [{prediction.lower_bound}, {prediction.upper_bound}]")
            logger.info(f"  Risk Score: {prediction.risk_score}/100")
            logger.info(f"  Risk Level: {prediction.risk_level}")
            logger.info(f"  Exceeds Warning: {prediction.exceeds_warning}")
            logger.info(f"  Exceeds Danger: {prediction.exceeds_danger}")
            logger.info(f"  Top Features: {prediction.feature_importance}")
        else:
            logger.error("Prediction failed - model not trained")


if __name__ == "__main__":
    from sqlalchemy import select
    
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asset_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        horizon = int(sys.argv[3]) if len(sys.argv) > 3 else 7
        test_prediction(asset_id, horizon)
    else:
        results = train_all_assets()
        logger.info(f"\n\nTraining complete. {len(results)} models trained.")
