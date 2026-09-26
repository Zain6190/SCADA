# Official IRSA/FFD anchoring for Soft OT. No database required.
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ot-runtime"))

from ot_runtime.anchor import map_official_anchor
from ot_runtime.interlocks import gate_from_outflow, outflow_from_gate
from ot_runtime.plant import VirtualPlant
from ot_runtime.runtime import OtRuntime


class TestPlantApplyAnchor(unittest.TestCase):
    def test_tarbela_level_and_inflow_match_as_ai(self):
        plant = VirtualPlant(sim_minutes=15)
        catalog_level = plant.tanks[1].level_ft
        plant.apply_anchor({1: {"level_ft": 1542.0, "inflow_cusecs": 90000.0}})
        ai = plant.as_ai(1)
        self.assertAlmostEqual(ai["level_ft"], 1542.0)
        self.assertAlmostEqual(ai["inflow_cusecs"], 90000.0)
        self.assertNotAlmostEqual(catalog_level, ai["level_ft"])

    def test_delay_line_to_kalabagh_uses_new_discharge(self):
        plant = VirtualPlant(sim_minutes=15)
        plant.tanks[1].discharge_cusecs = 12_000
        plant._reseed_routes()
        plant.apply_anchor({1: {"level_ft": 1542.0, "inflow_cusecs": 90000.0, "discharge_cusecs": 90000.0}})
        found = False
        for up, down, buf in plant._routes:
            if up == 1 and down == 4:
                found = True
                self.assertTrue(buf)
                self.assertTrue(all(abs(sample - 90000.0) < 1e-6 for sample in buf))
        self.assertTrue(found)

    def test_null_fields_keep_previous_plant_value(self):
        plant = VirtualPlant(sim_minutes=15)
        before_inflow = plant.tanks[1].inflow_cusecs
        plant.apply_anchor({1: {"level_ft": 1542.0}})
        self.assertAlmostEqual(plant.tanks[1].level_ft, 1542.0)
        self.assertAlmostEqual(plant.tanks[1].inflow_cusecs, before_inflow)

    def test_missing_asset_keeps_catalog_default(self):
        plant = VirtualPlant(sim_minutes=15)
        mangla_before = plant.as_ai(2)
        plant.apply_anchor({1: {"level_ft": 1542.0, "inflow_cusecs": 90000.0}})
        self.assertAlmostEqual(plant.as_ai(2)["level_ft"], mangla_before["level_ft"])
        self.assertAlmostEqual(plant.as_ai(2)["inflow_cusecs"], mangla_before["inflow_cusecs"])


class TestRuntimeOfficialAnchor(unittest.TestCase):
    def test_catalog_defaults_gone_after_anchor(self):
        rt = OtRuntime(sim_minutes=15)
        catalog_level = rt.plant.tanks[1].level_ft
        catalog_inflow = rt.plant.tanks[1].inflow_cusecs
        rt.apply_official_anchor(
            {
                1: {
                    "level_ft": 1542.0,
                    "inflow_cusecs": 88_000.0,
                    "outflow_cusecs": 70_000.0,
                    "discharge_cusecs": 70_000.0,
                    "source": "IRSA",
                    "observed_at": "2026-09-20T00:00:00+00:00",
                }
            }
        )
        ai = rt.plant.as_ai(1)
        self.assertAlmostEqual(ai["level_ft"], 1542.0)
        self.assertAlmostEqual(ai["inflow_cusecs"], 88000.0)
        self.assertNotAlmostEqual(catalog_level, ai["level_ft"])
        self.assertNotAlmostEqual(catalog_inflow, ai["inflow_cusecs"])
        self.assertTrue(rt.anchored)
        self.assertEqual(rt.anchor_meta["date"], "2026-09-20")

    def test_sukkur_gate_matches_official_outflow(self):
        rt = OtRuntime(sim_minutes=15)
        self.assertAlmostEqual(rt.plcs[7].gate_pos_pct, 40.0)
        rt.apply_official_anchor(
            {
                7: {
                    "level_ft": 266.0,
                    "inflow_cusecs": 210_000.0,
                    "outflow_cusecs": 200_000.0,
                    "discharge_cusecs": 200_000.0,
                    "source": "IRSA",
                    "observed_at": "2026-09-20",
                }
            }
        )
        self.assertGreater(rt.plcs[7].gate_pos_pct, 70.0)
        self.assertAlmostEqual(rt.plcs[7].gate_cmd_pct, rt.plcs[7].gate_pos_pct)

    def test_published_notes_include_anchored_to(self):
        rt = OtRuntime(sim_minutes=15)
        rt.apply_official_anchor(
            {
                1: {
                    "level_ft": 1542.0,
                    "inflow_cusecs": 90000.0,
                    "source": "IRSA",
                    "observed_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
                }
            }
        )
        result = rt.tick(now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc))
        tarbela = next(p for p in result.published if p.asset_id == 1)
        self.assertIn("anchored_to=IRSA:2026-09-20", tarbela.notes)


class TestMapOfficialAnchor(unittest.TestCase):
    def test_ffd_wins_nowshera_discharge(self):
        irsa = {
            1: {
                "water_level_ft": 1542.0,
                "inflow_cusecs": 90000.0,
                "outflow_cusecs": 80000.0,
                "source_authority": "IRSA",
                "observed_at": datetime(2026, 9, 20),
            },
            9: {
                "discharge_cusecs": 10_000.0,
                "source_authority": "IRSA",
                "observed_at": datetime(2026, 9, 19),
            },
        }
        ffd = {
            9: {
                "gauge_level_ft": 8.5,
                "discharge_cusecs": 22_222.0,
                "observed_at": date(2026, 9, 20),
            }
        }
        mapped = map_official_anchor(irsa, ffd)
        self.assertAlmostEqual(mapped[1]["level_ft"], 1542.0)
        self.assertAlmostEqual(mapped[1]["inflow_cusecs"], 90000.0)
        self.assertEqual(mapped[1]["source"], "IRSA")
        self.assertAlmostEqual(mapped[9]["discharge_cusecs"], 22222.0)
        self.assertAlmostEqual(mapped[9]["level_ft"], 8.5)
        self.assertEqual(mapped[9]["source"], "FFD")

    def test_barrage_uses_upstream_as_inflow(self):
        irsa = {
            7: {
                "upstream_discharge_cusecs": 180_000.0,
                "downstream_discharge_cusecs": 170_000.0,
                "source_authority": "IRSA",
                "observed_at": datetime(2026, 9, 20),
            }
        }
        mapped = map_official_anchor(irsa, {})
        self.assertAlmostEqual(mapped[7]["inflow_cusecs"], 180000.0)
        self.assertAlmostEqual(mapped[7]["outflow_cusecs"], 170000.0)

    def test_skips_soft_ot_and_usgs(self):
        irsa = {
            1: {"inflow_cusecs": 1.0, "source_authority": "SOFT_OT", "observed_at": datetime(2026, 9, 20)},
            2: {"inflow_cusecs": 2.0, "source_authority": "USGS", "observed_at": datetime(2026, 9, 20)},
        }
        mapped = map_official_anchor(irsa, {})
        self.assertNotIn(1, mapped)
        self.assertNotIn(2, mapped)


class TestSoftOtProvenanceUnchanged(unittest.TestCase):
    def test_persist_contract_still_synthetic_priority_4(self):
        from infrastructure.ot import persist as persist_mod

        self.assertEqual(persist_mod.SOFT_OT_ORIGIN, "SYNTHETIC")
        self.assertEqual(persist_mod.SOFT_OT_STATUS, "SIMULATED")
        self.assertEqual(persist_mod.SOFT_OT_PRIORITY, 4)
        self.assertEqual(persist_mod.SOFT_OT_AUTHORITY, "SOFT_OT")

    def test_gate_from_outflow_inverts_rating(self):
        outflow = outflow_from_gate(55, 266, 255, 268, 250_000)
        gate = gate_from_outflow(outflow, 266, 255, 268, 250_000)
        self.assertAlmostEqual(gate, 55.0, places=4)


if __name__ == "__main__":
    unittest.main()
