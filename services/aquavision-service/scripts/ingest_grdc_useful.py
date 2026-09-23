import os
os.environ['DATABASE_URL'] = 'postgresql://postgres:1234@localhost:5433/ibcp_scada'

import re
from datetime import datetime
from sqlalchemy import text
from infrastructure.db.engine import SessionLocal

GRDC_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'grdc')
M3S_TO_CUSECS = 35.3147

# GRDC station -> asset mapping
# Kabul tributaries -> Asset 9 (Kabul@Nowshera)
# Jhelum@Chinari -> Asset 2 (Mangla)
STATION_ASSET_MAP = {
    '2240100': 9,  # Kabul @ Dakah
    '2240101': 9,  # Kabul @ Near Daronta
    '2240102': 9,  # Kabul @ Naglu
    '2240103': 9,  # Kabul @ Tang-i-Gharu
    '2336350': 2,  # Jhelum @ Chinari -> Mangla
}

def parse_grdc_file(filepath):
    """Parse GRDC Export format: YYYY-MM-DD;hh:mm;Value"""
    observations = []
    in_data = False
    with open(filepath, 'r', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if 'YYYY-MM-DD' in line:
                in_data = True
                continue
            if not in_data:
                continue
            parts = line.split(';')
            if len(parts) < 3:
                continue
            try:
                date_str = parts[0].strip()
                value_str = parts[2].strip()
                date = datetime.strptime(date_str[:10], '%Y-%m-%d')
                value = float(value_str)
                if value < 0 or abs(value - (-999)) < 0.01:
                    continue
                observations.append((date, value))
            except (ValueError, IndexError):
                continue
    return observations


def get_grdc_source_id(db):
    row = db.execute(text(
        "SELECT id FROM aquavision.water_sources WHERE authority = :n LIMIT 1"
    ), {'n': 'GRDC'}).fetchone()
    if row:
        return row[0]
    db.execute(text(
        "INSERT INTO aquavision.water_sources (authority, source_url, source_type, update_frequency, description, created_at) "
        "VALUES ('GRDC', 'https://grdc.bafg.de', 'CSV', 'ONE_TIME', 'Global Runoff Data Centre', NOW())"
    ))
    db.commit()
    row = db.execute(text("SELECT id FROM aquavision.water_sources WHERE authority = :n"), {'n': 'GRDC'}).scalar()
    print(f"Created GRDC source id={row}")
    return row


def main():
    db = SessionLocal()
    source_id = get_grdc_source_id(db)
    total_inserted = 0

    for grdc_no, asset_id in STATION_ASSET_MAP.items():
        fname = f"{grdc_no}_Q_Day.Cmd.txt"
        fpath = os.path.join(GRDC_DIR, fname)
        if not os.path.exists(fpath):
            print(f"SKIP: {fname} not found")
            continue

        observations = parse_grdc_file(fpath)
        print(f"\n{fname}: {len(observations)} obs -> Asset {asset_id}")

        inserted = 0
        for date, discharge_m3s in observations:
            discharge_cusecs = discharge_m3s * M3S_TO_CUSECS

            existing = db.execute(text(
                "SELECT id FROM aquavision.water_observations "
                "WHERE asset_id = :aid AND observed_at = :dt AND discharge_cusecs IS NOT NULL"
            ), {'aid': asset_id, 'dt': date}).fetchone()

            if existing:
                continue

            db.execute(text(
                "INSERT INTO aquavision.water_observations "
                "(asset_id, source_id, observed_at, discharge_cusecs, unit, data_status, data_origin, "
                "quality_status, source_authority, source_priority, created_at) "
                "VALUES (:aid, :sid, :dt, :dis, 'cusecs', 'OBSERVED_OFFICIAL', 'REAL', "
                "'VALID', 'GRDC', 1, NOW()) "
                "ON CONFLICT (asset_id, observed_at, source_id) DO NOTHING"
            ), {'aid': asset_id, 'sid': source_id, 'dt': date, 'dis': round(discharge_cusecs, 2)})
            inserted += 1

        db.commit()
        total_inserted += inserted
        print(f"  Inserted {inserted} new observations")

    db.close()
    print(f"\nTotal inserted: {total_inserted}")


if __name__ == "__main__":
    main()
