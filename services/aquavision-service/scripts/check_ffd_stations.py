import re
from pathlib import Path

html = Path("/app/infrastructure/ingestion/raw_archive/ffl/FFD_18-08-2026.html").read_text()
stations = re.findall(r'data-ffd-headroom="([^"]+)"', html)
print(f"{len(stations)} stations found:")
for s in stations:
    print(f"  {s}")

# Also check if "Nowshera" or "Kabul" appears anywhere in the HTML
for keyword in ["Nowshera", "Kabul", "nowshera", "kabul"]:
    if keyword in html:
        print(f"\nFound '{keyword}' in HTML text (not as data-ffd-headroom attribute)")
    else:
        print(f"\n'{keyword}' NOT found anywhere in HTML")
