# Unit-aware flood classification: level vs level, discharge vs discharge.
import unittest

from infrastructure.flood.territories import threshold_flood_classification
from infrastructure.thresholds.flood_class import classify_flood


class TestClassifyFlood(unittest.TestCase):
    def test_level_over_critical_is_critical(self):
        result = classify_flood(
            level=1215.5,
            discharge=None,
            warning_level_ft=1200.0,
            critical_level_ft=1210.0,
        )
        self.assertEqual(result, (0.9, "CRITICAL", "Level at 100% of critical threshold"))

    def test_level_between_warning_and_critical_scales(self):
        result = classify_flood(
            level=1205.0,
            discharge=None,
            warning_level_ft=1200.0,
            critical_level_ft=1210.0,
        )
        self.assertEqual(result, (0.475, "MODERATE", "Level at 50% of critical threshold"))

    def test_level_below_warning_classifies_nothing(self):
        result = classify_flood(
            level=1190.0,
            discharge=None,
            warning_level_ft=1200.0,
            critical_level_ft=1210.0,
        )
        self.assertIsNone(result)

    def test_discharge_over_danger_is_critical(self):
        result = classify_flood(
            level=None,
            discharge=160000.0,
            warning_discharge=100000.0,
            danger_discharge=150000.0,
        )
        self.assertEqual(
            result, (0.9, "CRITICAL", "Discharge at 100% of danger threshold")
        )

    def test_discharge_mid_band_is_high(self):
        result = classify_flood(
            level=None,
            discharge=125000.0,
            warning_discharge=100000.0,
            danger_discharge=150000.0,
        )
        self.assertEqual(
            result, (0.475, "HIGH", "Discharge at 50% of danger threshold")
        )

    def test_discharge_below_warning_classifies_nothing(self):
        result = classify_flood(
            level=None,
            discharge=14300.0,
            warning_discharge=100000.0,
            danger_discharge=150000.0,
        )
        self.assertIsNone(result)

    def test_discharge_never_compares_against_level_thresholds(self):
        result = classify_flood(
            level=None,
            discharge=50000.0,
            warning_level_ft=1200.0,
            critical_level_ft=1210.0,
        )
        self.assertIsNone(result)

    def test_level_never_compares_against_discharge_thresholds(self):
        result = classify_flood(
            level=644.4,
            discharge=None,
            warning_discharge=300000.0,
            danger_discharge=400000.0,
        )
        self.assertIsNone(result)

    def test_no_thresholds_returns_none(self):
        result = classify_flood(
            level=None,
            discharge=50000.0,
            warning_level_ft=None,
            critical_level_ft=None,
        )
        self.assertIsNone(result)

    def test_no_readings_returns_none(self):
        result = classify_flood(
            level=None,
            discharge=None,
            warning_level_ft=1200.0,
            critical_level_ft=1210.0,
            warning_discharge=100000.0,
            danger_discharge=150000.0,
        )
        self.assertIsNone(result)


class TestTerritoryDelegate(unittest.TestCase):
    def test_level_path_matches_classify_flood(self):
        result = threshold_flood_classification(
            discharge=None,
            inflow=80000.0,
            level=1215.5,
            warning_level_ft=1200.0,
            critical_level_ft=1210.0,
        )
        self.assertEqual(result, (0.9, "CRITICAL", "Level at 100% of critical threshold"))

    def test_inflow_alone_never_classifies(self):
        result = threshold_flood_classification(
            discharge=None,
            inflow=80000.0,
            level=None,
            warning_level_ft=1200.0,
            critical_level_ft=1210.0,
        )
        self.assertIsNone(result)

    def test_discharge_with_only_level_thresholds_is_none(self):
        result = threshold_flood_classification(
            discharge=50000.0,
            inflow=None,
            level=None,
            warning_level_ft=1200.0,
            critical_level_ft=1210.0,
        )
        self.assertIsNone(result)

    def test_discharge_thresholds_classify(self):
        result = threshold_flood_classification(
            discharge=160000.0,
            inflow=None,
            level=None,
            warning_discharge=100000.0,
            danger_discharge=150000.0,
        )
        self.assertEqual(
            result, (0.9, "CRITICAL", "Discharge at 100% of danger threshold")
        )


if __name__ == "__main__":
    unittest.main()
