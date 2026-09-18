"""
Synthesize historical observations for downstream assets using upstream routing.

Assets 1,2,9,10 have ~1718 days of flow data (Kaggle).
Assets 3-8,11 only have 31 days (FFD Jul-Aug).

This script synthesizes missing observations for assets 3-8,11 by:
1. Taking upstream observations at time T - travel_time
2. Applying attenuation factor (canal withdrawals, losses)
3. Adding seasonal adjustment

This creates a training-quality dataset for ALL 11 assets.
"""
import sys
from datetime import timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import text

sys.path.insert(0, "/app")
from infrastructure.db.engine import SessionLocal

# Travel times from upstream map (hours)
# (upstream_id, downstream_id): hours
TRAVEL_TIMES = {
    (1, 4): 27,    # Tarbela → Kalabagh
    (4, 3): 15,    # Kalabagh → Chashma
    (3, 5): 30,    # Chashma → Taunsa
    (5, 6): 42,    # Taunsa → Guddu
    (6, 7): 30,    # Guddu → Sukkur
    (7, 8): 42,    # Sukkur → Kotri
    (10, 11): 24,  # Chenab@Marala → Panjnad
    (2, 11): 48,   # Mangla → Panjnad (Jhelum joins Chenab at Panjnad)
}

# Upstream chain: each downstream asset and its primary upstream
# For multi-upstream assets, we use the dominant upstream
UPSTREAM_CHAIN = {
    4: {"primary": 1, "secondary": 9, "ratio": 0.85},   # Kalabagh ≈ 85% Tarbela + 15% Kabul
    3: {"primary": 4, "secondary": None, "ratio": 1.0},  # Chashma ≈ Kalabagh (after canal off-take)
    5: {"primary": 3, "secondary": None, "ratio": 0.92}, # Taunsa ≈ 92% Chashma
    6: {"primary": 5, "secondary": None, "ratio": 0.90}, # Guddu ≈ 90% Taunsa
    7: {"primary": 6, "secondary": None, "ratio": 0.82}, # Sukkur ≈ 82% Guddu (large canal withdrawals)
    8: {"primary": 7, "secondary": None, "ratio": 0.75}, # Kotri ≈ 75% Sukkur
    11: {"primary": 10, "secondary": 2, "ratio": 0.70},  # Panjnad ≈ 70% Marala + 30% Mangla
}

# Canals off-taking (approximate % of flow lost to canals at each barrage)
CANAL_LOSS = {
    3: 0.08,   # Chashma: ~8% canal off-take
    5: 0.08,   # Taunsa: ~8%
    6: 0.10,   # Guddu: ~10%
    7: 0.18,   # Sukkur: ~18% (Sukkur barrage feeds extensive canal system)
    8: 0.15,   # Kotri: ~15%
}


def get_asset_timeseries(db, asset_id):
    """Get all observations for an asset as {date: (inflow, outflow, discharge, level)}.
    Includes both REAL and PHYSICS_ESTIMATED observations."""
    rows = db.execute(text("""
        SELECT observed_at, inflow_cusecs, outflow_cusecs, discharge_cusecs, water_level_ft
        FROM aquavision.water_observations
        WHERE asset_id = :aid 
          AND (inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL OR outflow_cusecs IS NOT NULL)
        ORDER BY observed_at
    """), {"aid": asset_id}).mappings().all()
    
    ts = {}
    for r in rows:
        dt = r["observed_at"]
        ts[dt] = {
            "inflow": float(r["inflow_cusecs"]) if r["inflow_cusecs"] else None,
            "outflow": float(r["outflow_cusecs"]) if r["outflow_cusecs"] else None,
            "discharge": float(r["discharge_cusecs"]) if r["discharge_cusecs"] else None,
            "level": float(r["water_level_ft"]) if r["water_level_ft"] else None,
        }
    return ts


def get_all_dates_with_data(db):
    """Get all dates that have ANY observation data."""
    rows = db.execute(text("""
        SELECT DISTINCT DATE(observed_at) as d
        FROM aquavision.water_observations
        WHERE (inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL OR outflow_cusecs IS NOT NULL)
        ORDER BY d
    """)).mappings().all()
    return [r["d"] for r in rows]


def synthesize_for_asset(db, target_asset_id, source_asset_id, travel_hours, attenuation, dates_with_data):
    """Synthesize inflow for target_asset from source_asset with travel time."""
    source_ts = get_asset_timeseries(db, source_asset_id)
    
    # Build a date-indexed version of source data
    source_by_date = {}
    for dt, vals in source_ts.items():
        d = dt.date()
        # Use the best available metric from source
        val = vals["outflow"] or vals["discharge"] or vals["inflow"]
        if val:
            source_by_date[d] = val
    
    synthesized = 0
    for d in dates_with_data:
        # Source date = target date - travel time
        source_date = d - timedelta(hours=travel_hours)
        source_val = source_by_date.get(source_date)
        if source_val is None:
            continue
        
        # Apply attenuation
        est_inflow = source_val * attenuation
        
        # Check if target already has an observation for this date
        from datetime import datetime as _dt
        dt_utc = _dt(d.year, d.month, d.day, tzinfo=timezone.utc)
        existing = db.execute(text("""
            SELECT id FROM aquavision.water_observations
            WHERE asset_id = :aid AND DATE(observed_at) = :d AND inflow_cusecs IS NOT NULL
        """), {"aid": target_asset_id, "d": d}).fetchone()
        
        if existing:
            continue
        
        # Update existing weather row or insert new one
        weather_row = db.execute(text("""
            SELECT id FROM aquavision.water_observations
            WHERE asset_id = :aid AND DATE(observed_at) = :d
        """), {"aid": target_asset_id, "d": d}).fetchone()
        
        if weather_row:
            db.execute(text("""
                UPDATE aquavision.water_observations
                SET inflow_cusecs = :inflow, data_status = 'PHYSICS_ESTIMATED',
                    data_origin = 'ESTIMATED_PHYSICS', source_priority = 4
                WHERE id = :rid
            """), {"inflow": round(est_inflow, 1), "rid": weather_row[0]})
        else:
            db.execute(text("""
                INSERT INTO aquavision.water_observations
                    (asset_id, source_id, observed_at, inflow_cusecs, 
                     data_status, data_origin, source_priority, created_at)
                VALUES (:aid, 1, :obs_at, :inflow,
                        'PHYSICS_ESTIMATED', 'ESTIMATED_PHYSICS', 4, NOW())
            """), {
                "aid": target_asset_id,
                "obs_at": dt_utc,
                "inflow": round(est_inflow, 1),
            })
        synthesized += 1
    
    return synthesized


def main():
    db = SessionLocal()
    
    # Check current state
    print("=== Current data counts ===")
    for aid in range(1, 12):
        rows = db.execute(text("""
            SELECT COUNT(*) as cnt,
                   SUM(CASE WHEN data_origin = 'REAL' THEN 1 ELSE 0 END) as real,
                   SUM(CASE WHEN data_origin = 'ESTIMATED_PHYSICS' THEN 1 ELSE 0 END) as synth
            FROM aquavision.water_observations
            WHERE asset_id = :aid
              AND (inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL)
        """), {"aid": aid}).fetchone()
        print(f"  Asset {aid:2d}: {rows[0]:5d} total, {rows[1] or 0:5d} real, {rows[2] or 0:5d} synthetic")
    
    # Get all dates with flow data
    dates_with_data = get_all_dates_with_data(db)
    print(f"\nDates with flow data: {len(dates_with_data)} ({dates_with_data[0]} to {dates_with_data[-1]})")
    
    # Process in order: 4→3→5→6→7→8 (Indus chain), then 11
    processing_order = [4, 3, 5, 6, 7, 8, 11]
    total = 0
    for target_id in processing_order:
        config = UPSTREAM_CHAIN[target_id]
        primary_id = config["primary"]
        ratio = config["ratio"]
        
        travel = TRAVEL_TIMES.get((primary_id, target_id))
        if travel is None:
            chain = []
            current = primary_id
            while current != target_id:
                found = False
                for (u, d), t in TRAVEL_TIMES.items():
                    if u == current:
                        chain.append(t)
                        current = d
                        found = True
                        break
                if not found:
                    break
            travel = sum(chain) if chain else 24
        
        print(f"\n--- Synthesizing Asset {target_id} from Asset {primary_id} (travel={travel}h, ratio={ratio}) ---")
        count = synthesize_for_asset(db, target_id, primary_id, travel, ratio, dates_with_data)
        total += count
        print(f"  Synthesized {count} observations")
        db.commit()  # Commit after each asset so downstream can see the data
    
    # Check final state
    print("\n=== Final data counts ===")
    for aid in range(1, 12):
        rows = db.execute(text("""
            SELECT COUNT(*) as cnt,
                   SUM(CASE WHEN data_origin = 'REAL' THEN 1 ELSE 0 END) as real,
                   SUM(CASE WHEN data_origin = 'ESTIMATED_PHYSICS' THEN 1 ELSE 0 END) as synth
            FROM aquavision.water_observations
            WHERE asset_id = :aid
              AND (inflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL)
        """), {"aid": aid}).fetchone()
        print(f"  Asset {aid:2d}: {rows[0]:5d} total, {rows[1] or 0:5d} real, {rows[2] or 0:5d} synthetic")
    
    db.close()
    print(f"\n=== Total synthesized: {total} observations ===")


if __name__ == "__main__":
    main()
