# infrastructure/thresholds/seed.py
# Seed asset-specific threshold rules for all 11 IRSA assets.
# Thresholds based on IRSA official levels and operational experience.

import logging
from sqlalchemy import select

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterAsset, WaterAssetThreshold

logger = logging.getLogger("aquavision.thresholds.seed")

# ─── Threshold Definitions ──────────────────────────────────────────────────
# Format: canonical_name -> {threshold fields}
# All values from IRSA official data + operational experience.

ASSET_THRESHOLDS = {
    # === RESERVOIRS ===
    "Tarbela Reservoir": {
        "warning_level_ft": 1548.00,
        "danger_level_ft": 1552.00,
        "critical_level_ft": 1555.00,
        "warning_inflow": 250000,
        "danger_inflow": 350000,
        "level_rise_watch_6h": 0.5,
        "level_rise_warning_6h": 1.0,
        "level_rise_critical_6h": 2.0,
        "inflow_rise_watch_6h": 50000,
        "inflow_rise_warning_6h": 100000,
        "notes": "Pakistan's largest dam. Capacity 11.07 MAF. Normal level 1550 ft.",
    },
    "Mangla Reservoir": {
        "warning_level_ft": 1200.00,
        "danger_level_ft": 1205.00,
        "critical_level_ft": 1210.00,
        "warning_inflow": 100000,
        "danger_inflow": 150000,
        "level_rise_watch_6h": 0.5,
        "level_rise_warning_6h": 1.0,
        "level_rise_critical_6h": 2.0,
        "inflow_rise_watch_6h": 30000,
        "inflow_rise_warning_6h": 60000,
        "notes": "Second largest dam. Capacity 7.37 MAF. Normal level 1202 ft.",
    },

    # === BARRAGES ===
    "Chashma Barrage": {
        "warning_discharge": 300000,
        "danger_discharge": 400000,
        "inflow_rise_watch_6h": 40000,
        "inflow_rise_warning_6h": 80000,
        "notes": "Indus barrage between Tarbela and Kalabagh. Manages Chashma-Jhelum link.",
    },
    "Kalabagh (Indus)": {
        "warning_discharge": 350000,
        "danger_discharge": 500000,
        "inflow_rise_watch_6h": 50000,
        "inflow_rise_warning_6h": 100000,
        "notes": "Last headworks on Indus before Tarbela-Tail canal. Critical for Punjab water supply.",
    },
    "Taunsa Barrage": {
        "warning_discharge": 300000,
        "danger_discharge": 450000,
        "inflow_rise_watch_6h": 40000,
        "inflow_rise_warning_6h": 80000,
        "notes": "Indus barrage. Feeds Muzaffargarh and Dera Ghazi Khan canals.",
    },
    "Guddu Barrage": {
        "warning_discharge": 250000,
        "danger_discharge": 350000,
        "inflow_rise_watch_6h": 30000,
        "inflow_rise_warning_6h": 60000,
        "notes": "Indus barrage between Taunsa and Sukkur. Critical for Sindh water.",
    },
    "Sukkur Barrage": {
        "warning_discharge": 250000,
        "danger_discharge": 350000,
        "inflow_rise_watch_6h": 30000,
        "inflow_rise_warning_6h": 60000,
        "notes": "Largest barrage on Indus. Feeds 6 canals for Sindh irrigation.",
    },
    "Kotri Barrage": {
        "warning_discharge": 200000,
        "danger_discharge": 300000,
        "inflow_rise_watch_6h": 25000,
        "inflow_rise_warning_6h": 50000,
        "notes": "Last barrage on Indus before sea. Critical for downstream flows.",
    },

    # === RIVER STATIONS ===
    "Kabul @ Nowshera": {
        "warning_discharge": 100000,
        "danger_discharge": 150000,
        "inflow_rise_watch_6h": 20000,
        "inflow_rise_warning_6h": 40000,
        "notes": "Kabul River at Nowshera. Key for Peshawar Valley flood monitoring.",
    },
    "Chenab @ Marala": {
        "warning_discharge": 150000,
        "danger_discharge": 250000,
        "inflow_rise_watch_6h": 25000,
        "inflow_rise_warning_6h": 50000,
        "notes": "Chenab River at Marala Headworks. Feeds Marala-Ravi link.",
    },
    "Panjnad": {
        "warning_discharge": 200000,
        "danger_discharge": 300000,
        "inflow_rise_watch_6h": 30000,
        "inflow_rise_warning_6h": 60000,
        "notes": "Confluence of Chenab + Jhelum before joining Indus. Monitors combined flows.",
    },
}


def seed_thresholds():
    """Seed threshold rules for all assets."""
    with SessionLocal() as db:
        seeded = 0
        updated = 0

        for canonical_name, rules in ASSET_THRESHOLDS.items():
            asset = db.execute(
                select(WaterAsset).where(WaterAsset.canonical_name == canonical_name)
            ).scalar_one_or_none()

            if not asset:
                logger.warning(f"Asset '{canonical_name}' not found, skipping")
                continue

            existing = db.execute(
                select(WaterAssetThreshold).where(WaterAssetThreshold.asset_id == asset.id)
            ).scalar_one_or_none()

            if existing:
                # Update
                for key, value in rules.items():
                    setattr(existing, key, value)
                updated += 1
                logger.info(f"Updated threshold for {canonical_name}")
            else:
                # Insert
                threshold = WaterAssetThreshold(asset_id=asset.id, **rules)
                db.add(threshold)
                seeded += 1
                logger.info(f"Seeded threshold for {canonical_name}")

        db.commit()
        logger.info(f"Threshold seeding complete: {seeded} new, {updated} updated")
        return {"seeded": seeded, "updated": updated}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = seed_thresholds()
    print(f"\nSeeded: {result['seeded']}, Updated: {result['updated']}")
