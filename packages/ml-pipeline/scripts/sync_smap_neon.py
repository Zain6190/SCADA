"""Sync region_features.csv (with SMAP) to Neon DB indicators table.
Uses psycopg2 executemany for speed."""
import csv
import os
from datetime import date
import psycopg2
import numpy as np
import pandas as pd

DB_DSN = os.getenv('DATABASE_URL', '').replace('postgresql+psycopg2://', 'postgresql://')
if not DB_DSN:
    raise RuntimeError('Set DATABASE_URL env var')

rows = []
with open('/tmp/region_features.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

df = pd.DataFrame(rows)
df['region_id'] = pd.to_numeric(df['region_id'], errors='coerce').astype(int)
for c in ['rainfall_mm','et_mm','water_extent','ndvi','sm_rootzone','sm_surface']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df['month'] = pd.to_datetime(df['month'])

FEATURE_COLS = ['rainfall_mm', 'et_mm', 'water_extent', 'ndvi', 'sm_rootzone', 'sm_surface']
WEIGHTS = {'rainfall_mm': 0.25, 'ndvi': 0.20, 'water_extent': 0.15, 'et_mm': 0.15, 'sm_rootzone': 0.15, 'sm_surface': 0.10}

def minmax(s):
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.5, index=s.index)
    return (s - lo) / (hi - lo)

df.loc[df['water_extent'] == -1, 'water_extent'] = float('nan')
for col in FEATURE_COLS:
    if col == 'et_mm':
        df[col + '_norm'] = 1.0 - minmax(df[col])
    else:
        df[col + '_norm'] = minmax(df[col])

norm_cols = [c + '_norm' for c in FEATURE_COLS]
present = df[norm_cols].notna()
w = pd.Series([WEIGHTS[c] for c in FEATURE_COLS], index=norm_cols)
w_avail = present.multiply(w, axis=1)
w_sum = w_avail.sum(axis=1).replace(0, np.nan)
df['wai_score'] = (df[norm_cols].fillna(0).multiply(w_avail, axis=1).sum(axis=1) / w_sum) * 100.0

def classify(wai):
    if wai < 25: return 'Critical'
    if wai < 40: return 'Severe'
    if wai < 55: return 'Stressed'
    if wai < 70: return 'Moderate'
    return 'Normal'

SOURCE_VERSION = 'GEE-CHIRPS/ERA5-JRC-SMAP-2026.8'
MODEL_VERSION = 'composite-v2.0'

# Build all params
params = []
for _, r in df.sort_values(['region_id','month']).iterrows():
    rainfall = None if np.isnan(r['rainfall_mm']) else round(float(r['rainfall_mm']), 2)
    et = round(float(r['et_mm']), 2) if (not np.isnan(r['et_mm']) and r['et_mm'] > 0) else None
    sm_r = None if np.isnan(r['sm_rootzone']) else round(float(r['sm_rootzone']), 6)
    sm_s = None if np.isnan(r['sm_surface']) else round(float(r['sm_surface']), 6)
    wai = round(float(r['wai_score']), 2) if not np.isnan(r['wai_score']) else 50.0
    sev = classify(wai)
    m = r['month']
    ws = m.strftime('%Y-%m-%d')
    pe = (m + pd.offsets.MonthEnd(0)).strftime('%Y-%m-%d')
    params.append({
        'rid': int(r['region_id']), 'ws': ws,
        'wn': int(m.isocalendar()[1]), 'yr': int(m.year),
        'ps': ws, 'pe': pe,
        'comp': True, 'cov': 100.0,
        'obs': int(m.days_in_month), 'exp': int(m.days_in_month),
        'qs': 'VALID', 'rain': rainfall, 'et': et,
        'smr': sm_r, 'sms': sm_s, 'wai': wai, 'sev': sev,
        'src': SOURCE_VERSION, 'ds': 'Actual', 'dq': 'Good',
        'dp': 'GEE', 'mv': MODEL_VERSION, 'soa': pe,
    })

print(f'Built {len(params)} param sets')

SQL = """
INSERT INTO aquavision.water_indicators_weekly
    (region_id, week_start_date, week_number, year, period_start, period_end,
     is_complete_period, coverage_percent, observation_count, expected_observation_count,
     quality_status, rainfall_mm_30day, et_mm_8day, sm_rootzone, sm_surface,
     wai_score, severity, data_source_version, data_status, data_quality,
     data_provider, wai_model_version, source_observed_at, last_validated_at)
VALUES
    (%(rid)s, %(ws)s, %(wn)s, %(yr)s, %(ps)s, %(pe)s,
     %(comp)s, %(cov)s, %(obs)s, %(exp)s, %(qs)s,
     %(rain)s, %(et)s, %(smr)s, %(sms)s,
     %(wai)s, %(sev)s, %(src)s, %(ds)s, %(dq)s,
     %(dp)s, %(mv)s, %(soa)s, now())
ON CONFLICT (region_id, week_start_date)
DO UPDATE SET
    rainfall_mm_30day = EXCLUDED.rainfall_mm_30day,
    et_mm_8day = EXCLUDED.et_mm_8day,
    sm_rootzone = EXCLUDED.sm_rootzone,
    sm_surface = EXCLUDED.sm_surface,
    wai_score = EXCLUDED.wai_score,
    severity = EXCLUDED.severity,
    data_source_version = EXCLUDED.data_source_version,
    data_status = EXCLUDED.data_status,
    wai_model_version = EXCLUDED.wai_model_version,
    source_observed_at = EXCLUDED.source_observed_at,
    last_validated_at = now()
"""

conn = psycopg2.connect(DB_DSN)
conn.autocommit = False
cur = conn.cursor()
batch_size = 100
for i in range(0, len(params), batch_size):
    batch = params[i:i+batch_size]
    cur.executemany(SQL, batch)
    conn.commit()
    print(f'Batch {i//batch_size + 1}: committed {len(batch)} rows (total {i+len(batch)})')

cur.close()
conn.close()
print(f'Done: upserted {len(params)} rows to Neon')
