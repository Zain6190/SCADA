# tests/unit/test_water_classifier.py
import unittest

from domain.water_classifier import classify_severity, is_critical_or_severe, worst_severity


class TestClassifier(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(classify_severity(20), "Critical")
        self.assertEqual(classify_severity(25), "Severe")   # boundary: < critical_min is Critical
        self.assertEqual(classify_severity(30), "Severe")
        self.assertEqual(classify_severity(45), "Stressed")
        self.assertEqual(classify_severity(60), "Moderate")
        self.assertEqual(classify_severity(80), "Normal")

    def test_is_critical_or_severe(self):
        self.assertTrue(is_critical_or_severe("Critical"))
        self.assertTrue(is_critical_or_severe("Severe"))
        self.assertFalse(is_critical_or_severe("Stressed"))

    def test_worst_severity(self):
        self.assertEqual(worst_severity(["Normal", "Severe", "Stressed"]), "Severe")
        self.assertEqual(worst_severity([]), "Unknown")


if __name__ == "__main__":
    unittest.main()
