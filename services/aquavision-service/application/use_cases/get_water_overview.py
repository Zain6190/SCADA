# application/use_cases/get_water_overview.py
from application.dtos import WaterOverviewResponse
from domain.entities import WaterIndicatorWeekly
from domain.services.water_overview_service import WaterOverviewService
from infrastructure.db.repositories.water_alert_repo import WaterAlertRepository
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository


class GetWaterOverviewUseCase:
    """Aggregate the latest week's indicators into national KPIs."""

    def __init__(
        self,
        indicator_repo: WaterIndicatorRepository,
        alert_repo: WaterAlertRepository,
    ):
        self._indicators = indicator_repo
        self._alerts = alert_repo

    def execute(self) -> WaterOverviewResponse:
        latest_week = self._indicators.get_latest_week()
        if latest_week is None:
            return WaterOverviewResponse(
                week_start_date=None,
                regions_monitored=0,
                avg_wai_score=0.0,
                critical_regions=0,
                active_alerts=0,
                national_status="Unknown",
            )

        rows = self._indicators.list_by_week(latest_week)
        indicators = [
            WaterIndicatorWeekly(
                region_id=r.region_id,
                week_start_date=r.week_start_date,
                week_number=r.week_number,
                year=r.year,
                surface_water_area_km2=float(r.surface_water_area_km2)
                if r.surface_water_area_km2 is not None else None,
                rainfall_mm_30day=float(r.rainfall_mm_30day)
                if r.rainfall_mm_30day is not None else None,
                et_mm_8day=float(r.et_mm_8day) if r.et_mm_8day is not None else None,
                wai_score=float(r.wai_score) if r.wai_score is not None else None,
                severity=r.severity,
            )
            for r in rows
        ]

        metrics = WaterOverviewService.compute(indicators, week_start_date=latest_week)
        active_alerts = self._alerts.count_by_status("New")

        return WaterOverviewResponse(
            week_start_date=metrics.week_start_date,
            regions_monitored=metrics.regions_monitored,
            avg_wai_score=metrics.avg_wai_score,
            critical_regions=metrics.critical_regions,
            active_alerts=active_alerts,
            national_status=metrics.national_status,
        )
