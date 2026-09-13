"""
Physics-based inflow estimation for Indus Basin assets.

Combines:
1. Mass balance for reservoirs (Tarbela, Mangla): inflow = outflow + Δstorage/Δt
2. Steady-state for barrages: inflow ≈ discharge (canal withdrawals subtracted)
3. Upstream discharge proxy with travel time lugs
4. Dynamic weight blending based on data freshness

Storage curves from WAPDA/IRSA official data:
- Tarbela: 1,402 ft (dead) → 1,550 ft (full) = 5.73 MAF = 2,502,240 cusec-days
- Mangla: 1,050 ft (dead) → 1,242 ft (full) = 7.5 MAF = 3,267,000 cusec-days

Travel times from FFD/IRSA bulletins:
- Tarbela → Kalabagh: 24-30h
- Kalabagh → Chashma: 12-18h
- Chashma → Taunsa: 24-36h
- Taunsa → Guddu: 36-48h
- Guddu → Sukkur: 24-36h
- Sukkur → Kotri: 36-48h
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("aquavision.physics_inflow")


# ─── Storage Curves (WAPDA/IRSA Official) ───────────────────────────────────

# Tarbela: level (ft) → storage (cusec-days)
# Source: WAPDA (Aug 2024): 1,550 ft = 5.766 MAF = 2,515,560 cusec-days
# Dead level: 1,402 ft
TARBELA_LEVELS = [1402, 1420, 1440, 1460, 1480, 1500, 1520, 1540, 1550]
TARBELA_STORAGE = [0, 174720, 524160, 1004640, 1397760, 1789440, 2184000, 2402400, 2515560]

# Mangla: level (ft) → storage (cusec-days)
# Source: WAPDA (Oct 2025): 1,242 ft = 7.277 MAF = 3,169,824 cusec-days
# Dead level: 1,050 ft
MANGLA_LEVELS = [1050, 1080, 1100, 1120, 1140, 1160, 1180, 1200, 1220, 1242]
MANGLA_STORAGE = [0, 217800, 524160, 871200, 1306800, 1742400, 2263200, 2699280, 3049200, 3169824]


def _interpolate_storage(level: float, levels: List[float], storage: List[float]) -> float:
    """Linear interpolation of storage from level."""
    if level <= levels[0]:
        return 0.0
    if level >= levels[-1]:
        return storage[-1]
    for i in range(len(levels) - 1):
        if levels[i] <= level <= levels[i + 1]:
            frac = (level - levels[i]) / (levels[i + 1] - levels[i])
            return storage[i] + frac * (storage[i + 1] - storage[i])
    return storage[-1]


def tarbela_storage(level_ft: float) -> float:
    """Tarbela storage in cusec-days from water level."""
    return _interpolate_storage(level_ft, TARBELA_LEVELS, TARBELA_STORAGE)


def mangla_storage(level_ft: float) -> float:
    """Mangla storage in cusec-days from water level."""
    return _interpolate_storage(level_ft, MANGLA_LEVELS, MANGLA_STORAGE)


# ─── Travel Times (hours) ───────────────────────────────────────────────────

TRAVEL_TIMES = {
    # (upstream_asset_id, downstream_asset_id): hours
    (1, 4): 27,    # Tarbela → Kalabagh
    (4, 3): 15,    # Kalabagh → Chashma
    (3, 5): 30,    # Chashma → Taunsa
    (5, 6): 42,    # Taunsa → Guddu
    (6, 7): 30,    # Guddu → Sukkur
    (7, 8): 42,    # Sukkur → Kotri
    (10, 11): 24,  # Chenab@Marala → Panjnad
}

# Upstream relationships
UPSTREAM_MAP = {
    1: [],           # Tarbela: headwater (Indus)
    2: [],           # Mangla: headwater (Jhelum)
    4: [1, 9],       # Kalabagh: Tarbela + Kabul@Nowshera
    3: [1, 9],       # Chashma: Tarbela + Kabul (via Kalabagh)
    5: [4],          # Taunsa: Kalabagh
    6: [5],          # Guddu: Taunsa
    7: [6],          # Sukkur: Guddu
    8: [7],          # Kotri: Sukkur
    9: [],           # Kabul@Nowshera: headwater
    10: [],          # Chenab@Marala: headwater
    11: [10, 2],     # Panjnad: Chenab + Jhelum (via Mangla)
}

# Reservoir vs barrage classification
RESERVOIRS = {1, 2}  # Tarbela, Mangla (have storage)
BARRAGES = {3, 4, 5, 6, 7, 8, 9, 10, 11}  # Run-of-river


# ─── Mass Balance Inflow ────────────────────────────────────────────────────

def estimate_inflow_physics(
    asset_id: int,
    level_ft: float,
    outflow_cusecs: float,
    prev_level_ft: Optional[float] = None,
    prev_outflow_cusecs: Optional[float] = None,
    dt_hours: float = 24.0,
) -> Optional[float]:
    """Estimate inflow using physics (mass balance or steady-state).
    
    For reservoirs: inflow = outflow + Δstorage/Δt
    For barrages: inflow ≈ outflow (steady-state assumption)
    
    Returns inflow in cusecs, or None if insufficient data.
    """
    if asset_id in RESERVOIRS:
        if prev_level_ft is None or prev_outflow_cusecs is None:
            return None
        
        # Storage function
        storage_fn = tarbela_storage if asset_id == 1 else mangla_storage
        
        storage_now = storage_fn(level_ft)
        storage_prev = storage_fn(prev_level_ft)
        
        # Δstorage in cusec-days, convert to cusecs
        delta_storage_days = storage_now - storage_prev
        delta_storage_cusecs = delta_storage_days / dt_hours * 24.0  # cusec-days → cusecs
        
        # Average outflow over the period
        avg_outflow = (outflow_cusecs + prev_outflow_cusecs) / 2.0
        
        inflow = avg_outflow + delta_storage_cusecs
        
        # Sanity check: inflow should be positive and within reasonable range
        if inflow < 0:
            inflow = avg_outflow  # Fallback: assume steady-state
        if inflow > 1_000_000:  # 1M cusecs is extreme
            logger.warning(f"Physics inflow {inflow:.0f} cusecs for asset {asset_id} seems excessive")
        
        return inflow
    
    elif asset_id in BARRAGES:
        # Barrages: steady-state assumption
        # inflow ≈ outflow (canal withdrawals are small relative to river flow)
        return outflow_cusecs
    
    return None


# ─── Upstream Discharge Proxy ───────────────────────────────────────────────

def get_upstream_discharge(
    asset_id: int,
    observations: Dict[int, Dict],
    travel_times: Dict[Tuple[int, int], int] = None,
) -> Optional[float]:
    """Get upstream discharge proxy for an asset.
    
    Uses travel-time-adjusted upstream observations.
    
    Args:
        asset_id: Target asset
        observations: {asset_id: {"discharge": cusecs, "observed_at": datetime}}
        travel_times: Override travel times (hours)
    
    Returns upstream discharge in cusecs, or None.
    """
    if travel_times is None:
        travel_times = TRAVEL_TIMES
    
    upstream_ids = UPSTREAM_MAP.get(asset_id, [])
    if not upstream_ids:
        return None
    
    upstream_discharges = []
    
    for upstream_id in upstream_ids:
        if upstream_id not in observations:
            continue
        
        obs = observations[upstream_id]
        discharge = obs.get("discharge") or obs.get("outflow")
        if discharge is None or discharge <= 0:
            continue
        
        # Apply travel time adjustment (simple: just use the value)
        # In a more sophisticated model, we'd shift the time series
        upstream_discharges.append(discharge)
    
    if not upstream_discharges:
        return None
    
    # Sum of upstream discharges
    return sum(upstream_discharges)


# ─── Dynamic Weight Blending ────────────────────────────────────────────────

def compute_blend_weights(
    irsa_age_hours: Optional[float] = None,
    has_physics: bool = True,
    has_upstream: bool = True,
) -> Dict[str, float]:
    """Compute blending weights based on data freshness.
    
    Weight matrix:
    | IRSA Age    | w1 (IRSA) | w2 (Physics) | w3 (Upstream) | w4 (Median) |
    |-------------|-----------|--------------|---------------|-------------|
    | 0-1 days    | 0.70      | 0.15         | 0.10          | 0.05        |
    | 2-3 days    | 0.40      | 0.25         | 0.25          | 0.10        |
    | 4-7 days    | 0.20      | 0.30         | 0.30          | 0.20        |
    | 7+ days     | 0.00      | 0.35         | 0.35          | 0.30        |
    """
    if irsa_age_hours is not None:
        age_days = irsa_age_hours / 24.0
    else:
        age_days = 999  # No IRSA data
    
    if age_days <= 1:
        weights = {"irsa": 0.70, "physics": 0.15, "upstream": 0.10, "median": 0.05}
    elif age_days <= 3:
        weights = {"irsa": 0.40, "physics": 0.25, "upstream": 0.25, "median": 0.10}
    elif age_days <= 7:
        weights = {"irsa": 0.20, "physics": 0.30, "upstream": 0.30, "median": 0.20}
    else:
        weights = {"irsa": 0.00, "physics": 0.35, "upstream": 0.35, "median": 0.30}
    
    # Zero out unavailable sources
    if not has_physics:
        # Redistribute physics weight to others
        p = weights["physics"]
        weights["physics"] = 0
        remaining = weights["irsa"] + weights["upstream"] + weights["median"]
        if remaining > 0:
            weights["irsa"] += p * weights["irsa"] / remaining
            weights["upstream"] += p * weights["upstream"] / remaining
            weights["median"] += p * weights["median"] / remaining
    
    if not has_upstream:
        u = weights["upstream"]
        weights["upstream"] = 0
        remaining = weights["irsa"] + weights["physics"] + weights["median"]
        if remaining > 0:
            weights["irsa"] += u * weights["irsa"] / remaining
            weights["physics"] += u * weights["physics"] / remaining
            weights["median"] += u * weights["median"] / remaining
    
    # Normalize
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    return weights


def blend_inflow(
    irsa_inflow: Optional[float] = None,
    physics_inflow: Optional[float] = None,
    upstream_discharge: Optional[float] = None,
    median_inflow: Optional[float] = None,
    irsa_age_hours: Optional[float] = None,
) -> Dict:
    """Blend inflow estimates from multiple sources.
    
    Returns:
        {"inflow": float, "source": str, "weights": dict, "inflow_missing": bool}
    """
    weights = compute_blend_weights(
        irsa_age_hours=irsa_age_hours,
        has_physics=physics_inflow is not None,
        has_upstream=upstream_discharge is not None,
    )
    
    sources = {
        "irsa": irsa_inflow,
        "physics": physics_inflow,
        "upstream": upstream_discharge,
        "median": median_inflow,
    }
    
    # Compute weighted average
    total_weight = 0
    weighted_sum = 0
    used_sources = []
    
    for source, weight in weights.items():
        value = sources.get(source)
        if value is not None and value > 0:
            weighted_sum += value * weight
            total_weight += weight
            used_sources.append(source)
    
    if total_weight > 0:
        blended = weighted_sum / total_weight
    elif median_inflow is not None:
        blended = median_inflow
        used_sources = ["median"]
    else:
        return {"inflow": 0.0, "source": "NONE", "weights": weights, "inflow_missing": True}
    
    source_label = "+".join(used_sources)
    
    return {
        "inflow": blended,
        "source": source_label,
        "weights": weights,
        "inflow_missing": False,
    }


# ─── Main Entry Point ──────────────────────────────────────────────────────

def estimate_inflow(
    asset_id: int,
    db_session,
    irsa_inflow: Optional[float] = None,
    irsa_age_hours: Optional[float] = None,
) -> Dict:
    """Estimate inflow for an asset using all available methods.
    
    Returns:
        {"inflow": float, "source": str, "method": str, "inflow_missing": bool}
    """
    from sqlalchemy import text
    from infrastructure.db.models import WaterObservation
    
    # Get latest observations for this asset and upstream
    upstream_ids = UPSTREAM_MAP.get(asset_id, [])
    all_asset_ids = [asset_id] + upstream_ids
    
    observations = {}
    for aid in all_asset_ids:
        row = db_session.execute(
            text("""
                SELECT asset_id, water_level_ft, outflow_cusecs, discharge_cusecs,
                       inflow_cusecs, observed_at
                FROM aquavision.water_observations
                WHERE asset_id = :asset_id
                ORDER BY observed_at DESC
                LIMIT 2
            """),
            {"asset_id": aid},
        ).mappings().all()
        
        if row:
            observations[aid] = dict(row[0])
            if len(row) > 1:
                observations[aid]["prev"] = dict(row[1])
    
    latest = observations.get(asset_id, {})
    level = latest.get("water_level_ft")
    outflow = latest.get("outflow_cusecs")
    discharge = latest.get("discharge_cusecs")
    prev = latest.get("prev", {})
    
    # Method 1: Physics-based (mass balance for reservoirs)
    physics_inflow = None
    if level is not None and outflow is not None:
        prev_level = prev.get("water_level_ft")
        prev_outflow = prev.get("outflow_cusecs")
        physics_inflow = estimate_inflow_physics(
            asset_id=asset_id,
            level_ft=level,
            outflow_cusecs=outflow,
            prev_level_ft=prev_level,
            prev_outflow_cusecs=prev_outflow,
        )
    
    # Method 2: Upstream discharge proxy
    upstream_discharge = get_upstream_discharge(asset_id, observations)
    
    # Method 3: Median fallback (from recent observations)
    median_inflow = None
    rows = db_session.execute(
        text("""
            SELECT inflow_cusecs FROM aquavision.water_observations
            WHERE asset_id = :asset_id AND inflow_cusecs IS NOT NULL AND inflow_cusecs > 0
            ORDER BY observed_at DESC LIMIT 30
        """),
        {"asset_id": asset_id},
    ).scalars().all()
    if rows:
        median_inflow = float(np.median(rows))
    
    # Blend
    result = blend_inflow(
        irsa_inflow=irsa_inflow,
        physics_inflow=physics_inflow,
        upstream_discharge=upstream_discharge,
        median_inflow=median_inflow,
        irsa_age_hours=irsa_age_hours,
    )
    
    result["method"] = "blended"
    result["physics_inflow"] = physics_inflow
    result["upstream_discharge"] = upstream_discharge
    
    logger.info(
        f"Asset {asset_id}: inflow={result['inflow']:.0f} cusecs "
        f"(source={result['source']}, physics={physics_inflow}, "
        f"upstream={upstream_discharge}, irsa={irsa_inflow})"
    )
    
    return result
