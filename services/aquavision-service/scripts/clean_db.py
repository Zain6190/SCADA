"""Nuclear clean: delete all alerts/audit/forecasts, then remove non-REAL observations."""
import sys; sys.path.insert(0, '/app')
from infrastructure.db.engine import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Step 1: Wipe all dependent tables
print("Step 1: Clearing alerts, audit logs, forecasts...")
db.execute(text("DELETE FROM aquavision.water_alert_audit_log"))
db.execute(text("DELETE FROM aquavision.water_operational_alerts"))
db.execute(text("DELETE FROM aquavision.water_asset_forecasts"))
db.commit()
print("  Done.")

# Step 2: Remove non-REAL observations
print("Step 2: Removing non-REAL observations...")
r = db.execute(text("SELECT COUNT(*) FROM aquavision.water_observations WHERE data_origin != 'REAL'"))
non_real = r.scalar()
db.execute(text("DELETE FROM aquavision.water_observations WHERE data_origin != 'REAL'"))
db.commit()
print(f"  Removed {non_real} non-REAL rows.")

# Step 3: Remove weather-only rows
print("Step 3: Removing weather-only rows (no flow data)...")
r2 = db.execute(text("""
    SELECT COUNT(*) FROM aquavision.water_observations 
    WHERE water_level_ft IS NULL AND inflow_cusecs IS NULL 
    AND outflow_cusecs IS NULL AND discharge_cusecs IS NULL
"""))
weather_only = r2.scalar()
db.execute(text("""
    DELETE FROM aquavision.water_observations 
    WHERE water_level_ft IS NULL AND inflow_cusecs IS NULL 
    AND outflow_cusecs IS NULL AND discharge_cusecs IS NULL
"""))
db.commit()
print(f"  Removed {weather_only} weather-only rows.")

# Step 4: Report
print("\nFINAL STATE:")
r3 = db.execute(text("""
    SELECT wa.id, wa.canonical_name, COUNT(wo.id) as cnt,
           MIN(wo.observed_at) as earliest, MAX(wo.observed_at) as latest
    FROM aquavision.water_assets wa
    LEFT JOIN aquavision.water_observations wo ON wo.asset_id = wa.id
    WHERE wa.is_active = true
    GROUP BY wa.id, wa.canonical_name ORDER BY wa.id
"""))
for row in r3:
    dates = f"{row.earliest} to {row.latest}" if row.earliest else "EMPTY"
    print(f"  {row.canonical_name}: {row.cnt} obs ({dates})")

db.close()
print("\nDone.")
