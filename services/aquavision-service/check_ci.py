import requests, json

for aid in [9, 10, 2, 1, 5]:
    r = requests.get(f"http://127.0.0.1:8100/water/v2/predict/{aid}")
    d = r.json()
    name = d["asset_name"]
    print(f"\n{name} (ID={aid}):")
    for lk, lv in d["predictions"].items():
        dc = lv["discharge"]
        val = dc["value_m3s"]
        lo = dc["confidence_lower_m3s"]
        hi = dc["confidence_upper_m3s"]
        ci_width = hi - lo
        ci_pct = (ci_width / val * 100) if val > 0 else 0
        print(f"  {lk}: {val:>8.1f} m3/s  CI=[{lo:>8.1f}, {hi:>8.1f}]  width={ci_width:.1f} ({ci_pct:.0f}%)")
