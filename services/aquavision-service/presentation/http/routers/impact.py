# presentation/http/routers/impact.py
# Downstream Impact Engine API.

import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session, engine as sa_engine
from infrastructure.impact.downstream_engine import DownstreamImpactEngine

logger = logging.getLogger("aquavision.api.impact")

router = APIRouter(prefix="/impact", tags=["Downstream Impact"])


class ImpactCalculateRequest(BaseModel):
    source_asset_id: int
    release_flow_cusecs: float
    release_time: str  # ISO format


class SegmentImpactResponse(BaseModel):
    segment_order: int
    river_name: str
    upstream_asset: str
    downstream_asset: str
    distance_km: float
    travel_time_hours: float
    arrival_time: str
    flow_at_arrival: float
    population_exposed: int
    village_count: int
    town_count: int
    bridges_count: int
    hospitals_count: int
    roads_km: float
    confidence: str
    notes: str


class ImpactSummaryResponse(BaseModel):
    source_asset: str
    release_flow_cusecs: float
    release_time: str
    chain_rivers: List[str]
    segments: List[SegmentImpactResponse]
    total_population_exposed: int
    total_villages: int
    total_towns: int
    total_bridges: int
    total_hospitals: int
    total_roads_km: float
    furthest_asset: str
    furthest_arrival: Optional[str]
    total_travel_hours: float


class PreCalculatedImpactResponse(BaseModel):
    id: int
    source_asset_id: int
    downstream_asset_id: Optional[int]
    travel_time_hours_min: Optional[float]
    travel_time_hours_max: Optional[float]
    travel_time_hours_expected: Optional[float]
    distance_km: Optional[float]
    affected_population_est: Optional[int]
    affected_village_count: Optional[int]
    affected_town_count: Optional[int]
    affected_city_count: Optional[int]
    bridges_count: Optional[int]
    hospitals_count: Optional[int]
    roads_km: Optional[float]
    notes: Optional[str]
    upstream_asset: str
    downstream_asset: str


def _get_engine() -> DownstreamImpactEngine:
    return DownstreamImpactEngine(sa_engine)


@router.post("/calculate", response_model=ImpactSummaryResponse)
def calculate_impact(
    request: ImpactCalculateRequest,
    engine: DownstreamImpactEngine = Depends(_get_engine),
):
    """Calculate downstream flood impact from an upstream release."""
    try:
        release_time = datetime.fromisoformat(request.release_time)
    except ValueError:
        raise HTTPException(400, "Invalid datetime format. Use ISO format.")

    if request.release_flow_cusecs <= 0:
        raise HTTPException(400, "Flow must be positive.")

    result = engine.calculate(
        source_asset_id=request.source_asset_id,
        release_flow_cusecs=request.release_flow_cusecs,
        release_time=release_time,
    )

    return ImpactSummaryResponse(
        source_asset=result.source_asset,
        release_flow_cusecs=result.release_flow_cusecs,
        release_time=result.release_time.isoformat(),
        chain_rivers=result.chain_rivers,
        segments=[
            SegmentImpactResponse(
                segment_order=s.segment_order,
                river_name=s.river_name,
                upstream_asset=s.upstream_asset,
                downstream_asset=s.downstream_asset,
                distance_km=s.distance_km,
                travel_time_hours=s.travel_time_hours,
                arrival_time=s.arrival_time.isoformat(),
                flow_at_arrival=s.flow_at_arrival,
                population_exposed=s.population_exposed,
                village_count=s.village_count,
                town_count=s.town_count,
                bridges_count=s.bridges_count,
                hospitals_count=s.hospitals_count,
                roads_km=s.roads_km,
                confidence=s.confidence,
                notes=s.notes,
            )
            for s in result.segments
        ],
        total_population_exposed=result.total_population_exposed,
        total_villages=result.total_villages,
        total_towns=result.total_towns,
        total_bridges=result.total_bridges,
        total_hospitals=result.total_hospitals,
        total_roads_km=result.total_roads_km,
        furthest_asset=result.furthest_asset,
        furthest_arrival=result.furthest_arrival.isoformat() if result.furthest_arrival else None,
        total_travel_hours=result.total_travel_hours,
    )


@router.get("/precalculated", response_model=List[PreCalculatedImpactResponse])
def get_precalculated_impacts(
    engine: DownstreamImpactEngine = Depends(_get_engine),
):
    """Get all pre-calculated downstream impacts."""
    impacts = engine.get_all_impacts()
    return [
        PreCalculatedImpactResponse(
            id=i["id"],
            source_asset_id=i["source_asset_id"],
            downstream_asset_id=i.get("downstream_asset_id"),
            travel_time_hours_min=i.get("travel_time_hours_min"),
            travel_time_hours_max=i.get("travel_time_hours_max"),
            travel_time_hours_expected=i.get("travel_time_hours_expected"),
            distance_km=i.get("distance_km"),
            affected_population_est=i.get("affected_population_est"),
            affected_village_count=i.get("affected_village_count"),
            affected_town_count=i.get("affected_town_count"),
            affected_city_count=i.get("affected_city_count"),
            bridges_count=i.get("bridges_count"),
            hospitals_count=i.get("hospitals_count"),
            roads_km=i.get("roads_km"),
            notes=i.get("notes"),
            upstream_asset=i["upstream_asset"],
            downstream_asset=i["downstream_asset"],
        )
        for i in impacts
    ]


@router.get("/assets")
def get_impact_assets():
    """Get all assets that can be used as impact sources."""
    from sqlalchemy import text
    from infrastructure.db.engine import engine as db_engine

    with db_engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, canonical_name, asset_type, latitude, longitude
                FROM aquavision.water_assets
                WHERE id IN (SELECT DISTINCT upstream_asset_id FROM aquavision.water_river_network)
                ORDER BY id
            """)
        ).mappings().all()
        return [dict(r) for r in rows]
