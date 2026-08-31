# tests/unit/test_usgs_nwis.py
# Pure-logic tests for the USGS NWIS adapter. No network, no database.
import unittest
from datetime import date

from infrastructure.ingestion.usgs_nwis import (
    CHUNK_DAYS,
    CSV_COLUMNS,
    PARAM_DISCHARGE,
    PARAM_GAUGE_HT,
    SITE_MAPPINGS,
    SiteMapping,
    _chunk_ranges,
    build_readings,
    parse_timeseries,
)


def _payload(*series) -> dict:
    """Build an NWIS-shaped response from (param_code, [(ts, value), ...]) pairs."""
    return {
        "value": {
            "timeSeries": [
                {
                    "variable": {"variableCode": [{"value": code}]},
                    "values": [{"value": [{"dateTime": ts, "value": val}
                                          for ts, val in points]}],
                }
                for code, points in series
            ]
        }
    }


MAPPING = SiteMapping("06610000", 9, "Kabul @ Nowshera", "test proxy")


class TestParseTimeseries(unittest.TestCase):
    def test_merges_both_parameters_on_one_timestamp(self):
        payload = _payload(
            (PARAM_GAUGE_HT, [("2026-08-29T00:00:00.000-05:00", "13.05")]),
            (PARAM_DISCHARGE, [("2026-08-29T00:00:00.000-05:00", "27200")]),
        )
        series = parse_timeseries(payload)
        self.assertEqual(series, {
            "2026-08-29T00:00:00.000-05:00": {
                "water_level_ft": 13.05,
                "discharge_cusecs": 27200.0,
            }
        })

    def test_drops_the_nodata_sentinel(self):
        payload = _payload((PARAM_DISCHARGE, [("t1", "-999999"), ("t2", "500")]))
        series = parse_timeseries(payload)
        self.assertNotIn("t1", series)
        self.assertEqual(series["t2"]["discharge_cusecs"], 500.0)

    def test_ignores_unmapped_parameter_codes(self):
        payload = _payload(("00010", [("t1", "21.5")]))  # water temperature
        self.assertEqual(parse_timeseries(payload), {})

    def test_tolerates_empty_and_malformed_payloads(self):
        self.assertEqual(parse_timeseries({}), {})
        self.assertEqual(parse_timeseries({"value": {"timeSeries": []}}), {})
        self.assertEqual(parse_timeseries(_payload((PARAM_DISCHARGE, [("t", "n/a")]))), {})


class TestBuildReadings(unittest.TestCase):
    def test_units_pass_through_unconverted(self):
        # 00060 is already cusecs and 00065 is already feet - any scaling here
        # would be a bug.
        series = {"t1": {"water_level_ft": 13.05, "discharge_cusecs": 27200.0}}
        reading = build_readings(MAPPING, series)[0]
        self.assertEqual(reading["water_level_ft"], 13.05)
        self.assertEqual(reading["discharge_cusecs"], 27200.0)

    def test_marks_every_reading_synthetic_with_a_traceable_sensor_id(self):
        series = {"t1": {"discharge_cusecs": 100.0}}
        reading = build_readings(MAPPING, series)[0]
        self.assertEqual(reading["origin"], "SYNTHETIC")
        self.assertEqual(reading["status"], "SIMULATED")
        self.assertEqual(reading["sensor_id"], "USGS_06610000")
        self.assertEqual(reading["asset_id"], 9)

    def test_drops_levels_outside_the_ingest_range_check(self):
        series = {"t1": {"water_level_ft": 2500.0}, "t2": {"water_level_ft": -5.0}}
        self.assertEqual(build_readings(MAPPING, series), [])

    def test_skips_timestamps_with_no_usable_measurement(self):
        # The endpoint rejects a reading carrying no values at all.
        series = {"t1": {}, "t2": {"discharge_cusecs": 42.0}}
        readings = build_readings(MAPPING, series)
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0]["discharge_cusecs"], 42.0)

    def test_output_is_chronological(self):
        series = {f"t{i}": {"discharge_cusecs": float(i)} for i in (3, 1, 2)}
        stamps = [r["timestamp"] for r in build_readings(MAPPING, series)]
        self.assertEqual(stamps, sorted(stamps))


class TestChunkRanges(unittest.TestCase):
    def test_covers_the_span_without_gaps_or_overlap(self):
        windows = list(_chunk_ranges(date(2022, 1, 1), date(2024, 1, 1), days=180))
        self.assertEqual(windows[0][0], date(2022, 1, 1))
        self.assertEqual(windows[-1][1], date(2024, 1, 1))
        for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
            self.assertEqual(prev_end, next_start)

    def test_short_span_is_a_single_window(self):
        windows = list(_chunk_ranges(date(2026, 1, 1), date(2026, 1, 5), days=CHUNK_DAYS))
        self.assertEqual(windows, [(date(2026, 1, 1), date(2026, 1, 5))])

    def test_empty_span_yields_nothing(self):
        self.assertEqual(list(_chunk_ranges(date(2026, 1, 1), date(2026, 1, 1))), [])


class TestExportContract(unittest.TestCase):
    def test_csv_carries_provenance_and_site_identity(self):
        # Both matter: without site_no the reading is unattributable, and
        # without data_origin a real measurement can be mistaken for a
        # Pakistani observation downstream.
        for required in ("observed_at", "site_no", "data_origin", "source_authority"):
            self.assertIn(required, CSV_COLUMNS)

    def test_measurement_columns_present(self):
        self.assertIn("water_level_ft", CSV_COLUMNS)
        self.assertIn("discharge_cusecs", CSV_COLUMNS)


class TestSiteMappings(unittest.TestCase):
    def test_targets_river_stations_only(self):
        # Assets 9-11 are river_station rows in db/seed.sql. A USGS site IS a
        # gauge station, so mapping one onto a reservoir would mismatch semantics.
        for m in SITE_MAPPINGS:
            self.assertIn(m.asset_id, (9, 10, 11), m.asset_name)

    def test_no_duplicate_targets(self):
        ids = [m.asset_id for m in SITE_MAPPINGS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_site_numbers_keep_their_leading_zeros(self):
        # USGS site numbers are 8-character strings, not integers. Losing the
        # leading zero silently renames the site everywhere downstream.
        for m in SITE_MAPPINGS:
            self.assertIsInstance(m.site_no, str)
            self.assertEqual(len(m.site_no), 8, m.site_no)
            self.assertTrue(m.site_no.startswith("0"), m.site_no)


if __name__ == "__main__":
    unittest.main()
