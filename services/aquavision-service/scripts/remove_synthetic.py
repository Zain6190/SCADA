"""Remove all synthetic observations from local DB and Neon.

Keeps only rows where data_origin = 'REAL'.
Reports how many rows removed per asset.
"""
import sys; sys.path.insert(0, '/app')
from infrastructure.db.engine import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("=" * 70)
print("REMOVING ALL SYNTHETIC DATA")
print("=" * 70)

# Count before
result = db.execute(text("""
    SELECT 
        wa.id, wa.canonical_name,
        COUNT(wo.id) as total,
        COUNT(wo.id) FILTER (WHERE wo.data_origin = 'REAL') as real_count,
        COUNT(wo.id) FILTER (WHERE wo.data_origin = 'SYNTHETIC') as synth_count
    FROM aquavision.water_assets wa
    LEFT JOIN aquavision.water_observations wo ON wo.asset_id = wa.id
    GROUP BY wa.id, wa.canonical_name ORDER BY wa.id
"""))

print(f"\n{'Asset':<22} {'Before':>8} {'REAL':>8} {'SYNTH':>8} {'Removed':>8}")
print("-" * 60)
total_before = 0
total_real = 0
total_synth = 0
for r in result:
    print(f"{r.canonical_name:<22} {r.total:>8} {r.real_count:>8} {r.synth_count:>8} {r.synth_count:>8}")
    total_before += r.total
    total_real += r.real_count
    total_synth += r.synth_count

print("-" * 60)
print(f"{'TOTAL':<22} {total_before:>8} {total_real:>8} {total_synth:>8} {total_synth:>8}")

# Remove synthetic
print(f"\nRemoving {total_synth} synthetic rows...")
db.execute(text("DELETE FROM aquavision.water_observations WHERE data_origin = 'SYNTHETIC'"))
db.commit()

# Also remove SYNTHETIC_HISTORICAL status
result2 = db.execute(text("SELECT COUNT(*) FROM aquavision.water_observations WHERE data_status = 'SYNTHETIC_HISTORICAL'"))
synth_hist = result2.scalar()
if synth_hist > 0:
    print(f"Also removing {synth_hist} SYNTHETIC_HISTORICAL rows...")
    db.execute(text("DELETE FROM aquavision.water_observations WHERE data_status = 'SYNTHETIC_HISTORICAL'"))
    db.commit()

# Count after
print("\n" + "=" * 70)
print("AFTER REMOVAL")
print("=" * 70)
result3 = db.execute(text("""
    SELECT 
        wa.id, wa.canonical_name,
        COUNT(wo.id) as remaining,
        MIN(wo.observed_at) as earliest,
        MAX(wo.observed_at) as latest
    FROM aquavision.water_assets wa
    LEFT JOIN aquavision.water_observations wo ON wo.asset_id = wa.id
    GROUP BY wa.id, wa.canonical_name ORDER BY wa.id
"""))

print(f"\n{'Asset':<22} {'Remaining':>10} {'Date Range'}")
print("-" * 70)
for r in result3:
    dates = f"{r.earliest} to {r.latest}" if r.earliest else "EMPTY"
    print(f"{r.canonical_name:<22} {r.remaining:>10} {dates}")

db.close()
print("\nDone. All synthetic data removed.")
