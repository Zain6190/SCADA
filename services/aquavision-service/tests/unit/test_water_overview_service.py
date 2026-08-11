# tests/unit/test_water_overview_service.py
import unittest
from datetime import date

from domain.entities import WaterIndicatorWeekly
from domain.services.water_overview_service import WaterOverviewService


class TestWaterOverviewService(unittest.TestCase):
    def test_empty(self):
        metrics = WaterOverviewService.compute([], week_start_date=date(2026, 7, 27))
        self.assertEqual(metrics.regions_monitored, 0)
        self.assertEqual(metrics.avg_wai_score, 0.0)
        self.assertEqual(metrics.national_status, "Unknown")

    def test_averages_and_critical_count(self):
        indicators = [
            WaterIndicatorWeekly(region_id=5, week_start_date=date(2026, 7, 27), wai_score=80, severity="Normal"),
            WaterIndicatorWeekly(region_id=8, week_start_date=date(2026, 7, 27), wai_score=20, severity="Critical"),
            WaterIndicatorWeekly(region_id=11, week_start_date=date(2026, 7, 27), wai_score=35, severity="Severe"),
        ]
        metrics = WaterOverviewService.compute(indicators)
        self.assertEqual(metrics.regions_monitored, 3)
        self.assertEqual(metrics.avg_wai_score, 45.0)
        self.assertEqual(metrics.critical_regions, 2)
        self.assertEqual(metrics.national_status, "Stressed")  # avg 45 -> Stressed


if __name__ == "__main__":
    unittest.main()
