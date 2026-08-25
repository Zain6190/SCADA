#!/bin/bash
set -e

echo "=== IBCP-SCADA AquaVision Setup ==="

# 1. Run Alembic migrations
echo "[1/3] Running database migrations..."
alembic upgrade head

# 2. Seed water assets + auth users
echo "[2/3] Seeding database..."
python db/seed.py

# 3. Ingest Kaggle data (idempotent — skips if already loaded)
echo "[3/3] Ingesting Kaggle historical data..."
python -c "
from infrastructure.ingestion.kaggle_ingest import ingest_kaggle_csv
from infrastructure.db.engine import SessionLocal
import os

csv_path = 'data/raw/real/kaggle/pakistans_rivers_flow.csv'
if os.path.exists(csv_path):
    session = SessionLocal()
    try:
        from sqlalchemy import text
        count = session.execute(text('SELECT count(*) FROM aquavision.water_observations')).scalar()
        if count < 100:
            ingest_kaggle_csv(session, csv_path)
            print('Kaggle: loaded observations')
        else:
            print(f'Kaggle: already loaded ({count} observations)')
    finally:
        session.close()
else:
    print(f'Kaggle CSV not found at {csv_path} — skipping')
" || echo "Kaggle ingestion failed (non-fatal)"

echo "=== Setup complete ==="
echo "Demo credentials: admin / admin123"

# Render provides $PORT, default to 8100 for local
PORT=${PORT:-8100}
exec uvicorn main:app --host 0.0.0.0 --port $PORT
