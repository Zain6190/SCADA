# infrastructure/ingestion/historical_backfill.py
# Generate realistic historical observations for ML training.
# Uses seasonal patterns per asset type with random variation.
# This is synthetic data for development — real data comes from IRSA PDFs.
import random
import math
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterAsset, WaterObservation


# ─── Seasonal patterns per asset type (Jul-Dec) ────────────────────────────
# Values are monthly medians based on Indus Basin hydrology.
# Format: {asset_type: {month: {field: (mean, stddev)}}}

SEASONAL = {
    "reservoir": {
        # Tarbela, Mangla
        7: {"water_level_ft": (1545, 15), "inflow_cusecs": (250000, 40000), "outflow_cusecs": (240000, 35000)},
        8: {"water_level_ft": (1548, 12), "inflow_cusecs": (280000, 50000), "outflow_cusecs": (270000, 45000)},
        9: {"water_level_ft": (1550, 10), "inflow_cusecs": (200000, 35000), "outflow_cusecs": (195000, 30000)},
        10: {"water_level_ft": (1552, 8), "inflow_cusecs": (120000, 25000), "outflow_cusecs": (118000, 22000)},
        11: {"water_level_ft": (1550, 6), "inflow_cusecs": (70000, 15000), "outflow_cusecs": (68000, 14000)},
        12: {"water_level_ft": (1547, 5), "inflow_cusecs": (40000, 10000), "outflow_cusecs": (39000, 9000)},
    },
    "barrage": {
        # Chashma, Guddu, Sukkur, Kotri, Taunsa
        7: {"inflow_cusecs": (280000, 50000), "outflow_cusecs": (260000, 45000)},
        8: {"inflow_cusecs": (320000, 60000), "outflow_cusecs": (300000, 55000)},
        9: {"inflow_cusecs": (220000, 40000), "outflow_cusecs": (210000, 38000)},
        10: {"inflow_cusecs": (140000, 30000), "outflow_cusecs": (135000, 28000)},
        11: {"inflow_cusecs": (80000, 18000), "outflow_cusecs": (78000, 17000)},
        12: {"inflow_cusecs": (45000, 12000), "outflow_cusecs": (44000, 11000)},
    },
    "river_station": {
        # Kalabagh, Panjnad, Kabul@Nowshera
        7: {"inflow_cusecs": (280000, 55000), "discharge_cusecs": (270000, 50000)},
        8: {"inflow_cusecs": (320000, 65000), "discharge_cusecs": (310000, 60000)},
        9: {"inflow_cusecs": (210000, 45000), "discharge_cusecs": (205000, 42000)},
        10: {"inflow_cusecs": (130000, 30000), "discharge_cusecs": (127000, 28000)},
        11: {"inflow_cusecs": (75000, 18000), "discharge_cusecs": (73000, 17000)},
        12: {"inflow_cusecs": (40000, 10000), "discharge_cusecs": (39000, 9500)},
    },
}

# Kabul @ Nowshera has different patterns (higher discharge, lower inflow)
KABUL_OVERRIDE = {
    7: {"discharge_cusecs": (85000, 20000)},
    8: {"discharge_cusecs": (95000, 25000)},
    9: {"discharge_cusecs": (60000, 15000)},
    10: {"discharge_cusecs": (35000, 10000)},
    11: {"discharge_cusecs": (20000, 6000)},
    12: {"discharge_cusecs": (12000, 4000)},
}


def _gauss(mu: float, sigma: float) -> float:
    """Generate a normally-distributed value, clamped to non-negative."""
    return max(0, random.gauss(mu, sigma))


def _add_trend(value: float, day_offset: int, period_days: int = 90) -> float:
    """Add a slow sinusoidal trend to simulate seasonal variation."""
    trend = math.sin(2 * math.pi * day_offset / period_days) * 0.05
    return value * (1 + trend)


def generate_historical_observations(
    db: Session,
    days: int = 90,
    start_date: datetime = None,
) -> int:
    """Generate realistic historical observations for all active assets.
    
    Args:
        db: Database session
        days: Number of days of history to generate
        start_date: End date (defaults to today)
    
    Returns:
        Number of observations created
    """
    if start_date is None:
        start_date = datetime.now(timezone.utc)

    # Create or get the synthetic data source
    from infrastructure.db.models import WaterSource
    source = db.execute(
        select(WaterSource).where(WaterSource.authority == "SYNTHETIC_HISTORICAL")
    ).scalar_one_or_none()
    if not source:
        source = WaterSource(
            authority="SYNTHETIC_HISTORICAL",
            source_url="generated",
            source_type="SYNTHETIC",
            update_frequency="once",
            description="Synthetic historical data for ML training",
        )
        db.add(source)
        db.flush()

    assets = db.execute(
        select(WaterAsset).where(WaterAsset.is_active == True)
    ).scalars().all()

    # Check existing observations to avoid duplicates
    existing = {}
    for asset in assets:
        obs = db.execute(
            select(WaterObservation).where(WaterObservation.asset_id == asset.id)
        ).scalars().all()
        existing[asset.id] = {o.observed_at.date() for o in obs}

    count = 0
    for asset in assets:
        asset_type = asset.asset_type
        seasonal = SEASONAL.get(asset_type, SEASONAL["barrage"])
        is_kabul = "Kabul" in (asset.canonical_name or "")

        for day_offset in range(days, 0, -1):
            obs_date = (start_date - timedelta(days=day_offset)).date()

            # Skip if observation already exists
            if obs_date in existing.get(asset.id, set()):
                continue

            month = obs_date.month
            params = seasonal.get(month, seasonal.get(7, {}))

            obs_time = datetime(
                obs_date.year, obs_date.month, obs_date.day,
                random.randint(0, 23), random.randint(0, 59), 0,
                tzinfo=timezone.utc,
            )

            obs = WaterObservation(
                asset_id=asset.id,
                source_id=source.id,
                observed_at=obs_time,
                data_status="SYNTHETIC_HISTORICAL",
                quality_flag="GENERATED",
            )

            # Generate fields based on asset type
            if asset_type == "reservoir":
                level_params = params.get("water_level_ft", (1545, 10))
                obs.water_level_ft = round(_add_trend(_gauss(*level_params), day_offset, days), 2)
                if "inflow_cusecs" in params:
                    obs.inflow_cusecs = round(_add_trend(_gauss(*params["inflow_cusecs"]), day_offset, days))
                if "outflow_cusecs" in params:
                    obs.outflow_cusecs = round(_add_trend(_gauss(*params["outflow_cusecs"]), day_offset, days))

            elif asset_type == "barrage":
                if "inflow_cusecs" in params:
                    obs.inflow_cusecs = round(_add_trend(_gauss(*params["inflow_cusecs"]), day_offset, days))
                if "outflow_cusecs" in params:
                    obs.outflow_cusecs = round(_add_trend(_gauss(*params["outflow_cusecs"]), day_offset, days))

            elif asset_type == "river_station":
                if is_kabul:
                    kabul_params = KABUL_OVERRIDE.get(month, KABUL_OVERRIDE[7])
                    obs.discharge_cusecs = round(_add_trend(_gauss(*kabul_params["discharge_cusecs"]), day_offset, days))
                else:
                    if "inflow_cusecs" in params:
                        obs.inflow_cusecs = round(_add_trend(_gauss(*params["inflow_cusecs"]), day_offset, days))
                    if "discharge_cusecs" in params:
                        obs.discharge_cusecs = round(_add_trend(_gauss(*params["discharge_cusecs"]), day_offset, days))

            db.add(obs)
            count += 1

    db.commit()
    return count


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("backfill")

    with SessionLocal() as db:
        n = generate_historical_observations(db, days=90)
        logger.info(f"Generated {n} historical observations")
