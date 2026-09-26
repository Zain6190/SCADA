# Downstream impact engine orchestration: honest null travel times,
# impact lookup by asset pair, furthest/total derived from known arrivals.
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from infrastructure.impact.downstream_engine import DownstreamImpactEngine


def _seg(order: int, up_id: int, dst_id: int, dst_name: str, river: str = "Indus") -> dict:
    return {
        "river_segment_id": 100 + order,
        "upstream_asset_id": up_id,
        "downstream_asset_id": dst_id,
        "segment_order": order,
        "river_name": river,
        "upstream_name": f"Asset {up_id}",
        "downstream_name": dst_name,
        "distance_km": 50.0,
        "confidence": "MEDIUM",
    }


class TestCalculateWithTravelTimes(unittest.TestCase):
    def _engine(self, segments, travel_times, impacts):
        engine = DownstreamImpactEngine(MagicMock())
        engine._get_asset_name = lambda aid: "Tarbela Reservoir"
        engine._get_downstream_chain = lambda aid: segments
        engine._get_travel_time = lambda seg_id, flow: travel_times.get(seg_id)
        engine._get_impact_data = lambda src, dst: impacts.get((src, dst), {})
        return engine

    def test_known_travel_times_produce_arrivals_and_totals(self):
        segments = [_seg(1, 1, 4, "Kalabagh"), _seg(2, 4, 5, "Taunsa")]
        engine = self._engine(
            segments,
            {101: 12.0, 102: 24.0},
            {(1, 4): {"affected_population_est": 1000}, (4, 5): {"affected_population_est": 500}},
        )
        release = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
        result = engine.calculate(1, 400000.0, release)

        self.assertEqual(len(result.segments), 2)
        first, second = result.segments
        self.assertEqual(first.travel_time_hours, 12.0)
        self.assertEqual(first.arrival_time, datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(second.arrival_time, datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(result.total_population_exposed, 1500)
        self.assertEqual(result.furthest_asset, "Taunsa")
        self.assertEqual(result.total_travel_hours, 36.0)

    def test_missing_travel_model_yields_null_arrival_and_honest_notes(self):
        segments = [_seg(1, 1, 4, "Kalabagh"), _seg(2, 4, 5, "Taunsa")]
        engine = self._engine(
            segments,
            {101: 12.0, 102: None},
            {(1, 4): {}, (4, 5): {"affected_population_est": 500}},
        )
        release = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
        result = engine.calculate(1, 400000.0, release)

        first, second = result.segments
        self.assertEqual(first.travel_time_hours, 12.0)
        self.assertIsNotNone(first.arrival_time)
        self.assertIsNone(second.travel_time_hours)
        self.assertIsNone(second.arrival_time)
        self.assertEqual(second.confidence, "LOW")
        self.assertIn("No travel-time model", second.notes)
        self.assertNotIn("No travel-time model", first.notes)
        self.assertEqual(result.total_population_exposed, 500)
        self.assertEqual(result.furthest_asset, "Kalabagh")
        self.assertEqual(result.furthest_arrival, first.arrival_time)
        self.assertEqual(result.total_travel_hours, 12.0)

    def test_all_arrivals_unknown_leaves_totals_unset(self):
        segments = [_seg(1, 1, 4, "Kalabagh")]
        engine = self._engine(segments, {101: None}, {(1, 4): {}})
        release = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
        result = engine.calculate(1, 400000.0, release)

        self.assertIsNone(result.segments[0].arrival_time)
        self.assertIsNone(result.furthest_arrival)
        self.assertIsNone(result.total_travel_hours)
        self.assertEqual(result.furthest_asset, "Kalabagh")

    def test_impact_lookup_uses_asset_pair_not_segment_id(self):
        segments = [_seg(1, 1, 4, "Kalabagh")]
        seen = []

        engine = DownstreamImpactEngine(MagicMock())
        engine._get_asset_name = lambda aid: "Tarbela Reservoir"
        engine._get_downstream_chain = lambda aid: segments
        engine._get_travel_time = lambda seg_id, flow: 12.0

        def record(src, dst):
            seen.append((src, dst))
            return {}

        engine._get_impact_data = record
        release = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
        engine.calculate(1, 400000.0, release)

        self.assertEqual(seen, [(1, 4)])


if __name__ == "__main__":
    unittest.main()
