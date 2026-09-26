# Soft OT replay against an official day. No database and no IRSA write.
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "ot-runtime"))

from ml.features.feature_engineering import usable_for_training
from ot_runtime.runtime import OtRuntime
from ot_runtime.series import (
    OfficialDay,
    barrage_release,
    canal_shortfall_note,
    flood_discharge,
    ot_alert_candidates,
)


def _day(asset_id: int, observed: date, **kwargs) -> OfficialDay:
    base = dict(
        observed_on=observed,
        asset_id=asset_id,
        level_ft=260.0,
        inflow_cusecs=100_000.0,
        outflow_cusecs=70_000.0,
        discharge_cusecs=70_000.0,
        canal_offtake_cusecs=20_000.0,
        source_authority="IRSA",
        source_url="http://pakirsa.gov.pk/Doc/Data01-09-2026.pdf",
    )
    base.update(kwargs)
    return OfficialDay(**base)


class TestSeriesReplay(unittest.TestCase):
    def test_track_matches_official_and_leaves_the_day_unchanged(self):
        observed = date(2026, 9, 1)
        day = _day(7, observed)
        before = (day.level_ft, day.outflow_cusecs, day.source_authority)
        runtime = OtRuntime(sim_minutes=15)
        runtime.load_series([day])
        result = runtime.tick(now=datetime(2026, 9, 1, 18, tzinfo=timezone.utc), advance=False)
        packet = next(row for row in result.published if row.asset_id == 7)
        self.assertEqual(packet.water_level_ft, 260.0)
        self.assertEqual(packet.outflow_cusecs, 70_000.0)
        self.assertEqual(packet.data_origin, "OFFICIAL_REPLAY")
        self.assertEqual(packet.extras["source_authority"], "SOFT_OT")
        self.assertIsNotNone(runtime.plcs[7].gate_cmd_pct)
        self.assertEqual((day.level_ft, day.outflow_cusecs, day.source_authority), before)

    def test_setpoint_uses_scenario_discharge_for_flood(self):
        observed = date(2026, 9, 1)
        day = _day(7, observed)
        runtime = OtRuntime(sim_minutes=15)
        runtime.load_series([day])
        runtime.plcs[7].gate_pos_pct = 100
        runtime.set_setpoint(7, "AO.gate_cmd_pct", 100)
        result = runtime.tick(now=datetime(2026, 9, 1, 18, tzinfo=timezone.utc), advance=False)
        packet = next(row for row in result.published if row.asset_id == 7)
        self.assertEqual(runtime.modes[7], "SCENARIO")
        self.assertEqual(packet.data_origin, "SCENARIO")
        discharge, source = flood_discharge("SCENARIO", day.discharge_cusecs, packet.discharge_cusecs)
        self.assertEqual(source, "SOFT_OT_SCENARIO")
        self.assertEqual(discharge, packet.discharge_cusecs)
        self.assertEqual(packet.outflow_cusecs, 80_000.0)

    def test_downstream_critical_refuses_further_open(self):
        observed = date(2026, 9, 1)
        runtime = OtRuntime(sim_minutes=15)
        runtime.load_series([
            _day(4, observed, level_ft=635, inflow_cusecs=80_000, outflow_cusecs=60_000, discharge_cusecs=60_000, canal_offtake_cusecs=0),
            _day(5, observed, level_ft=507, inflow_cusecs=60_000, outflow_cusecs=60_000, discharge_cusecs=60_000, canal_offtake_cusecs=0),
        ])
        held = runtime.plcs[4].gate_pos_pct
        runtime.set_setpoint(4, "AO.gate_cmd_pct", 90)
        result = runtime.tick(now=datetime(2026, 9, 1, 18, tzinfo=timezone.utc), advance=False)
        packet = next(row for row in result.published if row.asset_id == 4)
        self.assertIn("downstream_critical_no_further_open", packet.extras["reasons"])
        self.assertLessEqual(runtime.plcs[4].gate_pos_pct, held + 0.01)

    def test_training_drops_soft_ot_rows(self):
        self.assertFalse(usable_for_training("SCENARIO", "SOFT_OT"))
        self.assertFalse(usable_for_training("OFFICIAL_REPLAY", "SOFT_OT"))
        self.assertFalse(usable_for_training("REAL", "SOFT_OT"))
        self.assertTrue(usable_for_training("REAL", "IRSA"))

    def test_restart_restores_cursor_and_command(self):
        first = date(2026, 9, 1)
        second = date(2026, 9, 2)
        days = [_day(7, first), _day(7, second, outflow_cusecs=72_000, discharge_cusecs=72_000)]
        runtime = OtRuntime(sim_minutes=15)
        runtime.load_series(days)
        runtime.tick(now=datetime(2026, 9, 2, 12, tzinfo=timezone.utc), advance=True)
        runtime.set_setpoint(7, "AO.gate_cmd_pct", 80)
        state = runtime.export_state()
        restored = OtRuntime(sim_minutes=15)
        restored.load_series(days)
        restored.restore_state(state)
        self.assertEqual(restored.cursor, second)
        self.assertEqual(restored.plcs[7].gate_cmd_pct, 80)
        self.assertEqual(restored.modes[7], "SCENARIO")

    def test_routes_use_official_discharge(self):
        first = date(2026, 9, 1)
        second = date(2026, 9, 2)
        runtime = OtRuntime(sim_minutes=15)
        runtime.load_series([
            _day(1, first, level_ft=1500, inflow_cusecs=400_000, outflow_cusecs=400_000, discharge_cusecs=400_000, canal_offtake_cusecs=0),
            _day(1, second, level_ft=1500, inflow_cusecs=400_000, outflow_cusecs=400_000, discharge_cusecs=400_000, canal_offtake_cusecs=0),
        ], cursor=second)
        seeded = False
        for upstream, downstream, buf in runtime.plant._routes:
            if upstream == 1 and downstream == 4:
                self.assertIn(400_000, list(buf))
                seeded = True
        self.assertTrue(seeded)

    def test_stale_when_official_day_is_old(self):
        observed = date(2026, 8, 1)
        runtime = OtRuntime(sim_minutes=15)
        runtime.load_series([
            _day(9, observed, level_ft=12, inflow_cusecs=20_000, outflow_cusecs=19_000, discharge_cusecs=19_000, canal_offtake_cusecs=0),
        ])
        now = datetime(2026, 8, 1, 12, tzinfo=timezone.utc) + timedelta(hours=40)
        result = runtime.tick(now=now, advance=False)
        packet = next(row for row in result.published if row.asset_id == 9)
        self.assertEqual(packet.quality, "STALE")

    def test_alert_candidates_do_not_replace_irsa_type(self):
        rows = ot_alert_candidates([{
            "asset_id": 7,
            "device_code": "PLC-SUKKUR",
            "mode": "SCENARIO",
            "official_on": "2026-09-01",
            "interlock_reasons": ["downstream_critical_no_further_open"],
            "official_outflow": 70000,
            "scenario_outflow": 80000,
        }])
        kinds = {row["alert_type"] for row in rows if row.get("active")}
        self.assertEqual(kinds, {"OT_INTERLOCK", "OT_SCENARIO"})
        self.assertIsNone(canal_shortfall_note(100, 99, date(2026, 9, 1)))
        self.assertIsNotNone(canal_shortfall_note(100, 50, date(2026, 9, 1)))


if __name__ == "__main__":
    unittest.main()
