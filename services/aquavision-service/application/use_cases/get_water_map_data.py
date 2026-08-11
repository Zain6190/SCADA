# application/use_cases/get_water_map_data.py
from datetime import date, datetime, timedelta
from typing import Optional

from application.dtos import WaterMapResponse
from domain.services.water_map_service import MapRegionState, WaterMapService
from infrastructure.db.repositories.region_repo import RegionRepository
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository


def parse_week_label(week: str) -> date:
    """Parse '2026-W30' or '2026-07-27' into the Monday of that ISO week."""
    value = week.strip()
    if "W" in value.upper():
        try:
            year, w = value.upper().split("-W")
            return datetime.strptime(f"{year}-W{w}-1", "%G-W%V-%u").date()
        except ValueError:
            pass
    return date.fromisoformat(value)


class GetWaterMapDataUseCase:
    """Join water indicators with region geometry -> GeoJSON FeatureCollection."""

    def __init__(
        self,
        indicator_repo: WaterIndicatorRepository,
        region_repo: RegionRepository,
    ):
        self._indicators = indicator_repo
        self._regions = region_repo

    def execute(
        self,
        week: Optional[str] = None,
        region_type: Optional[str] = None,
    ) -> WaterMapResponse:
        # Resolve target week (latest in DB if not given).
        if week:
            week_date = parse_week_label(week)
            week_label = week
        else:
            week_date = self._indicators.get_latest_week()
            week_label = week_date.isoformat() if week_date else None

        rows = self._indicators.list_by_week(week_date) if week_date else []
        by_region = {r.region_id: r for r in rows}

        geometry = self._regions.geometry_map(region_type=region_type)
        regions = self._regions.list(region_type=region_type)

        states: list[MapRegionState] = []
        for region in regions:
            row = by_region.get(region.id)
            if row is None:
                continue
            states.append(
                MapRegionState(
                    region_id=region.id,
                    name=region.name,
                    region_type=region.type,
                    wai_score=float(row.wai_score) if row.wai_score is not None else None,
                    severity=row.severity,
                    rainfall_mm_30day=float(row.rainfall_mm_30day)
                    if row.rainfall_mm_30day is not None else None,
                    et_mm_8day=float(row.et_mm_8day)
                    if row.et_mm_8day is not None else None,
                    surface_water_change_pct=float(row.surface_water_change_pct)
                    if row.surface_water_change_pct is not None else None,
                    geometry=geometry.get(region.id, {}),
                )
            )

        fc = WaterMapService.build_feature_collection(states, week_label=week_label)
        return WaterMapResponse.model_validate(fc)
