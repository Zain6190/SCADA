from infrastructure.db.engine import get_session
from ml.models.prediction_v2 import AquaVisionPredictionModel
session = next(get_session())
model = AquaVisionPredictionModel(session=session)

obs = model._get_current_observation(7)
upstream = model._get_upstream_discharge(7)
trend = model._get_discharge_trend(7)

print(f"Current discharge: {obs.get('discharge_cusecs')}")
print(f"Upstream: {upstream}")
print(f"Trend: {trend}")

if upstream and upstream > 0:
    if trend is not None:
        cd = obs.get("discharge_cusecs") or 0
        print(f"Current discharge value: {cd}")
        if cd > 0:
            for lt in [3,7,14]:
                damp = {3: 0.8, 7: 0.4, 14: 0.2}.get(lt, 0.3)
                eff = trend * damp
                tc = max(-40, min(40, eff * lt))
                pred = upstream * (1 + tc/100)
                print(f"  {lt}-day: {pred:.0f} cusecs = {pred*0.0283168:.0f} m3/s (change={tc:.1f}%)")
        else:
            print("current_discharge <= 0")
    else:
        print("trend is None")
session.close()
