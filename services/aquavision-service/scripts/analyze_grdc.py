import os

GRDC_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'grdc')

print('=' * 80)
print('GRDC DATA ANALYSIS FOR IBCP-SCADA')
print('=' * 80)

# Our target assets
TARGET_MAP = {
    'tarbela': 1, 'mangla': 2, 'chashma': 3, 'kalabagh': 4,
    'taunsa': 5, 'guddu': 6, 'sukkur': 7, 'kotri': 8,
    'nowshera': 9, 'marala': 10, 'panjnad': 11,
}

all_stations = []

for fname in sorted(os.listdir(GRDC_DIR)):
    if not fname.endswith('_Q_Day.Cmd.txt'):
        continue
    fpath = os.path.join(GRDC_DIR, fname)
    with open(fpath, 'r', errors='replace') as f:
        lines = f.readlines()

    data_lines = [l.strip() for l in lines if l.strip() and not l.startswith('#') and 'YYYY' not in l]
    
    meta = {}
    for line in lines[:25]:
        line = line.lstrip('#').strip()
        if ':' in line:
            key, val = line.split(':', 1)
            meta[key.strip().lower()] = val.strip()
    
    timerange = ''
    for line in lines[:25]:
        if 'Time series' in line:
            timerange = line.split(':', 1)[1].strip()

    # Get date range from data
    first_date = data_lines[0].split(';')[0].strip() if data_lines else ''
    last_date = data_lines[-1].split(';')[0].strip() if data_lines else ''

    station = {
        'file': fname,
        'grdc_no': meta.get('grdc-no.', ''),
        'station': meta.get('station', ''),
        'river': meta.get('river', ''),
        'country': meta.get('country', ''),
        'lat': meta.get('latitude (dd)', ''),
        'lon': meta.get('longitude (dd)', ''),
        'catchment': meta.get('catchment area (km)', ''),
        'timerange': timerange,
        'first_date': first_date,
        'last_date': last_date,
        'obs': len(data_lines),
    }
    all_stations.append(station)

# Categorize
pk = [s for s in all_stations if s['country'] == 'PK' and s['obs'] > 0]
af = [s for s in all_stations if s['country'] == 'AF' and s['obs'] > 0]
empty = [s for s in all_stations if s['obs'] == 0]

print(f'\nTotal files: {len(all_stations)}')
print(f'With data: {len(all_stations) - len(empty)}')
print(f'Empty (no data): {len(empty)}')

print(f'\n--- PAKISTAN stations with data ({len(pk)}) ---')
for s in pk:
    print(f"  {s['grdc_no']}: {s['river']} @ {s['station']}")
    print(f"    Coords: {s['lat']}, {s['lon']}")
    print(f"    Catchment: {s['catchment']} km2")
    print(f"    Period: {s['first_date']} to {s['last_date']} ({s['obs']} daily obs)")

print(f'\n--- AFGHANISTAN stations with data ({len(af)}) ---')
for s in af:
    print(f"  {s['grdc_no']}: {s['river']} @ {s['station']}")
    print(f"    Coords: {s['lat']}, {s['lon']}")
    print(f"    Catchment: {s['catchment']} km2")
    print(f"    Period: {s['first_date']} to {s['last_date']} ({s['obs']} daily obs)")

print(f'\n--- EMPTY stations ({len(empty)}) ---')
for s in empty:
    print(f"  {s['grdc_no']}: {s['river']} @ {s['station']} [{s['country']}]")

# Map to our assets
print('\n' + '=' * 80)
print('ASSET MAPPING ANALYSIS')
print('=' * 80)

asset_mapping = {
    9: {'name': 'Kabul@Nowshera', 'candidates': []},
    10: {'name': 'Chenab@Marala', 'candidates': []},
    1: {'name': 'Tarbela', 'candidates': []},
    2: {'name': 'Mangla', 'candidates': []},
    3: {'name': 'Chashma', 'candidates': []},
    4: {'name': 'Kalabagh', 'candidates': []},
    5: {'name': 'Taunsa', 'candidates': []},
    6: {'name': 'Guddu', 'candidates': []},
    7: {'name': 'Sukkur', 'candidates': []},
    8: {'name': 'Kotri', 'candidates': []},
    11: {'name': 'Panjnad', 'candidates': []},
}

for s in all_stations:
    river_lower = s['river'].lower()
    station_lower = s['station'].lower()
    
    # Kabul River stations -> Asset 9
    if 'kabul' in river_lower and s['obs'] > 0:
        asset_mapping[9]['candidates'].append(s)
    
    # Jhelum -> could proxy for Mangla (Asset 2)
    if 'jhelum' in river_lower and s['obs'] > 0:
        asset_mapping[2]['candidates'].append(s)
    
    # Chenab -> Asset 10
    if 'chenab' in river_lower and s['obs'] > 0:
        asset_mapping[10]['candidates'].append(s)
    
    # Indus mainstem
    if 'indus' in river_lower:
        if 'attock' in station_lower:
            asset_mapping[4]['candidates'].append(s)  # near Kalabagh
        if 'kotri' in station_lower:
            asset_mapping[8]['candidates'].append(s)

for aid, info in sorted(asset_mapping.items()):
    if info['candidates']:
        print(f"\nAsset {aid} ({info['name']}):")
        for c in info['candidates']:
            print(f"  -> {c['river']} @ {c['station']} [{c['first_date']} to {c['last_date']}] {c['obs']} obs")
    else:
        print(f"\nAsset {aid} ({info['name']}): NO CANDIDATE DATA")
