# Soft RTU store-and-forward + plant routing. No database.
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ot-runtime"))

from ot_runtime.catalog import DEVICE_BY_CODE
from ot_runtime.plant import VirtualPlant
from ot_runtime.rtu import SoftRTU
from ot_runtime.runtime import OtRuntime


class TestSoftRtu(unittest.TestCase):
    def setUp(self):
        self.rtu = SoftRTU(DEVICE_BY_CODE["RTU-NOWSHERA"])
        self.ai = {
            "level_ft": 12.0,
            "inflow_cusecs": 20000,
            "outflow_cusecs": 19000,
            "discharge_cusecs": 19000,
        }
        self.t0 = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

    def test_normal_scan_publishes(self):
        out = self.rtu.scan(self.ai, now=self.t0)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].quality, "VALID")
        self.assertTrue(out[0].comms_ok)

    def test_comms_down_buffers_then_flushes(self):
        self.rtu.inject_fault("comms_down")
        self.assertEqual(self.rtu.scan(self.ai, now=self.t0), [])
        self.assertEqual(len(self.rtu.buffer), 1)
        later = self.t0 + timedelta(hours=7)
        self.rtu.scan(self.ai, now=later)
        self.assertEqual(self.rtu.buffer[0].quality, "STALE")
        self.rtu.clear_faults()
        flushed = self.rtu.scan(self.ai, now=later + timedelta(minutes=15))
        self.assertGreaterEqual(len(flushed), 2)
        self.assertTrue(any(p.quality == "STALE" for p in flushed))

    def test_sensor_stuck_is_suspect(self):
        self.rtu.inject_fault("sensor_stuck")
        first = self.rtu.scan(self.ai, now=self.t0)[0]
        moved = dict(self.ai, level_ft=18.0)
        second = self.rtu.scan(moved, now=self.t0 + timedelta(minutes=15))[0]
        self.assertEqual(first.water_level_ft, second.water_level_ft)
        self.assertEqual(second.quality, "SUSPECT")


class TestPlantAndRuntime(unittest.TestCase):
    def test_all_eleven_devices_tick(self):
        rt = OtRuntime(sim_minutes=15)
        result = rt.tick()
        self.assertEqual(len(result.devices), 11)
        self.assertGreaterEqual(len(result.published), 5)  # RTUs + PLCs publish

    def test_setpoint_is_ao_only(self):
        rt = OtRuntime(sim_minutes=15)
        rt.set_setpoint(7, "AO.gate_cmd_pct", 70)
        self.assertEqual(rt.plcs[7].gate_cmd_pct, 70)
        with self.assertRaises(ValueError):
            rt.set_setpoint(7, "AI.level_ft", 10)
        with self.assertRaises(ValueError):
            rt.set_setpoint(9, "AO.gate_cmd_pct", 50)  # Nowshera is RTU

    def test_plant_routes_upstream_to_downstream(self):
        plant = VirtualPlant(sim_minutes=15)
        before = plant.tanks[4].inflow_cusecs
        plant.tanks[1].discharge_cusecs = 400_000
        # Fill the Tarbela->Kalabagh delay line with high flow
        for up, down, buf in plant._routes:
            if up == 1 and down == 4:
                buf.clear()
                buf.extend([400_000] * buf.maxlen)
        plant.step()
        self.assertGreater(plant.tanks[4].inflow_cusecs, before * 0.5)
