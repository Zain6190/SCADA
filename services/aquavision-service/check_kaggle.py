import csv
with open('data/raw/real/kaggle/pakistans_rivers_flow.csv', 'r') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    print(f'Total rows: {len(rows)}')
    dates = [r['Date'] for r in rows]
    print(f'First 5 dates: {dates[:5]}')
    print(f'Last 5 dates: {dates[-5:]}')
    # Show date pattern
    from collections import Counter
    months = Counter()
    for d in dates:
        parts = d.split('-')
        if len(parts) == 2:
            months[parts[1]] += 1
    for m, c in sorted(months.items(), key=lambda x: -x[1]):
        print(f'  {m}: {c} rows')
