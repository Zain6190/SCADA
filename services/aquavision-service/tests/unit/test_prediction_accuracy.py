# tests/unit/test_prediction_accuracy.py
"""Unit tests for P1 real accuracy pipeline (prediction_errors → prediction_v2)."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from ml.models.prediction_v2 import ACCURACY_MIN_SAMPLES, AquaVisionPredictionModel
from scripts.compute_accuracy import _horizon_days


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class TestHorizonDays(unittest.TestCase):
    def test_seven_day_gap(self):
        gen = datetime(2026, 1, 1, tzinfo=timezone.utc)
        tgt = datetime(2026, 1, 8, tzinfo=timezone.utc)
        self.assertEqual(_horizon_days(gen, tgt), 7)

    def test_rounds_partial_days(self):
        gen = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        tgt = datetime(2026, 1, 4, 6, 0, tzinfo=timezone.utc)  # 2.75 days
        self.assertEqual(_horizon_days(gen, tgt), 3)

    def test_minimum_one_day(self):
        gen = datetime(2026, 1, 1, tzinfo=timezone.utc)
        tgt = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(_horizon_days(gen, tgt), 1)


class TestGetAccuracyByLead(unittest.TestCase):
    def test_validated_and_insufficient_samples(self):
        session = MagicMock()
        rows = [
            {"horizon": 3, "n": 10, "mape": 12.0},   # accuracy 0.88
            {"horizon": 7, "n": ACCURACY_MIN_SAMPLES - 1, "mape": 5.0},  # too few → None
            {"horizon": 14, "n": 20, "mape": 80.0},  # accuracy 0.20
        ]
        session.execute.return_value = FakeResult(rows)

        model = AquaVisionPredictionModel(session=session)
        out = model._get_accuracy_by_lead(1)

        self.assertAlmostEqual(out[3], 0.88)
        self.assertIsNone(out[7])
        self.assertAlmostEqual(out[14], 0.20)

    def test_mape_over_100_clamped_to_zero(self):
        session = MagicMock()
        session.execute.return_value = FakeResult(
            [{"horizon": 7, "n": 10, "mape": 150.0}]
        )
        model = AquaVisionPredictionModel(session=session)
        self.assertEqual(model._get_accuracy_by_lead(2)[7], 0.0)

    def test_no_session_returns_empty(self):
        model = AquaVisionPredictionModel(session=None)
        self.assertEqual(model._get_accuracy_by_lead(1), {})

    def test_db_error_returns_empty(self):
        session = MagicMock()
        session.execute.side_effect = RuntimeError("table missing")
        model = AquaVisionPredictionModel(session=session)
        self.assertEqual(model._get_accuracy_by_lead(1), {})


class TestComputeAccuracySql(unittest.TestCase):
    def test_scorer_targets_asset_forecasts_not_weekly(self):
        import inspect
        from scripts import compute_accuracy

        src = inspect.getsource(compute_accuracy.compute_accuracy)
        self.assertIn("water_asset_forecasts", src)
        self.assertNotIn("water_predictions_weekly", src)
        self.assertIn("data_origin = 'REAL'", src)


if __name__ == "__main__":
    unittest.main()
