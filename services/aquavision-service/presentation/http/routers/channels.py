# presentation/http/routers/channels.py
# Module 6.4: serve the river and canal condition layer as GeoJSON.
#
# The existing /water/map-data endpoint serves region POLYGONS joined to weekly
# indicators. This is the channel equivalent: LINESTRINGS joined to condition.
#
# Every feature carries its `method` so a consumer can always tell an official
# gauge reading from a satellite estimate. Presenting them interchangeably would
# be the single most misleading thing this layer could do.

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session

logger = logging.getLogger("aquavision.api.channels")

router = APIRouter()

# Untrimmed, Pakistan's canal network is ~10,500 linestrings. Simplification
# tolerance in degrees, chosen by zoom so a national view stays renderable.
SIMPLIFY_BY_ZOOM = {
    "national": 0.005,   # ~500 m
    "province": 0.001,   # ~100 m
    "district": 0.0002,  # ~20 m
    "full": None,        # no simplification
}

MAX_FEATURES = 5000


@router.get("/channels")
async def get_channels(
    channel_type: Optional[str] = Query(
        None, pattern="^(river|canal|link_canal)$",
        description="Filter by channel type."),
    monitored_only: bool = Query(
        True, description="Only channels flagged for monitoring (named/major)."),
    week: Optional[str] = Query(
        None, description="Condition as of this week (YYYY-MM-DD). Latest if omitted."),
    condition: Optional[str] = Query(
        None, pattern="^(FLOWING|REDUCED|LOW|DRY|UNKNOWN)$",
        description="Only channels in this condition."),
    detail: str = Query(
        "national", pattern="^(national|province|district|full)$",
        description="Geometry detail; lower detail simplifies server-side."),
    limit: int = Query(MAX_FEATURES, ge=1, le=MAX_FEATURES),
    db: Session = Depends(get_session),
):
    """River and canal geometry joined to its latest condition, as GeoJSON.

    This is the main output of scope module 6.4.
    """
    tolerance = SIMPLIFY_BY_ZOOM.get(detail)
    geom_expr = (
        "ST_AsGeoJSON(c.geom)" if tolerance is None
        else f"ST_AsGeoJSON(ST_SimplifyPreserveTopology(c.geom, {tolerance}))"
    )

    # Latest condition per channel, or the condition for a named week. Ordering
    # by method puts GAUGE_DISCHARGE ahead of NDWI_MASK when both exist for the
    # same week: an official measurement outranks a satellite inference.
    sql = f"""
        WITH latest AS (
            SELECT DISTINCT ON (cc.channel_id)
                   cc.channel_id, cc.observed_week, cc.method,
                   cc.discharge_cusecs, cc.wet_fraction,
                   cc.baseline, cc.change_pct, cc.condition
            FROM aquavision.water_channel_condition cc
            WHERE (:week IS NULL OR cc.observed_week = CAST(:week AS DATE))
            ORDER BY cc.channel_id, cc.observed_week DESC, cc.method ASC
        )
        SELECT c.id, c.name, c.channel_type, c.irsa_label, c.length_km,
               c.is_monitored, c.feeds_from_asset_id,
               a.canonical_name AS feeds_from,
               l.observed_week, l.method, l.discharge_cusecs, l.wet_fraction,
               l.baseline, l.change_pct,
               COALESCE(l.condition, 'UNKNOWN') AS condition,
               {geom_expr} AS geojson
        FROM aquavision.water_channels c
        LEFT JOIN latest l ON l.channel_id = c.id
        LEFT JOIN aquavision.water_assets a ON a.id = c.feeds_from_asset_id
        WHERE (:channel_type IS NULL OR c.channel_type = :channel_type)
          AND (NOT :monitored_only OR c.is_monitored)
          AND (:condition IS NULL OR COALESCE(l.condition, 'UNKNOWN') = :condition)
        ORDER BY c.is_monitored DESC, c.length_km DESC NULLS LAST
        LIMIT :limit
    """

    try:
        rows = db.execute(text(sql), {
            "channel_type": channel_type,
            "monitored_only": monitored_only,
            "week": week,
            "condition": condition,
            "limit": limit,
        }).mappings().all()
    except Exception as exc:  # noqa: BLE001
        logger.error("Channel query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Channel layer unavailable. Has migration 006_water_channels.sql been applied?",
        )

    import json as _json

    features = []
    for r in rows:
        if not r["geojson"]:
            continue
        features.append({
            "type": "Feature",
            "geometry": _json.loads(r["geojson"]),
            "properties": {
                "id": r["id"],
                "name": r["name"],
                "channel_type": r["channel_type"],
                "condition": r["condition"],
                # Never let a gauge reading pass as a satellite observation.
                "method": r["method"],
                "observed_week": str(r["observed_week"]) if r["observed_week"] else None,
                "discharge_cusecs": float(r["discharge_cusecs"]) if r["discharge_cusecs"] is not None else None,
                "wet_fraction": float(r["wet_fraction"]) if r["wet_fraction"] is not None else None,
                "baseline": float(r["baseline"]) if r["baseline"] is not None else None,
                "change_pct": float(r["change_pct"]) if r["change_pct"] is not None else None,
                "length_km": float(r["length_km"]) if r["length_km"] is not None else None,
                "feeds_from": r["feeds_from"],
                "irsa_label": r["irsa_label"],
            },
        })

    truncated = len(rows) >= limit
    if truncated:
        logger.warning("Channel layer truncated at %d features", limit)

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "count": len(features),
            "detail": detail,
            "simplify_tolerance_deg": tolerance,
            # Silent truncation would read as "this is the whole network".
            "truncated": truncated,
            "week": week,
        },
    }


@router.get("/channels/summary")
async def get_channel_summary(
    week: Optional[str] = Query(None, description="Week to summarise (YYYY-MM-DD)."),
    db: Session = Depends(get_session),
):
    """Condition counts by channel type - the KPI row for the map page."""
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (cc.channel_id)
                   cc.channel_id, cc.condition, cc.method, cc.observed_week
            FROM aquavision.water_channel_condition cc
            WHERE (:week IS NULL OR cc.observed_week = CAST(:week AS DATE))
            ORDER BY cc.channel_id, cc.observed_week DESC, cc.method ASC
        )
        SELECT c.channel_type,
               COALESCE(l.condition, 'UNKNOWN') AS condition,
               l.method,
               COUNT(*) AS n
        FROM aquavision.water_channels c
        LEFT JOIN latest l ON l.channel_id = c.id
        WHERE c.is_monitored
        GROUP BY c.channel_type, COALESCE(l.condition, 'UNKNOWN'), l.method
        ORDER BY c.channel_type, condition
    """
    try:
        rows = db.execute(text(sql), {"week": week}).mappings().all()
    except Exception as exc:  # noqa: BLE001
        logger.error("Channel summary failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Channel layer unavailable. Has migration 006_water_channels.sql been applied?",
        )

    return {
        "week": week,
        "by_type": [dict(r) for r in rows],
        "needs_attention": sum(
            r["n"] for r in rows if r["condition"] in ("LOW", "DRY")
        ),
    }
