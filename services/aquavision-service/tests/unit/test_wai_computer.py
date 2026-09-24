"""Unit tests for real-time WAI computer (no DB required for pure helpers)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from ml.models.wai_computer import (
    WEIGHTS,
    _percentile_rank,
    compute_realtime_wai,
    get_wai_for_prediction,
)


class TestPercentileRank(unittest.TestCase):
    def test_empty_history_returns_none(self):
        self.assertIsNone(_percentile_rank([], 100.0))

    def test_current_is_max(self):
        self.assertEqual(_percentile_rank([1.0, 2.0, 3.0], 3.0), 100.0)

    def test_current_is_min(self):
        self.assertEqual(_percentile_rank([1.0, 2.0, 3.0], 1.0), 100.0 / 3)

    def test_midrank(self):
        rank = _percentile_rank([10.0, 20.0, 30.0, 40.0], 25.0)
        self.assertEqual(rank, 50.0)


class TestComputeRealtimeWai(unittest.TestCase):
    def _session_with_rows(self, rows):
        session = MagicMock()
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        session.execute.return_value = result
        return session

    def test_none_session(self):
        self.assertEqual(compute_realtime_wai(None, 1), (None, None, None))

    def test_no_rows_returns_none(self):
        session = self._session_with_rows([])
        self.assertEqual(compute_realtime_wai(session, 1), (None, None, None))

    def test_no_flow_returns_none(self):
        rows = [
            {"observed_at": datetime.utcnow(), "flow": None, "storage_percent": 50},
        ]
        session = self._session_with_rows(rows)
        self.assertEqual(compute_realtime_wai(session, 1), (None, None, None))

    def test_score_in_range_with_rising_flow(self):
        base = datetime(2026, 9, 1)
        rows = []
        for i in range(30):
            rows.append(
                {
                    "observed_at": base + timedelta(days=i),
                    "flow": 100.0 + i * 5.0,  # rising
                    "storage_percent": 60.0 if i == 29 else None,
                }
            )
        session = self._session_with_rows(rows)
        wai, rain, et = compute_realtime_wai(session, 1)
        self.assertIsNotNone(wai)
        self.assertGreaterEqual(wai, 0.0)
        self.assertLessEqual(wai, 100.0)
        # Rising flow + mid storage should not be catastrophic
        self.assertGreater(wai, 30.0)
        self.assertIsNone(rain)
        self.assertIsNone(et)

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)


class TestGetWaiForPrediction(unittest.TestCase):
    def test_prefers_realtime(self):
        session = MagicMock()
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            {"observed_at": datetime.utcnow(), "flow": 50.0, "storage_percent": None},
            {"observed_at": datetime.utcnow(), "flow": 60.0, "storage_percent": None},
        ]
        session.execute.return_value = result
        wai, _, _ = get_wai_for_prediction(session, 1, stale_indicator_wai=11.0)
        self.assertIsNotNone(wai)
        self.assertNotEqual(wai, 11.0)

    def test_falls_back_to_stale_when_no_history(self):
        session = MagicMock()
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        session.execute.return_value = result
        wai, rain, et = get_wai_for_prediction(session, 1, stale_indicator_wai=42.5)
        self.assertEqual(wai, 42.5)
        self.assertIsNone(rain)
        self.assertIsNone(et)

    def test_returns_none_when_nothing_available(self):
        session = MagicMock()
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        session.execute.return_value = result
        self.assertEqual(
            get_wai_for_prediction(session, 1, stale_indicator_wai=None),
            (None, None, None),
        )


if __name__ == "__main__":
    unittest.main()
