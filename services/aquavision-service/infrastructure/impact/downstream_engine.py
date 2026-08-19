"""
Downstream Impact Engine

Calculates flood arrival times and affected population along river chains.
Uses water_river_network, water_travel_time_models, and water_downstream_impacts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _to_float(val) -> float:
    """Convert Decimal/int/float/None to float."""
    if val is None:
        return 0.0
    return float(val)


def _to_int(val) -> int:
    """Convert Decimal/int/float/None to int."""
    if val is None:
        return 0
    return int(val)

logger = logging.getLogger(__name__)


@dataclass
class SegmentImpact:
    """Impact at a single downstream segment."""
    segment_order: int
    river_name: str
    upstream_asset: str
    downstream_asset: str
    distance_km: float
    travel_time_hours: float
    arrival_time: datetime
    flow_at_arrival: float
    population_exposed: int
    village_count: int
    town_count: int
    bridges_count: int
    hospitals_count: int
    roads_km: float
    confidence: str
    notes: str = ""


@dataclass
class DownstreamImpactResult:
    """Complete downstream impact calculation result."""
    source_asset: str
    release_flow_cusecs: float
    release_time: datetime
    segments: list[SegmentImpact] = field(default_factory=list)
    total_population_exposed: int = 0
    total_villages: int = 0
    total_towns: int = 0
    total_bridges: int = 0
    total_hospitals: int = 0
    total_roads_km: float = 0.0
    furthest_asset: str = ""
    furthest_arrival: Optional[datetime] = None
    total_travel_hours: float = 0.0
    chain_rivers: list[str] = field(default_factory=list)


class DownstreamImpactEngine:
    """Calculate downstream flood impact from upstream release."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def calculate(
        self,
        source_asset_id: int,
        release_flow_cusecs: float,
        release_time: datetime,
        attenuation_factor: float = 0.95,
    ) -> DownstreamImpactResult:
        """
        Calculate downstream impact from an upstream release.

        Args:
            source_asset_id: ID of the source asset (e.g., Tarbela = 1)
            release_flow_cusecs: Flow release in cusecs
            release_time: When the release occurs
            attenuation_factor: Flow reduction per segment (0.95 = 5% loss)

        Returns:
            DownstreamImpactResult with all segment impacts
        """
        source_name = self._get_asset_name(source_asset_id)
        logger.info(
            f"Calculating impact: {source_name} release {release_flow_cusecs:,.0f} cusecs"
        )

        # Find all downstream segments from this source
        segments = self._get_downstream_chain(source_asset_id)

        result = DownstreamImpactResult(
            source_asset=source_name,
            release_flow_cusecs=release_flow_cusecs,
            release_time=release_time,
        )

        current_time = release_time
        current_flow = release_flow_cusecs

        for seg in segments:
            # Get travel time for this flow
            travel_time = self._get_travel_time(
                seg["river_segment_id"], current_flow
            )
            confidence = seg.get("confidence", "MEDIUM")

            arrival_time = current_time + timedelta(hours=travel_time)
            flow_at_arrival = current_flow * (attenuation_factor ** seg["segment_order"])

            # Get impact data
            impact = self._get_impact_data(seg["river_segment_id"])

            segment_impact = SegmentImpact(
                segment_order=seg["segment_order"],
                river_name=seg["river_name"],
                upstream_asset=seg["upstream_name"],
                downstream_asset=seg["downstream_name"],
                distance_km=_to_float(seg.get("distance_km", 0)),
                travel_time_hours=travel_time,
                arrival_time=arrival_time,
                flow_at_arrival=flow_at_arrival,
                population_exposed=_to_int(impact.get("affected_population_est", 0)),
                village_count=_to_int(impact.get("affected_village_count", 0)),
                town_count=_to_int(impact.get("affected_town_count", 0)),
                bridges_count=_to_int(impact.get("bridges_count", 0)),
                hospitals_count=_to_int(impact.get("hospitals_count", 0)),
                roads_km=_to_float(impact.get("roads_km", 0)),
                confidence=confidence,
                notes=impact.get("notes", ""),
            )
            result.segments.append(segment_impact)

            # Accumulate totals
            result.total_population_exposed += segment_impact.population_exposed
            result.total_villages += segment_impact.village_count
            result.total_towns += segment_impact.town_count
            result.total_bridges += segment_impact.bridges_count
            result.total_hospitals += segment_impact.hospitals_count
            result.total_roads_km += segment_impact.roads_km

            if seg["river_name"] not in result.chain_rivers:
                result.chain_rivers.append(seg["river_name"])

            current_time = arrival_time
            current_flow = flow_at_arrival

        if result.segments:
            last = result.segments[-1]
            result.furthest_asset = last.downstream_asset
            result.furthest_arrival = last.arrival_time
            result.total_travel_hours = (
                last.arrival_time - release_time
            ).total_seconds() / 3600

        logger.info(
            f"Impact: {result.total_population_exposed:,} people, "
            f"{result.total_bridges} bridges, "
            f"{result.total_hospitals} hospitals, "
            f"furthest: {result.furthest_asset} in {result.total_travel_hours:.0f}h"
        )

        return result

    def _get_asset_name(self, asset_id: int) -> str:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT canonical_name FROM aquavision.water_assets WHERE id = :id"),
                {"id": asset_id},
            ).mappings().first()
            return row["canonical_name"] if row else f"Asset {asset_id}"

    def _get_downstream_chain(self, source_asset_id: int) -> list[dict]:
        """Get all downstream segments from a source asset, following the chain."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT rn.id as river_segment_id,
                           rn.segment_order,
                           rn.river_name,
                           rn.distance_km,
                           a1.canonical_name as upstream_name,
                           a2.canonical_name as downstream_name,
                           a2.id as downstream_asset_id,
                           ttm.confidence
                    FROM aquavision.water_river_network rn
                    JOIN aquavision.water_assets a1 ON a1.id = rn.upstream_asset_id
                    JOIN aquavision.water_assets a2 ON a2.id = rn.downstream_asset_id
                    LEFT JOIN LATERAL (
                        SELECT confidence
                        FROM aquavision.water_travel_time_models
                        WHERE river_segment_id = rn.id
                        ORDER BY ABS(flow_max_cusecs - 200000)
                        LIMIT 1
                    ) ttm ON true
                    WHERE rn.upstream_asset_id = :source_id
                    ORDER BY rn.segment_order
                """),
                {"source_id": source_asset_id},
            ).mappings().all()

            # Also follow downstream chains (e.g., Tarbela → Kalabagh → Taunsa)
            all_segments = list(rows)
            visited = {source_asset_id}
            frontier = [r["downstream_asset_id"] for r in rows]

            while frontier:
                current_id = frontier.pop(0)
                if current_id in visited:
                    continue
                visited.add(current_id)

                more = conn.execute(
                    text("""
                        SELECT rn.id as river_segment_id,
                               rn.segment_order,
                               rn.river_name,
                               rn.distance_km,
                               a1.canonical_name as upstream_name,
                               a2.canonical_name as downstream_name,
                               a2.id as downstream_asset_id,
                               ttm.confidence
                        FROM aquavision.water_river_network rn
                        JOIN aquavision.water_assets a1 ON a1.id = rn.upstream_asset_id
                        JOIN aquavision.water_assets a2 ON a2.id = rn.downstream_asset_id
                        LEFT JOIN LATERAL (
                            SELECT confidence
                            FROM aquavision.water_travel_time_models
                            WHERE river_segment_id = rn.id
                            ORDER BY ABS(flow_max_cusecs - 200000)
                            LIMIT 1
                        ) ttm ON true
                        WHERE rn.upstream_asset_id = :current_id
                        ORDER BY rn.segment_order
                    """),
                    {"current_id": current_id},
                ).mappings().all()

                for r in more:
                    all_segments.append(r)
                    frontier.append(r["downstream_asset_id"])

            return all_segments

    def _get_travel_time(self, river_segment_id: int, flow_cusecs: float) -> float:
        """Get travel time for a given flow in a river segment."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT travel_time_expected_hours, confidence
                    FROM aquavision.water_travel_time_models
                    WHERE river_segment_id = :seg_id
                    AND flow_min_cusecs <= :flow
                    AND flow_max_cusecs > :flow
                    LIMIT 1
                """),
                {"seg_id": river_segment_id, "flow": flow_cusecs},
            ).mappings().first()

            if row:
                return float(row["travel_time_expected_hours"])

            # Fallback: find closest range
            row = conn.execute(
                text("""
                    SELECT travel_time_expected_hours
                    FROM aquavision.water_travel_time_models
                    WHERE river_segment_id = :seg_id
                    ORDER BY ABS((flow_min_cusecs + flow_max_cusecs) / 2 - :flow)
                    LIMIT 1
                """),
                {"seg_id": river_segment_id, "flow": flow_cusecs},
            ).mappings().first()

            return float(row["travel_time_expected_hours"]) if row else 24.0

    def _get_impact_data(self, river_segment_id: int) -> dict:
        """Get pre-calculated impact data for a segment."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT affected_population_est, affected_village_count,
                           affected_town_count, bridges_count, hospitals_count,
                           roads_km, notes
                    FROM aquavision.water_downstream_impacts
                    WHERE id = :seg_id
                    LIMIT 1
                """),
                {"seg_id": river_segment_id},
            ).mappings().first()

            return dict(row) if row else {}

    def get_all_impacts(self) -> list[dict]:
        """Get all pre-calculated downstream impacts."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT d.*, 
                           a1.canonical_name as upstream_asset,
                           a2.canonical_name as downstream_asset
                    FROM aquavision.water_downstream_impacts d
                    JOIN aquavision.water_assets a1 ON a1.id = d.source_asset_id
                    JOIN aquavision.water_assets a2 ON a2.id = d.downstream_asset_id
                    ORDER BY a1.canonical_name, d.travel_time_hours_expected
                """)
            ).mappings().all()
            return [dict(r) for r in rows]
