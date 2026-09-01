# tests/unit/test_plc_models.py
# Pure-logic tests for the PLC trainer. No network, no database, no CSV.
import unittest

import numpy as np
import pandas as pd

from ml.train_plc_models import (
    _state_vector,
    build_divergence_features,
    classify_signals,
    compute_spreads,
    find_command_feedback_pairs,
    score_divergence,
)


class TestSignalClassification(unittest.TestCase):
    def test_binary_tags_are_discrete_continuous_are_not(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2022-08-12", periods=6, freq="s"),
            "P1_PP01AR": [0, 1, 1, 0, 1, 0],          # DI - pump run feedback
            "P3_LH01":   [0, 0, 0, 0, 0, 0],          # DI - constant limit switch
            "P1_LIT01":  [1.0, 2.5, 3.1, 4.7, 5.2, 6.0],  # AI - level transmitter
        })
        c = classify_signals(df)
        self.assertIn("P1_PP01AR", c["discrete"])
        self.assertIn("P3_LH01", c["discrete"])
        self.assertIn("P1_LIT01", c["continuous"])

    def test_timestamp_is_never_classified(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2022-08-12", periods=3, freq="s"),
            "P1_LIT01": [1.0, 2.0, 3.0],
        })
        c = classify_signals(df)
        self.assertNotIn("timestamp", c["discrete"] + c["continuous"])


class TestCommandFeedbackPairing(unittest.TestCase):
    def test_matches_valve_demand_to_position_and_pump_demand_to_run(self):
        cols = ["P1_FCV01D", "P1_FCV01Z", "P1_PP01AD", "P1_PP01AR", "P1_LIT01"]
        self.assertEqual(
            find_command_feedback_pairs(cols),
            [("P1_FCV01D", "P1_FCV01Z"), ("P1_PP01AD", "P1_PP01AR")],
        )

    def test_demand_tag_with_no_feedback_is_not_paired(self):
        # P1_SOL01D is a solenoid command with no feedback tag - pairing it
        # against an unrelated column would invent a control loop.
        self.assertEqual(find_command_feedback_pairs(["P1_SOL01D", "P1_LIT01"]), [])

    def test_non_demand_tags_are_ignored(self):
        self.assertEqual(find_command_feedback_pairs(["P1_FCV01Z", "P1_LIT01"]), [])


class TestDivergenceScaling(unittest.TestCase):
    """The fit/score scale bug: recomputing spread per-frame made the learned
    band meaningless and flagged 99.9% of rows."""

    def setUp(self):
        self.pairs = [("P1_FCV01D", "P1_FCV01Z")]
        self.fit_df = pd.DataFrame({
            "P1_FCV01D": [10.0, 20.0, 30.0, 40.0],
            "P1_FCV01Z": [10.1, 20.1, 29.9, 40.2],
        })
        # Same relationship, much wider operating range -> different native std.
        self.score_df = pd.DataFrame({
            "P1_FCV01D": [10.0, 50.0, 90.0, 130.0],
            "P1_FCV01Z": [10.1, 50.1, 89.9, 130.2],
        })

    def test_supplied_spreads_are_used_verbatim(self):
        spreads = {"div_P1_FCV01D": 100.0}
        feats = build_divergence_features(self.fit_df, self.pairs, spreads)
        expected = (self.fit_df["P1_FCV01D"] - self.fit_df["P1_FCV01Z"]) / 100.0
        np.testing.assert_allclose(feats["div_P1_FCV01D"].to_numpy(),
                                   expected.to_numpy(), rtol=1e-9)

    def test_without_shared_spreads_the_two_frames_disagree(self):
        # Documents the bug: independent scaling puts fit and score on different
        # axes even though the underlying residual is identical.
        a = build_divergence_features(self.fit_df, self.pairs)
        b = build_divergence_features(self.score_df, self.pairs)
        self.assertNotAlmostEqual(float(a["div_P1_FCV01D"].iloc[0]),
                                  float(b["div_P1_FCV01D"].iloc[0]), places=3)

    def test_with_shared_spreads_identical_residuals_map_identically(self):
        spreads = compute_spreads(self.fit_df, self.pairs)
        a = build_divergence_features(self.fit_df, self.pairs, spreads)
        b = build_divergence_features(self.score_df, self.pairs, spreads)
        # Row 0 has the same raw residual (-0.1) in both frames.
        self.assertAlmostEqual(float(a["div_P1_FCV01D"].iloc[0]),
                               float(b["div_P1_FCV01D"].iloc[0]), places=9)


class TestDivergenceScoring(unittest.TestCase):
    def setUp(self):
        self.pairs = [("P1_PP01AD", "P1_PP01AR")]
        self.stats = {"div_P1_PP01AD": {"lo": -0.1, "hi": 0.1, "std": 0.05}}
        self.spreads = {"div_P1_PP01AD": 1.0}

    def _frame(self, cmd, fb):
        return pd.DataFrame({"P1_PP01AD": cmd, "P1_PP01AR": fb})

    def test_feedback_tracking_command_is_not_flagged(self):
        df = self._frame([1.0] * 20, [1.0] * 20)
        flags = score_divergence(df, self.pairs, self.stats, self.spreads)
        self.assertFalse(flags.any())

    def test_sustained_divergence_is_flagged(self):
        # Pump commanded on for 20s but feedback says it never ran.
        df = self._frame([1.0] * 20, [0.0] * 20)
        flags = score_divergence(df, self.pairs, self.stats, self.spreads, persist=5)
        self.assertTrue(flags.any())

    def test_single_sample_glitch_is_not_flagged(self):
        # One bad scan is an artefact, not an actuator fault.
        cmd = [1.0] * 20
        fb = [1.0] * 20
        fb[7] = 0.0
        flags = score_divergence(self._frame(cmd, fb), self.pairs, self.stats,
                                 self.spreads, persist=5)
        self.assertFalse(flags.any())


class TestStateVector(unittest.TestCase):
    def test_float_encoded_binaries_do_not_raise(self):
        # HAI stores some binary tags as 1.0 rather than 1; a direct int cast
        # raised TypeError on object-dtype columns.
        df = pd.DataFrame({"a": [0.0, 1.0], "b": [1, 0]})
        self.assertEqual(list(_state_vector(df, ["a", "b"])), ["0|1", "1|0"])

    def test_missing_values_become_their_own_state(self):
        # A dropout must not silently merge with the 0 state.
        df = pd.DataFrame({"a": [0.0, np.nan], "b": [1, 1]})
        states = list(_state_vector(df, ["a", "b"]))
        self.assertEqual(states[0], "0|1")
        self.assertEqual(states[1], "-1|1")
        self.assertNotEqual(states[0], states[1])

    def test_non_numeric_is_coerced_rather_than_raising(self):
        df = pd.DataFrame({"a": ["0", "bad"], "b": [1, 1]})
        self.assertEqual(list(_state_vector(df, ["a", "b"])), ["0|1", "-1|1"])


if __name__ == "__main__":
    unittest.main()
