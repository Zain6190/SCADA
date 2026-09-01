# tests/unit/test_channel_condition.py
# Module 6.4 condition classification. Pure logic - no database, no network.
import unittest
from datetime import date, timedelta

from domain.services.channel_condition_service import (
    CONDITION_DRY,
    CONDITION_FLOWING,
    CONDITION_LOW,
    CONDITION_REDUCED,
    CONDITION_UNKNOWN,
    MIN_BASELINE_SAMPLES,
    assess_gauge_series,
    change_pct,
    classify_gauge,
    classify_ndwi,
    needs_attention,
    rolling_baseline,
    worst_condition,
)


class TestBaseline(unittest.TestCase):
    def test_median_not_mean(self):
        # Rotational closures put zeros in the history. A mean would be dragged
        # down until a genuinely dry week looked normal.
        history = [8000, 8000, 8000, 8000, 0, 0]
        self.assertEqual(rolling_baseline(history), 8000.0)

    def test_too_few_samples_gives_no_baseline(self):
        self.assertIsNone(rolling_baseline([8000] * (MIN_BASELINE_SAMPLES - 1)))
        self.assertIsNotNone(rolling_baseline([8000] * MIN_BASELINE_SAMPLES))

    def test_ignores_missing_readings(self):
        self.assertEqual(rolling_baseline([100, None, 100, 100, 100]), 100.0)


class TestChangePct(unittest.TestCase):
    def test_shortfall_is_negative(self):
        self.assertEqual(change_pct(4000, 8000), -50.0)

    def test_surplus_is_positive(self):
        self.assertEqual(change_pct(12000, 8000), 50.0)

    def test_no_baseline_or_zero_baseline_gives_none(self):
        self.assertIsNone(change_pct(4000, None))
        self.assertIsNone(change_pct(4000, 0))


class TestClassifyGauge(unittest.TestCase):
    def test_zero_discharge_is_dry_even_without_baseline(self):
        # Muzafarghar Canal reads 0 Cs on three days of the archive. That is an
        # observation, not an inference, and must classify regardless.
        self.assertEqual(classify_gauge(0, None), CONDITION_DRY)
        self.assertEqual(classify_gauge(0, 8000), CONDITION_DRY)

    def test_bands(self):
        self.assertEqual(classify_gauge(8000, 8000), CONDITION_FLOWING)
        self.assertEqual(classify_gauge(5000, 8000), CONDITION_REDUCED)   # -37.5%
        self.assertEqual(classify_gauge(2000, 8000), CONDITION_LOW)       # -75%
        self.assertEqual(classify_gauge(12000, 8000), CONDITION_FLOWING)  # surplus

    def test_band_boundaries(self):
        self.assertEqual(classify_gauge(6000, 8000), CONDITION_REDUCED)   # exactly -25%
        self.assertEqual(classify_gauge(3200, 8000), CONDITION_LOW)       # exactly -60%

    def test_flow_without_baseline_is_unknown_not_flowing(self):
        # Claiming FLOWING with nothing to compare against would be a guess.
        self.assertEqual(classify_gauge(8000, None), CONDITION_UNKNOWN)

    def test_missing_reading_is_unknown(self):
        self.assertEqual(classify_gauge(None, 8000), CONDITION_UNKNOWN)


class TestClassifyNdwi(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(classify_ndwi(0.02), CONDITION_DRY)
        self.assertEqual(classify_ndwi(0.25), CONDITION_LOW)
        self.assertEqual(classify_ndwi(0.50), CONDITION_REDUCED)
        self.assertEqual(classify_ndwi(0.90), CONDITION_FLOWING)

    def test_missing_is_unknown(self):
        self.assertEqual(classify_ndwi(None), CONDITION_UNKNOWN)


class TestRollups(unittest.TestCase):
    def test_worst_condition_wins(self):
        self.assertEqual(
            worst_condition([CONDITION_FLOWING, CONDITION_DRY, CONDITION_REDUCED]),
            CONDITION_DRY,
        )

    def test_unknown_is_not_treated_as_severe(self):
        self.assertEqual(
            worst_condition([CONDITION_UNKNOWN, CONDITION_REDUCED]), CONDITION_REDUCED
        )

    def test_all_unknown_stays_unknown(self):
        self.assertEqual(worst_condition([CONDITION_UNKNOWN]), CONDITION_UNKNOWN)
        self.assertEqual(worst_condition([]), CONDITION_UNKNOWN)

    def test_only_low_and_dry_raise_alerts(self):
        self.assertTrue(needs_attention(CONDITION_DRY))
        self.assertTrue(needs_attention(CONDITION_LOW))
        self.assertFalse(needs_attention(CONDITION_REDUCED))
        self.assertFalse(needs_attention(CONDITION_FLOWING))
        self.assertFalse(needs_attention(CONDITION_UNKNOWN))


class TestAssessSeries(unittest.TestCase):
    def setUp(self):
        start = date(2026, 7, 6)
        self.weeks = [start + timedelta(weeks=i) for i in range(8)]

    def test_baseline_never_uses_future_weeks(self):
        # Week 0 has no history, so it cannot be judged - if the series were
        # assessed as a whole, a later collapse would leak backwards.
        readings = list(zip(self.weeks, [8000] * 7 + [0]))
        rows = assess_gauge_series(readings)
        self.assertIsNone(rows[0]["baseline"])
        self.assertEqual(rows[0]["sample_count"], 0)
        self.assertEqual(rows[0]["condition"], CONDITION_UNKNOWN)

    def test_detects_a_collapse_once_a_baseline_exists(self):
        readings = list(zip(self.weeks, [8000] * 7 + [0]))
        rows = assess_gauge_series(readings)
        self.assertEqual(rows[-1]["condition"], CONDITION_DRY)
        self.assertEqual(rows[-1]["baseline"], 8000.0)

    def test_steady_canal_reads_flowing_after_warmup(self):
        rows = assess_gauge_series(list(zip(self.weeks, [8000] * 8)))
        self.assertTrue(all(r["condition"] == CONDITION_FLOWING
                            for r in rows[MIN_BASELINE_SAMPLES:]))

    def test_every_row_is_stamped_with_its_method(self):
        rows = assess_gauge_series(list(zip(self.weeks, [8000] * 8)))
        self.assertTrue(all(r["method"] == "GAUGE_DISCHARGE" for r in rows))

    def test_missing_weeks_do_not_pollute_the_baseline(self):
        readings = list(zip(self.weeks, [8000, 8000, None, 8000, 8000, 8000, 8000, 8000]))
        rows = assess_gauge_series(readings)
        self.assertEqual(rows[2]["condition"], CONDITION_UNKNOWN)
        self.assertEqual(rows[-1]["baseline"], 8000.0)


if __name__ == "__main__":
    unittest.main()
