# domain/services/water_overview_service.py
# Pure domain service: computes national KPI summary from a set of indicators.
from dataclasses import dataclass
from datetime import date
from typing import Optional

from domain.entities import WaterIndicatorWeekly
from domain.water_classifier import classify_severity, is_critical_or_severe


@dataclass
class OverviewMetrics:
    week_start_date: Optional[date]
    regions_monitored: int
    avg_wai_score: float
    critical_regions: int
    national_status: str


class WaterOverviewService:
    @staticmethod
    def compute(
        indicators: list[WaterIndicatorWeekly],
        week_start_date: Optional[date] = None,
    ) -> OverviewMetrics:
        if not indicators:
            return OverviewMetrics(
                week_start_date=week_start_date or date.today(),
                regions_monitored=0,
                avg_wai_score=0.0,
                critical_regions=0,
                national_status="Unknown",
            )

        scores = [i.wai_score for i in indicators if i.wai_score is not None]
        avg_wai = round(sum(scores) / len(scores), 1) if scores else 0.0
        critical = sum(
            1 for i in indicators if i.severity and is_critical_or_severe(i.severity)
        )

        return OverviewMetrics(
            week_start_date=week_start_date or indicators[0].week_start_date,
            regions_monitored=len(indicators),
            avg_wai_score=avg_wai,
            critical_regions=critical,
            national_status=classify_severity(avg_wai) if scores else "Unknown",
        )
