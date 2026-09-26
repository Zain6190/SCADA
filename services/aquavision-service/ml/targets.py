"""Canonical per-asset ML target resolution.

One source of truth for "what does this asset's model predict" — used by
retraining, accuracy seeding, and the forecast pipeline so they can never
drift apart.

Asset target map (data-driven, verified 2026-09-25):
    1, 2  (Tarbela, Mangla)  -> outflow    (reservoir release; discharge_cusecs
                                            is empty; storage_volume is empty so
                                            true mass-balance dS/dt is impossible)
    9, 10 (Kabul, Chenab)    -> discharge  (direct flow observations)
    3-8,11 (barrages)        -> inflow fallback; inference uses physics routing
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

# Explicit map — never resolve these from data.
EXPLICIT_TARGETS: dict[int, str] = {
    1: "outflow",
    2: "outflow",
    9: "discharge",
    10: "discharge",
}

# Assets whose primary discharge path is physics routing (not the ML target).
PHYSICS_ASSETS = frozenset({3, 4, 5, 6, 7, 8, 11})


def _data_detected_target(session, asset_id: int, real_only: bool = False) -> str:
    """Fallback: inflow if abundant, else discharge if abundant, else level."""
    origin_clause = "AND data_origin = 'REAL'" if real_only else ""
    counts = session.execute(
        text(
            f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE inflow_cusecs IS NOT NULL)   AS n_inflow,
                COUNT(*) FILTER (WHERE discharge_cusecs IS NOT NULL) AS n_discharge
            FROM aquavision.water_observations
            WHERE asset_id = :aid
            {origin_clause}
            """
        ),
        {"aid": asset_id},
    ).mappings().one()
    total = int(counts["total"] or 0)
    if not total:
        return "level"
    if int(counts["n_inflow"] or 0) > total * 0.3:
        return "inflow"
    if int(counts["n_discharge"] or 0) > total * 0.3:
        return "discharge"
    return "level"


def resolve_target_field(session, asset_id: int, real_only: bool = False) -> str:
    """Return the concrete target field for an asset ('outflow'|'discharge'|'inflow'|'level').

    Never returns 'auto' — callers must record the concrete field so train-time
    metadata, prediction field routing, and accuracy matching all agree.
    """
    explicit = EXPLICIT_TARGETS.get(asset_id)
    if explicit:
        return explicit
    return _data_detected_target(session, asset_id, real_only=real_only)


def flow_baseline_cusecs(current_obs: dict, target_field: Optional[str] = None) -> float:
    """Current flow (cusecs) best matching the model's target, for trend baselines."""
    if target_field == "outflow":
        order = ("outflow_cusecs", "discharge_cusecs", "inflow_cusecs")
    elif target_field == "inflow":
        order = ("inflow_cusecs", "discharge_cusecs", "outflow_cusecs")
    else:  # discharge / level / unknown — riverine flow first
        order = ("discharge_cusecs", "inflow_cusecs", "outflow_cusecs")
    for key in order:
        val = current_obs.get(key)
        if val:
            return float(val)
    return 0.0
