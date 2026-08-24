#!/bin/bash
set -e

echo "=== IBCP-SCADA AquaVision Setup ==="

# 1. Run Alembic migrations
echo "[1/4] Running database migrations..."
alembic upgrade head

# 2. Seed water assets + auth users
echo "[2/4] Seeding database..."
python db/seed.py

# 3. Ingest Kaggle data (idempotent — skips if already loaded)
echo "[3/4] Ingesting Kaggle historical data..."
python -c "
from infrastructure.ingestion.kaggle_ingest import ingest_kaggle_csv
from infrastructure.db.engine import SessionLocal
import os

csv_path = 'data/raw/real/kaggle/pakistans_rivers_flow.csv'
if os.path.exists(csv_path):
    session = SessionLocal()
    try:
        count = session.execute('SELECT count(*) FROM aquavision.water_observations').scalar()
        if count < 100:
            ingest_kaggle_csv(session, csv_path)
            print(f'Kaggle: loaded observations')
        else:
            print(f'Kaggle: already loaded ({count} observations)')
    finally:
        session.close()
else:
    print(f'Kaggle CSV not found at {csv_path} — skipping')
"

# 4. Train ML models (idempotent — only trains if no models exist)
echo "[4/4] Training ML models..."
python -c "
import os
from ml.train_flood_model import train_all_assets
model_dir = 'models/flood_xgb'
existing = [f for f in os.listdir(model_dir) if f.endswith('.joblib')] if os.path.exists(model_dir) else []
if len(existing) < 6:
    print('Training ML models (this takes ~5 minutes)...')
    results = train_all_assets()
    print(f'Trained {len(results)} models')
else:
    print(f'ML models already exist ({len(existing)} files)')
"

echo "=== Setup complete ==="
echo "API running on http://localhost:8100"
echo ""
echo "Demo credentials:"
echo "  admin / admin123"
echo "  water_ops / water123"
echo "  viewer / viewer123"

# Start the API server
exec uvicorn main:app --host 0.0.0.0 --port 8100
