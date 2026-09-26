# Pure-logic tests for Soft PLC interlocks. No database, no network.
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ot-runtime"))

from ot_runtime.interlocks import decide_interlocks, outflow_from_gate, slew_gate


class TestDecideInterlocks(unittest.TestCase):
    def test_comms_loss_holds_last_position(self):
        d = decide_interlocks(
            requested_cmd=90,
            gate_pos=40,
            local_level=266,
            prev_level=266,
            dt_hours=0.25,
            downstream_critical=False,
            comms_down=True,
        )
        self.assertTrue(d.freeze)
        self.assertEqual(d.effective_cmd, 40)
        self.assertIn("comms_loss_hold_last_output", d.reasons)

    def test_jam_sets_fault_and_freezes(self):
        d = decide_interlocks(
            requested_cmd=80,
            gate_pos=40,
            local_level=266,
            prev_level=266,
            dt_hours=0.25,
            downstream_critical=False,
            jammed=True,
        )
        self.assertTrue(d.fault)
        self.assertTrue(d.freeze)
        self.assertEqual(d.effective_cmd, 40)
        self.assertIn("command_feedback_divergence", d.reasons)

    def test_downstream_critical_blocks_further_open(self):
        d = decide_interlocks(
            requested_cmd=80,
            gate_pos=40,
            local_level=266,
            prev_level=266,
            dt_hours=0.25,
            downstream_critical=True,
        )
        self.assertEqual(d.effective_cmd, 40)
        self.assertIn("downstream_critical_no_further_open", d.reasons)

    def test_downstream_critical_allows_close(self):
        d = decide_interlocks(
            requested_cmd=20,
            gate_pos=40,
            local_level=266,
            prev_level=266,
            dt_hours=0.25,
            downstream_critical=True,
        )
        self.assertEqual(d.effective_cmd, 20)

    def test_rapid_rise_holds_minimum_opening(self):
        d = decide_interlocks(
            requested_cmd=0,
            gate_pos=10,
            local_level=267.5,
            prev_level=266.0,
            dt_hours=0.25,  # 1.5 ft in 0.25h => 36 ft / 6h
            downstream_critical=False,
        )
        self.assertEqual(d.effective_cmd, 15.0)
        self.assertIn("rapid_rise_hold_minimum_opening", d.reasons)


class TestSlewAndRating(unittest.TestCase):
    def test_slew_is_rate_limited(self):
        moved = slew_gate(40, 100, dt_hours=0.25, max_slew_pct_per_hour=30)
        self.assertAlmostEqual(moved, 47.5)

    def test_slew_jammed_does_not_move(self):
        self.assertEqual(slew_gate(40, 100, dt_hours=1, jammed=True), 40)

    def test_outflow_scales_with_opening_and_head(self):
        closed = outflow_from_gate(0, 268, 255, 268, 250_000)
        half = outflow_from_gate(50, 268, 255, 268, 250_000)
        self.assertEqual(closed, 0)
        self.assertGreater(half, 0)
        self.assertLess(half, 250_000)
