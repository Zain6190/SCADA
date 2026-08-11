# domain/services/water_map_service.py
# Pure domain service: builds a GeoJSON FeatureCollection of region water state.
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MapRegionState:
    region_id: int
    name: str
    region_type: str
    wai_score: Optional[float]
    severity: Optional[str]
    rainfall_mm_30day: Optional[float]
    et_mm_8day: Optional[float]
    surface_water_change_pct: Optional[float]
    geometry: dict  # GeoJSON geometry (SRID 4326)


class WaterMapService:
    @staticmethod
    def build_feature(state: MapRegionState) -> dict:
        return {
            "type": "Feature",
            "geometry": state.geometry,
            "properties": {
                "region_id": state.region_id,
                "name": state.name,
                "region_type": state.region_type,
                "wai_score": state.wai_score,
                "severity": state.severity,
                "rainfall_mm_30day": state.rainfall_mm_30day,
                "et_mm_8day": state.et_mm_8day,
                "surface_water_change_pct": state.surface_water_change_pct,
            },
        }

    @staticmethod
    def build_feature_collection(
        states: list[MapRegionState], week_label: Optional[str] = None
    ) -> dict:
        return {
            "type": "FeatureCollection",
            "week": week_label,
            "features": [WaterMapService.build_feature(s) for s in states],
        }
