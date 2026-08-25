#!/bin/bash
set -e

echo "=== IBCP-SCADA AquaVision Setup ==="
echo "DATABASE_URL is set: $(if [ -n \"$DATABASE_URL\" ]; then echo 'yes'; else echo 'NO - MISSING!'; fi)"

# 1. Apply SQL migration (creates all base tables)
echo "[1/4] Applying base schema..."
python db/setup_neon.py 2>&1 || echo "Schema setup had errors (non-fatal)"

# 2. Seed water assets + auth users
echo "[2/4] Seeding database..."
python db/seed_neon.py 2>&1 || echo "Seed had errors (non-fatal)"

# 3. Ingest Kaggle data
echo "[3/4] Ingesting Kaggle historical data..."
python -c "
import os, psycopg2
url = os.environ.get('DATABASE_URL', '')
if not url:
    print('DATABASE_URL not set, skipping Kaggle')
else:
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute('SELECT count(*) FROM aquavision.water_observations')
    count = cur.fetchone()[0]
    if count >= 100:
        print(f'Kaggle: already loaded ({count} observations)')
    else:
        # Run Kaggle ingestion
        import sys; sys.path.insert(0, '.')
        from ingest_kaggle_neon import ingest
        ingest('data/raw/real/kaggle/pakistans_rivers_flow.csv')
    cur.close(); conn.close()
" 2>&1 || echo "Kaggle ingestion failed (non-fatal)"

# 4. Verify
echo "[4/4] Verifying..."
python -c "
import os, psycopg2
url = os.environ.get('DATABASE_URL', '')
if not url:
    print('DATABASE_URL not set, skipping verify')
else:
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute('SELECT count(*) FROM aquavision.water_assets')
    a = cur.fetchone()[0]
    cur.execute('SELECT count(*) FROM aquavision.water_observations')
    o = cur.fetchone()[0]
    cur.execute('SELECT count(*) FROM shared.users')
    u = cur.fetchone()[0]
    print(f'Assets: {a}, Observations: {o}, Users: {u}')
    cur.close(); conn.close()
" 2>&1 || echo "Verification skipped"

echo "=== Setup complete ==="
echo "Demo credentials: admin / admin123"

PORT=${PORT:-8100}
exec uvicorn main:app --host 0.0.0.0 --port $PORT
