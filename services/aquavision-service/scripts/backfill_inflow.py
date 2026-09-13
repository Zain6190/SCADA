"""
Backfill missing inflow_cusecs in water_observations using physics.

FFD bulletin provides discharge (downstream) but not inflow (upstream).
This script estimates inflow using:
1. Mass balance for reservoirs: inflow = outflow + Δstorage/Δt
2. Steady-state for barrages: inflow ≈ discharge
3. Upstream proxy with travel time adjustment

Run after FFD ingestion or on schedule.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger("aquavision.backfill_inflow")


def backfill_missing_inflow(db_session, asset_id: int = None, dry_run: bool = False) -> dict:
    """Estimate and fill missing inflow_cusecs for observations.
    
    Args:
        db_session: SQLAlchemy session
        asset_id: Specific asset to backfill (None = all active)
        dry_run: If True, don't write to DB
    
    Returns:
        {"backfilled": int, "skipped": int, "errors": int}
    """
    from scripts.physics_inflow import (
        estimate_inflow_physics,
        RESERVOIRS,
        UPSTREAM_MAP,
    )
    
    # Get assets to process
    if asset_id:
        assets = db_session.execute(
            text("SELECT id, canonical_name FROM aquavision.water_assets WHERE id = :id AND is_active = true"),
            {"id": asset_id},
        ).mappings().all()
    else:
        assets = db_session.execute(
            text("SELECT id, canonical_name FROM aquavision.water_assets WHERE is_active = true ORDER BY id")
        ).mappings().all()
    
    results = {"backfilled": 0, "skipped": 0, "errors": 0}
    
    for asset in assets:
        aid = asset["id"]
        name = asset["canonical_name"]
        
        # Get observations missing inflow
        obs_rows = db_session.execute(
            text("""
                SELECT id, observed_at, water_level_ft, outflow_cusecs, 
                       discharge_cusecs, inflow_cusecs
                FROM aquavision.water_observations
                WHERE asset_id = :asset_id
                  AND inflow_cusecs IS NULL
                  AND outflow_cusecs IS NOT NULL
                ORDER BY observed_at ASC
            """),
            {"asset_id": aid},
        ).mappings().all()
        
        if not obs_rows:
            continue
        
        logger.info(f"Asset {aid} ({name}): {len(obs_rows)} observations missing inflow")
        
        for i, obs in enumerate(obs_rows):
            try:
                obs_id = obs["id"]
                level = obs["water_level_ft"]
                outflow = obs["outflow_cusecs"]
                discharge = obs["discharge_cusecs"]
                
                if outflow is None and discharge is None:
                    results["skipped"] += 1
                    continue
                
                # Get previous observation for delta storage
                prev = db_session.execute(
                    text("""
                        SELECT water_level_ft, outflow_cusecs
                        FROM aquavision.water_observations
                        WHERE asset_id = :asset_id AND observed_at < :observed_at
                        ORDER BY observed_at DESC LIMIT 1
                    """),
                    {"asset_id": aid, "observed_at": obs["observed_at"]},
                ).mappings().first()
                
                estimated_inflow = None
                
                if aid in RESERVOIRS:
                    # Reservoir: mass balance
                    if level is not None and outflow is not None and prev:
                        prev_level = prev["water_level_ft"]
                        prev_outflow = prev["outflow_cusecs"]
                        if prev_level is not None and prev_outflow is not None:
                            # Estimate dt_hours from observation timestamps
                            estimated_inflow = estimate_inflow_physics(
                                asset_id=aid,
                                level_ft=float(level),
                                outflow_cusecs=float(outflow),
                                prev_level_ft=float(prev_level),
                                prev_outflow_cusecs=float(prev_outflow),
                                dt_hours=24.0,
                            )
                else:
                    # Barrage: steady-state (inflow ≈ discharge)
                    if discharge is not None and discharge > 0:
                        estimated_inflow = float(discharge)
                    elif outflow is not None and outflow > 0:
                        estimated_inflow = float(outflow)
                
                if estimated_inflow is not None and estimated_inflow > 0:
                    if not dry_run:
                        db_session.execute(
                            text("""
                                UPDATE aquavision.water_observations
                                SET inflow_cusecs = :inflow,
                                    data_status = CASE 
                                        WHEN data_status IS NULL THEN 'ESTIMATED_PHYSICS'
                                        WHEN data_status NOT LIKE '%ESTIMATED%' THEN data_status || ',ESTIMATED_PHYSICS'
                                        ELSE data_status
                                    END
                                WHERE id = :id
                            """),
                            {"inflow": estimated_inflow, "id": obs_id},
                        )
                    results["backfilled"] += 1
                    logger.debug(f"  Obs {obs_id}: estimated inflow = {estimated_inflow:.0f} cusecs")
                else:
                    results["skipped"] += 1
            
            except Exception as e:
                logger.warning(f"  Error processing obs {obs.get('id')}: {e}")
                results["errors"] += 1
        
        logger.info(f"Asset {aid}: backfilled={results['backfilled']}, skipped={results['skipped']}")
    
    if not dry_run:
        db_session.commit()
    
    return results


def backfill_all_assets(db_session=None, dry_run: bool = False) -> dict:
    """Backfill missing inflow for all active assets."""
    close_session = False
    if db_session is None:
        from infrastructure.db.engine import SessionLocal
        db_session = SessionLocal()
        close_session = True
    
    try:
        results = backfill_missing_inflow(db_session, dry_run=dry_run)
        logger.info(f"Backfill complete: {results}")
        return results
    finally:
        if close_session:
            db_session.close()


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    dry_run = "--dry-run" in sys.argv
    results = backfill_all_assets(dry_run=dry_run)
    print(f"\nBackfill results: {results}")
