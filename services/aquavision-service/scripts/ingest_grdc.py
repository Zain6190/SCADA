"""
ingest_grdc.py - Ingest GRDC discharge data into water_observations.

GRDC Export Format (semicolon-delimited ASCII):
  - Header lines start with #
  - Contains metadata: GRDC-No, River, Station, Country, Latitude, Longitude
  - Data lines: YYYY-MM-DD;--:--;value
  - Value: discharge in m3/s (multiply by 35.3147 to get cusecs)
  - Missing values: -999.000

GRDC Station-to-Asset Mapping (auto-detected from header or filename):
  - Indus @ Sukkur       -> Asset 7
  - Indus @ Attock       -> Asset 4
  - Jhelum @ Mangla      -> Asset 2
  - Chenab @ Marala      -> Asset 10
  - Kabul @ Nowshera     -> Asset 9
  - Indus @ Chashma      -> Asset 3
  - Indus @ Taunsa       -> Asset 5
  - Indus @ Guddu        -> Asset 6
  - Indus @ Kotri        -> Asset 8
  - Panjnad              -> Asset 11
  - Tarbela              -> Asset 1

Usage:
  python ingest_grdc.py --file grdc_sukkur.txt --asset 7
  python ingest_grdc.py --dir ./grdc_data/   (batch mode)
  python ingest_grdc.py --dir ./grdc_data/ --source-id 1  (specify source_id)
"""
import argparse
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

M3S_TO_CUSECS = 35.3147
MISSING_VALUE = -999.0

# Keyword -> asset_id mapping for filename/header detection
STATION_KEYWORDS = {
    "sukkur": 7, "attock": 4, "mangla": 2, "marala": 10,
    "nowshera": 9, "chashma": 3, "taunsa": 5, "guddu": 6,
    "kotri": 8, "panjnad": 11, "tarbela": 1, "rasul": 2,
}


def parse_grdc_header(filepath):
    """Parse GRDC ASCII header to extract metadata.
    
    Returns dict with: station_name, river_name, grdc_no, country, lat, lon, catchment_area
    """
    metadata = {}
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line.startswith('#'):
                break
            line = line.lstrip('#').strip()
            if ':' in line:
                key, val = line.split(':', 1)
                key = key.strip().lower()
                val = val.strip()
                if key == 'grdc-no.':
                    metadata['grdc_no'] = val
                elif key == 'river':
                    metadata['river_name'] = val
                elif key == 'station':
                    metadata['station_name'] = val
                elif key == 'country':
                    metadata['country'] = val
                elif key == 'latitude (dd)':
                    try: metadata['latitude'] = float(val)
                    except: pass
                elif key == 'longitude (dd)':
                    try: metadata['longitude'] = float(val)
                    except: pass
                elif key == 'catchment area (km)':
                    try: metadata['catchment_area'] = float(val)
                    except: pass
    return metadata


def detect_asset_from_metadata(metadata, filepath):
    """Detect asset_id from GRDC header metadata or filename."""
    # Try station name
    station = metadata.get('station_name', '').lower()
    river = metadata.get('river_name', '').lower()
    
    for keyword, asset_id in STATION_KEYWORDS.items():
        if keyword in station or keyword in river:
            return asset_id
    
    # Try filename
    basename = os.path.basename(filepath).lower()
    for keyword, asset_id in STATION_KEYWORDS.items():
        if keyword in basename:
            return asset_id
    
    return None


def parse_grdc_file(filepath):
    """Parse GRDC Export format (semicolon-delimited).
    
    GRDC format:
      YYYY-MM-DD;--:--;     65.470
      
    Returns list of (date, discharge_m3s, quality_flag) tuples.
    """
    observations = []
    in_data = False
    
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines and headers
            if not line or line.startswith('#'):
                continue
            
            # Check if this is the data header
            if 'YYYY-MM-DD' in line:
                in_data = True
                continue
            
            if not in_data:
                continue
            
            # Parse data line: YYYY-MM-DD;--:--;value
            parts = line.split(';')
            if len(parts) < 3:
                # Try comma or space delimiter
                parts = line.replace(';', ',').split(',')
                if len(parts) < 2:
                    parts = line.split()
            
            if len(parts) < 2:
                continue
            
            try:
                date_str = parts[0].strip()
                value_str = parts[1].strip() if len(parts) > 1 else parts[-1].strip()
                quality = parts[2].strip() if len(parts) > 2 else 'A'
                
                # Parse date
                date = datetime.strptime(date_str[:10], '%Y-%m-%d')
                
                # Parse value
                value = float(value_str)
                
                # Skip missing values
                if value < 0 or abs(value - MISSING_VALUE) < 0.01:
                    continue
                
                observations.append((date, value, quality))
            except (ValueError, IndexError):
                continue
    
    return observations


def ensure_source_id(db, source_authority='GRDC'):
    """Find or create the source_id for GRDC."""
    from sqlalchemy import text
    
    row = db.execute(text(
        "SELECT id FROM aquavision.water_sources WHERE name = :name LIMIT 1"
    ), {'name': source_authority}).fetchone()
    
    if row:
        return row[0]
    
    # Insert new source
    db.execute(text(
        "INSERT INTO aquavision.water_sources (name, description, is_active, created_at) "
        "VALUES (:name, :desc, true, NOW()) RETURNING id"
    ), {'name': source_authority, 'desc': 'Global Runoff Data Centre discharge data'})
    
    result = db.execute(text("SELECT currval(pg_get_serial_sequence('aquavision.water_sources', 'id'))"))
    source_id = result.scalar()
    db.commit()
    print(f"  Created source '{source_authority}' with id={source_id}")
    return source_id


def ingest_grdc_file(filepath, asset_id=None, source_id=None):
    """Ingest a single GRDC file into water_observations.
    
    Returns number of observations inserted.
    """
    from sqlalchemy import text
    from infrastructure.db.engine import SessionLocal
    
    # Parse header
    metadata = parse_grdc_header(filepath)
    if metadata:
        print(f"  Station: {metadata.get('station_name', '?')}, River: {metadata.get('river_name', '?')}")
        print(f"  Country: {metadata.get('country', '?')}, GRDC-No: {metadata.get('grdc_no', '?')}")
    
    # Detect asset_id
    if asset_id is None:
        asset_id = detect_asset_from_metadata(metadata, filepath)
    if asset_id is None:
        print(f"  ERROR: Could not detect asset ID for {filepath}. Use --asset flag.")
        print(f"  Station: {metadata.get('station_name', '?')}")
        return 0
    
    # Parse observations
    observations = parse_grdc_file(filepath)
    if not observations:
        print(f"  WARNING: No valid observations in {filepath}")
        return 0
    
    print(f"  Parsed {len(observations)} observations from {filepath}")
    print(f"  Asset: {asset_id}, Date range: {observations[0][0].date()} to {observations[-1][0].date()}")
    
    db = SessionLocal()
    
    # Get source_id
    if source_id is None:
        source_id = ensure_source_id(db, 'GRDC')
    
    inserted = 0
    skipped = 0
    
    for date, discharge_m3s, quality in observations:
        discharge_cusecs = discharge_m3s * M3S_TO_CUSECS
        
        # Check if observation already exists
        existing = db.execute(text(
            "SELECT id FROM aquavision.water_observations "
            "WHERE asset_id = :aid AND observed_at = :dt AND discharge_cusecs IS NOT NULL"
        ), {"aid": asset_id, "dt": date}).fetchone()
        
        if existing:
            skipped += 1
            continue
        
        db.execute(text(
            "INSERT INTO aquavision.water_observations "
            "(asset_id, source_id, observed_at, discharge_cusecs, unit, data_status, "
            "data_origin, quality_status, source_authority, source_priority, created_at) "
            "VALUES (:aid, :sid, :dt, :dis, 'cusecs', 'OBSERVED_OFFICIAL', "
            "'REAL', :qs, 'GRDC', 1, NOW())"
        ), {
            "aid": asset_id, "sid": source_id, "dt": date,
            "dis": round(discharge_cusecs, 2),
            "qs": "VALID" if quality.strip() in ('A', '') else "PARTIAL"
        })
        inserted += 1
    
    db.commit()
    db.close()
    print(f"  Inserted {inserted} new, skipped {skipped} existing")
    return inserted


def batch_ingest_dir(dirpath, source_id=None):
    """Ingest all GRDC files in a directory."""
    total = 0
    for filename in sorted(os.listdir(dirpath)):
        if filename.endswith(('.txt', '.csv', '.dat')):
            filepath = os.path.join(dirpath, filename)
            print(f"\nProcessing: {filename}")
            count = ingest_grdc_file(filepath, source_id=source_id)
            total += count
    return total


def main():
    parser = argparse.ArgumentParser(description='Ingest GRDC discharge data')
    parser.add_argument('--file', '-f', help='Path to GRDC file')
    parser.add_argument('--dir', '-d', help='Directory containing GRDC files')
    parser.add_argument('--asset', '-a', type=int, help='Asset ID (auto-detected from filename/header)')
    parser.add_argument('--source-id', '-s', type=int, help='Source ID in water_sources table')
    args = parser.parse_args()
    
    if args.file:
        count = ingest_grdc_file(args.file, args.asset, args.source_id)
        print(f"\nTotal: {count} observations inserted")
    elif args.dir:
        count = batch_ingest_dir(args.dir, args.source_id)
        print(f"\nTotal: {count} observations inserted")
    else:
        parser.print_help()
        print("\nStation mapping:")
        for name, aid in sorted(STATION_KEYWORDS.items(), key=lambda x: x[1]):
            print(f"  {name:<12} -> Asset {aid}")
        print("\nUsage:")
        print("  python ingest_grdc.py --file grdc_sukkur.txt --asset 7")
        print("  python ingest_grdc.py --dir ./grdc_data/")


if __name__ == "__main__":
    main()
