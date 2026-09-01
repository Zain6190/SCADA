# tests/unit/test_sensor_replay.py
# Pure-logic tests for the BATADAL replay adapter. No network, no database.
import unittest
from datetime import timedelta

from infrastructure.ingestion.sensor_replay import (
    ANCHOR,
    TANK_MAPPINGS,
    TankMapping,
    _normalise_header,
    _to_float,
    batches,
    build_readings,
    column_range,
    rescale,
)


def _row(hour: int, level: float, flow: float) -> dict:
    """One BATADAL-shaped row. Note the leading spaces BATADAL ships with."""
    return {"DATETIME": f"01/01/14 {hour:02d}", "L_T1": str(level), " F_PU1": str(flow)}


class TestHelpers(unittest.TestCase):
    def test_normalise_header_strips_leading_spaces(self):
        self.assertEqual(_normalise_header({" F_PU1": "1", "L_T1 ": "2"}),
                         {"F_PU1": "1", "L_T1": "2"})

    def test_to_float_handles_blanks_and_junk(self):
        self.assertEqual(_to_float("3.5"), 3.5)
        self.assertIsNone(_to_float(""))
        self.assertIsNone(_to_float("   "))
        self.assertIsNone(_to_float(None))
        self.assertIsNone(_to_float("n/a"))

    def test_column_range(self):
        rows = [{"L_T1": "1.0"}, {"L_T1": "5.0"}, {"L_T1": ""}]
        self.assertEqual(column_range(rows, "L_T1"), (1.0, 5.0))
        self.assertIsNone(column_range(rows, "MISSING"))


class TestRescale(unittest.TestCase):
    def test_maps_endpoints_and_midpoint(self):
        self.assertAlmostEqual(rescale(1.0, 1.0, 5.0, 1355.0, 1545.0), 1355.0)
        self.assertAlmostEqual(rescale(5.0, 1.0, 5.0, 1355.0, 1545.0), 1545.0)
        self.assertAlmostEqual(rescale(3.0, 1.0, 5.0, 1355.0, 1545.0), 1450.0)

    def test_degenerate_source_range_returns_band_midpoint(self):
        # A flat column must not divide by zero.
        self.assertAlmostEqual(rescale(2.0, 2.0, 2.0, 100.0, 200.0), 150.0)


class TestBuildReadings(unittest.TestCase):
    def setUp(self):
        self.rows = [_row(h, 1.0 + h * 0.5, 100.0 + h * 10) for h in range(5)]
        self.mapping = TankMapping(
            "L_T1", 1, "Tarbela Reservoir", 1355.0, 1545.0,
            20_000, 250_000, "F_PU1", None,
        )

    def test_levels_land_inside_the_asset_band(self):
        readings = build_readings(self.rows, [self.mapping])
        levels = [r["water_level_ft"] for r in readings]
        self.assertEqual(min(levels), 1355.0)
        self.assertEqual(max(levels), 1545.0)
        for lvl in levels:
            # Must survive the ingest endpoint's range check.
            self.assertGreaterEqual(lvl, 0)
            self.assertLessEqual(lvl, 2000)

    def test_flows_are_rescaled_not_unit_converted(self):
        # Raw LPS->cusecs would give ~3.5 cusecs for Tarbela, which no threshold
        # can ever trigger. Rescaling must put flows in the asset's real band.
        readings = build_readings(self.rows, [self.mapping])
        flows = [r["inflow_cusecs"] for r in readings]
        self.assertEqual(min(flows), 20_000)
        self.assertEqual(max(flows), 250_000)

    def test_last_row_lands_on_anchor_and_steps_back_hourly(self):
        readings = build_readings(self.rows, [self.mapping])
        stamps = sorted({r["timestamp"] for r in readings})
        self.assertEqual(stamps[-1], ANCHOR.isoformat())
        self.assertEqual(stamps[0], (ANCHOR - timedelta(hours=4)).isoformat())

    def test_rebasing_is_deterministic(self):
        # Re-running must produce identical timestamps, so the endpoint's
        # (asset_id, observed_at, source_id) uniqueness yields duplicate
        # rejections rather than a second copy of the series.
        self.assertEqual(build_readings(self.rows, [self.mapping]),
                         build_readings(self.rows, [self.mapping]))

    def test_every_reading_is_marked_synthetic(self):
        for r in build_readings(self.rows, [self.mapping]):
            self.assertEqual(r["origin"], "SYNTHETIC")
            self.assertEqual(r["status"], "SIMULATED")

    def test_missing_tank_column_is_skipped_not_fatal(self):
        absent = TankMapping("L_T9", 4, "Nonexistent", 1.0, 2.0, 1.0, 2.0)
        self.assertEqual(build_readings(self.rows, [absent]), [])

    def test_days_limit_keeps_the_most_recent_rows(self):
        rows = [_row(h % 24, 1.0 + h, 100.0) for h in range(48)]
        readings = build_readings(rows, [self.mapping], days=1)
        self.assertEqual(len({r["timestamp"] for r in readings}), 24)


class TestMappingsAndBatching(unittest.TestCase):
    def test_batches_respect_the_endpoint_cap(self):
        chunks = list(batches(list(range(250)), size=100))
        self.assertEqual([len(c) for c in chunks], [100, 100, 50])

    def test_mappings_target_real_seeded_assets(self):
        # db/seed.sql seeds ids 1-11; 4 (Kalabagh) has no reservoir telemetry and
        # 9-11 are river stations fed by the USGS adapter instead.
        ids = [m.asset_id for m in TANK_MAPPINGS]
        self.assertEqual(len(ids), len(set(ids)), "duplicate asset_id in TANK_MAPPINGS")
        for asset_id in ids:
            self.assertIn(asset_id, range(1, 9))

    def test_bands_are_ordered(self):
        for m in TANK_MAPPINGS:
            self.assertLess(m.band_low_ft, m.band_high_ft, m.asset_name)
            self.assertLess(m.flow_low_cusecs, m.flow_high_cusecs, m.asset_name)


if __name__ == "__main__":
    unittest.main()
