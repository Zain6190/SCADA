# infrastructure/seed/river_network.py
# Seed river network and travel time models from IRSA/PDMA official data.
#
# Data sources:
# - IRSA Daily Water Situation Reports
# - PDMA Flood Reports
# - WAPDA Irrigation Design Wing
# - Historical flood wave observations
#
# NOTE: Travel times are PLANNING ESTIMATES based on historical observations.
# They are NOT calibrated hydraulic model outputs.
# Confidence: MEDIUM (based on historical flood-wave observations)

import logging
from sqlalchemy import select

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterAsset, WaterRiverNetwork, WaterTravelTimeModel

logger = logging.getLogger("aquavision.seed.river_network")

# ─── River Network Segments ─────────────────────────────────────────────────
# Each segment connects two assets on the same river.
# segment_order = position in the chain (1, 2, 3...)

RIVER_SEGMENTS = [
    # === INDUS RIVER ===
    {
        "river_name": "Indus",
        "upstream": "Tarbela Reservoir",
        "downstream": "Kalabagh (Indus)",
        "segment_order": 1,
        "distance_km": 300,
        "notes": "Indus River from Tarbela Dam to Kalabagh Headworks",
    },
    {
        "river_name": "Indus",
        "upstream": "Kalabagh (Indus)",
        "downstream": "Taunsa Barrage",
        "segment_order": 2,
        "distance_km": 400,
        "notes": "Indus River from Kalabagh to Taunsa Barrage",
    },
    {
        "river_name": "Indus",
        "upstream": "Taunsa Barrage",
        "downstream": "Guddu Barrage",
        "segment_order": 3,
        "distance_km": 500,
        "notes": "Indus River from Taunsa to Guddu Barrage",
    },
    {
        "river_name": "Indus",
        "upstream": "Guddu Barrage",
        "downstream": "Sukkur Barrage",
        "segment_order": 4,
        "distance_km": 350,
        "notes": "Indus River from Guddu to Sukkur Barrage",
    },
    {
        "river_name": "Indus",
        "upstream": "Sukkur Barrage",
        "downstream": "Kotri Barrage",
        "segment_order": 5,
        "distance_km": 400,
        "notes": "Indus River from Sukkur to Kotri Barrage",
    },

    # === KABUL RIVER ===
    {
        "river_name": "Kabul",
        "upstream": "Kabul @ Nowshera",
        "downstream": "Kalabagh (Indus)",
        "segment_order": 1,
        "distance_km": 100,
        "notes": "Kabul River joins Indus near Kalabagh",
    },

    # === JHELUM-CHENAB SYSTEM ===
    {
        "river_name": "Chenab",
        "upstream": "Chenab @ Marala",
        "downstream": "Panjnad",
        "segment_order": 1,
        "distance_km": 350,
        "notes": "Chenab River from Marala Headworks to Panjnad",
    },
    {
        "river_name": "Jhelum-Chenab",
        "upstream": "Panjnad",
        "downstream": "Guddu Barrage",
        "segment_order": 1,
        "distance_km": 200,
        "notes": "Panjnad joins Indus near Uch, flows to Guddu",
    },
]

# ─── Travel Time Models ──────────────────────────────────────────────────────
# Flow-band-based travel times for each segment.
# Based on historical flood-wave observations (NOT calibrated hydraulic models).
#
# Format: (upstream, downstream, flow_min, flow_max, time_min, time_max, time_expected, confidence)

TRAVEL_TIME_MODELS = [
    # Tarbela → Kalabagh
    # Based on 2010, 2014, 2022 flood events
    ("Tarbela Reservoir", "Kalabagh (Indus)",
     100_000, 200_000,   14, 22, 17, "MEDIUM",
     "Historical flood-wave observation (2010, 2014, 2022)"),
    ("Tarbela Reservoir", "Kalabagh (Indus)",
     200_000, 300_000,   12, 18, 14, "MEDIUM",
     "Historical flood-wave observation (2010, 2014, 2022)"),
    ("Tarbela Reservoir", "Kalabagh (Indus)",
     300_000, 400_000,   10, 16, 12, "MEDIUM",
     "Historical flood-wave observation (2010, 2014, 2022)"),
    ("Tarbela Reservoir", "Kalabagh (Indus)",
     400_000, 500_000,    8, 14, 10, "LOW",
     "Extrapolated from historical events"),

    # Kalabagh → Taunsa
    ("Kalabagh (Indus)", "Taunsa Barrage",
     100_000, 200_000,   28, 40, 34, "MEDIUM",
     "Historical flood-wave observation"),
    ("Kalabagh (Indus)", "Taunsa Barrage",
     200_000, 300_000,   24, 36, 28, "MEDIUM",
     "Historical flood-wave observation"),
    ("Kalabagh (Indus)", "Taunsa Barrage",
     300_000, 400_000,   20, 30, 24, "MEDIUM",
     "Historical flood-wave observation"),
    ("Kalabagh (Indus)", "Taunsa Barrage",
     400_000, 500_000,   16, 26, 20, "LOW",
     "Extrapolated from historical events"),

    # Taunsa → Guddu
    ("Taunsa Barrage", "Guddu Barrage",
     100_000, 200_000,   40, 56, 46, "MEDIUM",
     "Historical flood-wave observation"),
    ("Taunsa Barrage", "Guddu Barrage",
     200_000, 300_000,   36, 48, 40, "MEDIUM",
     "Historical flood-wave observation"),
    ("Taunsa Barrage", "Guddu Barrage",
     300_000, 400_000,   28, 40, 34, "MEDIUM",
     "Historical flood-wave observation"),
    ("Taunsa Barrage", "Guddu Barrage",
     400_000, 500_000,   24, 36, 28, "LOW",
     "Extrapolated from historical events"),

    # Guddu → Sukkur
    ("Guddu Barrage", "Sukkur Barrage",
     100_000, 200_000,   28, 40, 34, "MEDIUM",
     "Historical flood-wave observation"),
    ("Guddu Barrage", "Sukkur Barrage",
     200_000, 300_000,   24, 36, 28, "MEDIUM",
     "Historical flood-wave observation"),
    ("Guddu Barrage", "Sukkur Barrage",
     300_000, 400_000,   20, 30, 24, "MEDIUM",
     "Historical flood-wave observation"),
    ("Guddu Barrage", "Sukkur Barrage",
     400_000, 500_000,   16, 26, 20, "LOW",
     "Extrapolated from historical events"),

    # Sukkur → Kotri
    ("Sukkur Barrage", "Kotri Barrage",
     100_000, 200_000,   28, 40, 34, "MEDIUM",
     "Historical flood-wave observation"),
    ("Sukkur Barrage", "Kotri Barrage",
     200_000, 300_000,   24, 36, 28, "MEDIUM",
     "Historical flood-wave observation"),
    ("Sukkur Barrage", "Kotri Barrage",
     300_000, 400_000,   20, 30, 24, "MEDIUM",
     "Historical flood-wave observation"),
    ("Sukkur Barrage", "Kotri Barrage",
     400_000, 500_000,   16, 26, 20, "LOW",
     "Extrapolated from historical events"),

    # Chenab @ Marala → Panjnad
    ("Chenab @ Marala", "Panjnad",
     50_000, 100_000,   24, 36, 28, "MEDIUM",
     "Historical flood-wave observation"),
    ("Chenab @ Marala", "Panjnad",
     100_000, 150_000,  20, 30, 24, "MEDIUM",
     "Historical flood-wave observation"),
    ("Chenab @ Marala", "Panjnad",
     150_000, 200_000,  16, 26, 20, "MEDIUM",
     "Historical flood-wave observation"),
    ("Chenab @ Marala", "Panjnad",
     200_000, 300_000,  12, 22, 16, "LOW",
     "Extrapolated from historical events"),

    # Panjnad → Guddu (Jhelum-Chenab joins Indus)
    ("Panjnad", "Guddu Barrage",
     100_000, 200_000,  16, 24, 18, "LOW",
     "Estimated from regional hydrology"),
    ("Panjnad", "Guddu Barrage",
     200_000, 300_000,  12, 20, 14, "LOW",
     "Estimated from regional hydrology"),
]


def _get_asset_id(db, canonical_name: str) -> int:
    """Get asset ID by canonical name."""
    asset = db.execute(
        select(WaterAsset).where(WaterAsset.canonical_name == canonical_name)
    ).scalar_one_or_none()
    if not asset:
        raise ValueError(f"Asset '{canonical_name}' not found")
    return asset.id


def seed_river_network():
    """Seed river network segments."""
    with SessionLocal() as db:
        seeded = 0
        skipped = 0

        for seg in RIVER_SEGMENTS:
            try:
                upstream_id = _get_asset_id(db, seg["upstream"])
                downstream_id = _get_asset_id(db, seg["downstream"])
            except ValueError as e:
                logger.warning(f"Skipping segment: {e}")
                skipped += 1
                continue

            # Check if already exists
            existing = db.execute(
                select(WaterRiverNetwork).where(
                    WaterRiverNetwork.upstream_asset_id == upstream_id,
                    WaterRiverNetwork.downstream_asset_id == downstream_id,
                )
            ).scalar_one_or_none()

            if existing:
                skipped += 1
                continue

            network = WaterRiverNetwork(
                river_name=seg["river_name"],
                upstream_asset_id=upstream_id,
                downstream_asset_id=downstream_id,
                segment_order=seg["segment_order"],
                distance_km=seg["distance_km"],
                source_name="IRSA/PDMA",
                status="PLANNING_ESTIMATE",
                notes=seg.get("notes"),
            )
            db.add(network)
            seeded += 1
            logger.info(f"Seeded segment: {seg['upstream']} → {seg['downstream']} ({seg['distance_km']}km)")

        db.commit()
        logger.info(f"River network seeding: {seeded} new, {skipped} skipped")
        return {"seeded": seeded, "skipped": skipped}


def seed_travel_time_models():
    """Seed travel time models for each segment."""
    with SessionLocal() as db:
        seeded = 0
        skipped = 0

        for model in TRAVEL_TIME_MODELS:
            (upstream, downstream, flow_min, flow_max,
             time_min, time_max, time_expected, confidence, method) = model

            try:
                upstream_id = _get_asset_id(db, upstream)
                downstream_id = _get_asset_id(db, downstream)
            except ValueError as e:
                logger.warning(f"Skipping travel time model: {e}")
                skipped += 1
                continue

            # Get the river segment
            segment = db.execute(
                select(WaterRiverNetwork).where(
                    WaterRiverNetwork.upstream_asset_id == upstream_id,
                    WaterRiverNetwork.downstream_asset_id == downstream_id,
                )
            ).scalar_one_or_none()

            if not segment:
                logger.warning(f"Segment not found: {upstream} → {downstream}")
                skipped += 1
                continue

            # Check if model already exists
            existing = db.execute(
                select(WaterTravelTimeModel).where(
                    WaterTravelTimeModel.river_segment_id == segment.id,
                    WaterTravelTimeModel.flow_min_cusecs == flow_min,
                    WaterTravelTimeModel.flow_max_cusecs == flow_max,
                )
            ).scalar_one_or_none()

            if existing:
                skipped += 1
                continue

            tt_model = WaterTravelTimeModel(
                river_segment_id=segment.id,
                flow_min_cusecs=flow_min,
                flow_max_cusecs=flow_max,
                travel_time_min_hours=time_min,
                travel_time_max_hours=time_max,
                travel_time_expected_hours=time_expected,
                method=method,
                source_name="IRSA/PDMA",
                confidence=confidence,
            )
            db.add(tt_model)
            seeded += 1

        db.commit()
        logger.info(f"Travel time model seeding: {seeded} new, {skipped} skipped")
        return {"seeded": seeded, "skipped": skipped}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Seeding river network...")
    r1 = seed_river_network()
    print(f"  River network: {r1}")
    print("Seeding travel time models...")
    r2 = seed_travel_time_models()
    print(f"  Travel time models: {r2}")
