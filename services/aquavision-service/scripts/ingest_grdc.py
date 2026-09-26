"""
ingest_grdc.py - Ingest the GRDC archives in data/raw/grdc.

Stores into aquavision.grdc_stations / aquavision.grdc_observations (migration
007), NEVER into water_observations: of the 41 stations on disk almost none is
the gauge of an asset (the Kabul entries are upstream tributaries, not the
Nowshera gauge), and the intended uses - routing validation against
physics-routed reaches and long-history upstream features - need station
identity preserved.

GRDC export format (identical for *_Q_Day.Cmd.txt and *_Q_Month.txt):
  # header metadata lines (GRDC-No., River, Station, Country, Lat, Lon, ...)
      YYYY-MM-DD;hh:mm;value;flag;...
  missing values: -999.000
  monthly files are dated day 01 by convention ("Date (DD=00)" header note)

The 8 mainstem gauges with EMPTY daily files (Indus @ Attock/Kotri, Chenab @
Panjnad, ...) have populated monthly series - hence freq 'D'/'M' in the key.

Idempotent: re-running upserts metadata and updates values.

Run inside the api container:
    docker exec -w /app ibcp-api python -m scripts.ingest_grdc
"""
import os
from datetime import datetime

MISSING_VALUE = -999.0
DEFAULT_GRDC_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'grdc')
INSERT_CHUNK = 1000


def _header_value(key, val, meta):
    """Map one header key (already lowercased) to metadata."""
    if key == 'grdc-no.':
        meta['grdc_no'] = val
    elif key == 'river':
        meta['river'] = val
    elif key == 'station':
        meta['station'] = val
    elif key == 'country':
        meta['country'] = val
    elif key == 'latitude (dd)':
        meta['latitude'] = _to_float(val)
    elif key == 'longitude (dd)':
        meta['longitude'] = _to_float(val)
    elif key.startswith('catchment'):
        # key is "catchment area (km<sup>2</sup>)" - the superscript byte varies with encoding
        meta['catchment_km2'] = _to_float(val)
    elif key.startswith('altitude'):
        alt = _to_float(val)
        meta['altitude_m'] = alt if alt is not None and alt > -900 else None
    elif key == 'next downstream station':
        meta['next_downstream_grdc_no'] = val if val and val != '-' else None
    elif key.startswith('owner of original data'):
        meta['owner'] = val
    elif key == 'file generation date':
        try:
            meta['file_generated'] = datetime.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            pass


def _to_float(val):
    try:
        f = float(val)
        return None if abs(f - MISSING_VALUE) < 0.01 else f
    except (TypeError, ValueError):
        return None


def parse_header(lines):
    """Parse GRDC '#' header lines into a metadata dict."""
    meta = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not line.startswith('#'):
            break
        line = line.lstrip('#').strip()
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        _header_value(key.strip().lower(), val.strip(), meta)
    return meta


def parse_series(lines):
    """Parse data lines into [(date, discharge_m3s), ...].

    Format: YYYY-MM-DD;hh:mm;value;...  - missing (-999) and unparseable
    lines are skipped. No table-header gate: any non-comment line that
    parses as date;time;value is data.
    """
    observations = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(';')
        if len(parts) < 3:
            continue
        try:
            date = datetime.strptime(parts[0].strip()[:10], '%Y-%m-%d').date()
            value = float(parts[2].strip())
        except ValueError:
            continue
        if value < 0:
            continue
        observations.append((date, value))
    return observations


def read_file(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.readlines()


def ensure_grdc_source(db):
    from sqlalchemy import text

    row = db.execute(text(
        "SELECT id FROM aquavision.water_sources WHERE authority = 'GRDC'"
    )).scalar()
    if row:
        return row
    db.execute(text(
        "INSERT INTO aquavision.water_sources "
        "(authority, source_type, source_url, update_frequency, description) "
        "VALUES ('GRDC', 'CSV', 'https://grdc.bafg.de', 'ONE_TIME', "
        "'Global Runoff Data Centre discharge archives') "
        "ON CONFLICT (authority) DO NOTHING"
    ))
    db.commit()
    return db.execute(text(
        "SELECT id FROM aquavision.water_sources WHERE authority = 'GRDC'"
    )).scalar()


def _upsert_station(db, meta, periods):
    from sqlalchemy import text

    db.execute(text(
        "INSERT INTO aquavision.grdc_stations "
        "(grdc_no, river, station, country, latitude, longitude, catchment_km2, "
        " altitude_m, next_downstream_grdc_no, owner, file_generated, "
        " period_daily_start, period_daily_end, period_monthly_start, period_monthly_end) "
        "VALUES (:grdc_no, :river, :station, :country, :latitude, :longitude, "
        " :catchment_km2, :altitude_m, :next_downstream_grdc_no, :owner, :file_generated, "
        " :d_start, :d_end, :m_start, :m_end) "
        "ON CONFLICT (grdc_no) DO UPDATE SET "
        " river = EXCLUDED.river, station = EXCLUDED.station, country = EXCLUDED.country, "
        " latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, "
        " catchment_km2 = EXCLUDED.catchment_km2, altitude_m = EXCLUDED.altitude_m, "
        " next_downstream_grdc_no = EXCLUDED.next_downstream_grdc_no, "
        " owner = EXCLUDED.owner, file_generated = EXCLUDED.file_generated, "
        " period_daily_start = EXCLUDED.period_daily_start, "
        " period_daily_end = EXCLUDED.period_daily_end, "
        " period_monthly_start = EXCLUDED.period_monthly_start, "
        " period_monthly_end = EXCLUDED.period_monthly_end, "
        " updated_at = now()"
    ), {
        'grdc_no': meta.get('grdc_no'),
        'river': meta.get('river', ''),
        'station': meta.get('station', ''),
        'country': meta.get('country'),
        'latitude': meta.get('latitude'),
        'longitude': meta.get('longitude'),
        'catchment_km2': meta.get('catchment_km2'),
        'altitude_m': meta.get('altitude_m'),
        'next_downstream_grdc_no': meta.get('next_downstream_grdc_no'),
        'owner': meta.get('owner'),
        'file_generated': meta.get('file_generated'),
        'd_start': periods.get('D', (None, None))[0],
        'd_end': periods.get('D', (None, None))[1],
        'm_start': periods.get('M', (None, None))[0],
        'm_end': periods.get('M', (None, None))[1],
    })


def _upsert_observations(db, grdc_no, freq, obs, source_id):
    from sqlalchemy import text

    total = 0
    for i in range(0, len(obs), INSERT_CHUNK):
        chunk = obs[i:i + INSERT_CHUNK]
        placeholders = ', '.join(
            f"(:g{i}_{j}, :d{i}_{j}, '{freq}', :v{i}_{j}, :src)"
            for j in range(len(chunk))
        )
        params = {'src': source_id}
        for j, (d, v) in enumerate(chunk):
            params[f'g{i}_{j}'] = grdc_no
            params[f'd{i}_{j}'] = d
            params[f'v{i}_{j}'] = v
        result = db.execute(text(
            "INSERT INTO aquavision.grdc_observations "
            "(grdc_no, obs_date, freq, discharge_m3s, source_id) "
            f"VALUES {placeholders} "
            "ON CONFLICT (grdc_no, obs_date, freq) "
            "DO UPDATE SET discharge_m3s = EXCLUDED.discharge_m3s"
        ), params)
        total += result.rowcount
    return total


def ingest(grdc_dir=None):
    """Ingest every GRDC export file in grdc_dir. Idempotent.

    Returns dict stats: stations, daily_rows, monthly_rows, empty_files.
    """
    from sqlalchemy import text
    from infrastructure.db.engine import SessionLocal

    grdc_dir = grdc_dir or DEFAULT_GRDC_DIR
    db = SessionLocal()
    stats = {'stations': 0, 'daily_rows': 0, 'monthly_rows': 0, 'empty_files': 0,
             'files': 0}
    try:
        source_id = ensure_grdc_source(db)

        # pass 1: parse everything (small: ~100k rows) - a station's row must
        # exist before its observations (FK), and its period columns cover both files
        seen = {}
        for fname in sorted(os.listdir(grdc_dir)):
            if fname.endswith('_Q_Day.Cmd.txt'):
                freq = 'D'
            elif fname.endswith('_Q_Month.txt'):
                freq = 'M'
            else:
                continue
            lines = read_file(os.path.join(grdc_dir, fname))
            meta = parse_header(lines)
            if not meta.get('grdc_no'):
                meta['grdc_no'] = fname[:7]
            obs = parse_series(lines)
            stats['files'] += 1
            if not obs:
                stats['empty_files'] += 1
            station = seen.setdefault(meta['grdc_no'], {'meta': meta, 'series': {}})
            for k, v in meta.items():
                if v:
                    station['meta'][k] = v
            if obs:
                station['series'][freq] = obs
                if freq == 'D':
                    stats['daily_rows'] += len(obs)
                else:
                    stats['monthly_rows'] += len(obs)

        # pass 2: station row first, then its observations
        for grdc_no, station in sorted(seen.items()):
            periods = {f: (s[0][0], s[-1][0]) for f, s in station['series'].items()}
            _upsert_station(db, station['meta'], periods)
            stats['stations'] += 1
            for freq, obs in station['series'].items():
                _upsert_observations(db, grdc_no, freq, obs, source_id)
            db.commit()
    finally:
        db.close()

    print(
        f"GRDC ingest: {stats['stations']} stations, "
        f"{stats['daily_rows']} daily + {stats['monthly_rows']} monthly rows "
        f"from {stats['files']} files ({stats['empty_files']} empty)"
    )
    return stats


def main():
    ingest()


if __name__ == '__main__':
    main()
