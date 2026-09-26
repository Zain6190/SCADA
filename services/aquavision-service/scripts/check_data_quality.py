import sys; sys.path.insert(0, '/app')
from infrastructure.db.engine import SessionLocal
from sqlalchemy import text

db = SessionLocal()
result = db.execute(text("""
    SELECT 
        wa.id,
        wa.canonical_name,
        COUNT(wo.id) as total,
        COUNT(wo.id) FILTER (WHERE wo.data_origin = 'REAL') as real_obs,
        COUNT(wo.id) FILTER (WHERE wo.data_origin = 'SYNTHETIC') as synth_obs,
        MIN(wo.observed_at) as earliest,
        MAX(wo.observed_at) as latest
    FROM aquavision.water_assets wa
    LEFT JOIN aquavision.water_observations wo ON wo.asset_id = wa.id
    WHERE wa.is_active = true
    GROUP BY wa.id, wa.canonical_name
    ORDER BY wa.id
"""))

print(f"{'Asset':<22} {'Total':>7} {'REAL':>7} {'SYNTH':>7} {'REAL%':>7} {'Date Range'}")
print("-" * 85)
for r in result:
    real_pct = (r.real_obs / r.total * 100) if r.total > 0 else 0
    dates = f"{r.earliest} to {r.latest}" if r.earliest else "N/A"
    print(f"{r.canonical_name:<22} {r.total:>7} {r.real_obs:>7} {r.synth_obs:>7} {real_pct:>6.1f}% {dates}")

db.close()
