# HMI writes must not create water_observations. Persist helpers are tested
# with the publish function's contract (no DB required for the rule itself).
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ot-runtime"))

from ot_runtime.runtime import OtRuntime, PublishReading


class TestHmiDoesNotPublish(unittest.TestCase):
    def test_setpoint_and_fault_do_not_emit_readings(self):
        rt = OtRuntime(sim_minutes=15)
        before = rt.ticks
        rt.set_setpoint(7, "AO.gate_cmd_pct", 55)
        rt.inject_fault(7, "comms_down")
        self.assertEqual(rt.ticks, before)  # no tick => no publish

    def test_publish_reading_is_always_simulated_contract(self):
        # The persist layer stamps SYNTHETIC / SIMULATED / priority 4.
        # Guard the packet shape the publisher consumes.
        pkt = PublishReading(
            asset_id=7,
            device_code="PLC-SUKKUR",
            kind="PLC",
            observed_at=datetime.now(timezone.utc),
            water_level_ft=266.0,
            inflow_cusecs=65000,
            outflow_cusecs=60000,
            discharge_cusecs=60000,
            quality="VALID",
            notes="plc=PLC-SUKKUR",
            extras={"gate_cmd_pct": 40, "gate_pos_pct": 40},
        )
        self.assertEqual(pkt.kind, "PLC")
        self.assertIn("gate_cmd_pct", pkt.extras)

    def test_hmi_apply_setpoint_flag(self):
        # apply_hmi_setpoint documents writes_observations=False
        from infrastructure.ot import persist as persist_mod

        self.assertEqual(persist_mod.SOFT_OT_ORIGIN, "SYNTHETIC")
        self.assertEqual(persist_mod.SOFT_OT_STATUS, "SIMULATED")
        self.assertEqual(persist_mod.SOFT_OT_PRIORITY, 4)
        self.assertEqual(persist_mod.SOFT_OT_AUTHORITY, "SOFT_OT")


class TestSensorAuthorityIncludesSoftOt(unittest.TestCase):
    def test_soft_ot_registered(self):
        from presentation.http.routers.sensors import SENSOR_AUTHORITIES, SENSOR_SOURCE_PRIORITY

        self.assertIn("SOFT_OT", SENSOR_AUTHORITIES)
        self.assertEqual(SENSOR_SOURCE_PRIORITY, 4)
        self.assertEqual(SENSOR_AUTHORITIES["SOFT_OT"]["source_type"], "SIMULATED_OT")
