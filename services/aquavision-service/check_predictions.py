import json, glob, os

temp = os.environ.get("TEMP", "/tmp")
for name, f in [("Guddu", "g6"), ("Sukkur", "s6"), ("Taunsa", "t6"), ("Kotri", "k6")]:
    path = os.path.join(temp, f"{f}.json")
    d = json.load(open(path))
    method = d["model_metadata"]["prediction_method"]
    print(f"\n=== {name} ({method}) ===")
    for k, v in d["predictions"].items():
        dc = v["discharge"]
        ws = v["water_stress"]
        print(f"  {k}: {dc['value_m3s']:,.0f} m3/s  CI:[{dc['confidence_lower_m3s']:,.0f}-{dc['confidence_upper_m3s']:,.0f}]  trend={ws['trend']:+d}%")
