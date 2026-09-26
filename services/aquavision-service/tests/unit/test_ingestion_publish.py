# Fixture publish, skipped Earth Engine, IRSA series append, and stable district ids.
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
ML = REPO / "packages" / "ml-pipeline"
OT = REPO / "services" / "ot-runtime"
for path in (str(ROOT), str(ML), str(OT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from gee.districts import match_districts
from scripts.run_pipeline import gee_skip_reason, indicators_are_stale
from scripts.sync_indicators import PUBLISHED_TABLES, build_rows
from infrastructure.ingestion.ot_series_append import COLUMNS, append_days, days_from_irsa_observations
from infrastructure.ingestion.satellite_publish import (
    ndvi_rows,
    reservoir_area_row,
    satellite_section,
)


class _Obs:
    def __init__(self):
        self.asset_name = "Tarbela Reservoir"
        self.water_level_ft = 1529.0
        self.inflow_cusecs = 100000
        self.outflow_cusecs = 80000
        self.upstream_discharge_cusecs = None
        self.downstream_discharge_cusecs = None
        self.discharge_cusecs = 80000
        self.canal_withdrawals = None


class IngestionPublishTests(unittest.TestCase):
    def test_fixture_month_builds_wai_without_observations(self):
        import pandas as pd

        frame = pd.DataFrame([{
            "region_id": 5,
            "month": "2026-07-01",
            "rainfall_mm": 40.0,
            "et_mm": 80.0,
            "water_extent": 0.2,
            "ndvi": 0.45,
            "sm_rootzone": float("nan"),
            "sm_surface": float("nan"),
        }])
        rows, skipped = build_rows(frame, [5])
        self.assertEqual(skipped, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["region_id"], 5)
        self.assertIsNotNone(rows[0]["wai_score"])
        self.assertNotIn("aquavision.water_observations", PUBLISHED_TABLES)
        published = ndvi_rows([{
            "region_id": "5",
            "month": "2026-07-01",
            "rainfall_mm": "40",
            "et_mm": "80",
            "water_extent": "0.2",
            "ndvi": "0.45",
        }])
        self.assertEqual(published[0]["ndvi"], 0.45)
        section = satellite_section([{
            "region_id": "5",
            "month": "2026-07-01",
            "rainfall_mm": "12",
            "et_mm": "90",
            "water_extent": "0.1",
            "ndvi": "0.3",
        }], names={5: "Lahore"})
        self.assertEqual(section["image_week"], "2026-07-01")
        self.assertEqual(section["worst_districts"][0]["name"], "Lahore")
        from scripts.sync_indicators import attach_surface_area
        import pandas as pd
        stamped = [{
            "region_id": 9,
            "week_start_date": pd.Timestamp("2026-07-01"),
            "surface_water_area_km2": None,
            "surface_water_change_pct": None,
        }]
        folder = Path(tempfile.mkdtemp())
        surface = folder / "surface_water.csv"
        surface.write_text(
            "region_id,week_start_date,ndwi_mean,mndwi_mean,water_area_km2,cloud_pct,change_pct\n"
            "9,2026-07-06,0.2,0.3,12.5,10,4.0\n",
            encoding="utf-8",
        )
        attach_surface_area(stamped, surface)
        self.assertEqual(stamped[0]["surface_water_area_km2"], 12.5)
        self.assertEqual(stamped[0]["surface_water_change_pct"], 4.0)

    def test_fetch_without_credentials_is_skipped(self):
        reason = gee_skip_reason(False, None)
        self.assertIsNotNone(reason)
        self.assertIn("no GEE credentials", reason)
        self.assertIsNone(gee_skip_reason(True, None))
        self.assertTrue(indicators_are_stale(None))
        self.assertTrue(indicators_are_stale(30, max_days=7))
        self.assertFalse(indicators_are_stale(1, max_days=7))

    def test_irsa_append_does_not_change_observation_level(self):
        observation = _Obs()
        level_before = observation.water_level_ft
        days = days_from_irsa_observations([observation], date(2026, 9, 25), "http://pakirsa.gov.pk/Doc/Data25-09-2026.pdf")
        self.assertEqual(observation.water_level_ft, level_before)
        self.assertEqual(days[0].source_authority, "IRSA")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "indus_ot_daily.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerow({
                    "observed_on": "2026-09-24",
                    "asset_id": 1,
                    "device_code": "RTU-TARBELA",
                    "level_ft": 1500,
                    "inflow_cusecs": 1,
                    "outflow_cusecs": 1,
                    "discharge_cusecs": 1,
                    "canal_offtake_cusecs": 0,
                    "gate_pct_derived": "",
                    "source_authority": "IRSA",
                    "source_url": "kept",
                })
            append_days(days, path)
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        kept = next(row for row in rows if row["observed_on"] == "2026-09-24")
        added = next(row for row in rows if row["observed_on"] == "2026-09-25")
        self.assertEqual(kept["level_ft"], "1500")
        self.assertEqual(kept["source_authority"], "IRSA")
        self.assertEqual(added["source_authority"], "IRSA")
        area = reservoir_area_row(1, date(2026, 9, 25), 42.5)
        self.assertEqual(area["source_authority"], "GEE")
        self.assertFalse(area["writes_irsa_level"])
        self.assertNotIn("water_level_ft", area)

    def test_polygon_match_keeps_district_ids(self):
        existing = [
            {"id": 5, "name": "Lahore"},
            {"id": 8, "name": "Mirpurkhas"},
            {"id": 16, "name": "Khuzdar"},
        ]
        features = [
            {"properties": {"shapeName": "Khuzdar District"}, "geometry": {"type": "Polygon", "coordinates": []}},
            {"properties": {"shapeName": "Mirpur Khas"}, "geometry": {"type": "Polygon", "coordinates": []}},
            {"properties": {"shapeName": "Lahore"}, "geometry": {"type": "Polygon", "coordinates": []}},
            {"properties": {"shapeName": "Karachi"}, "geometry": {"type": "Polygon", "coordinates": []}},
        ]
        updates = match_districts(existing, features)
        self.assertEqual([row["id"] for row in updates], [16, 8, 5])
        self.assertEqual([row["name"] for row in updates], ["Khuzdar", "Mirpurkhas", "Lahore"])
        live = match_districts(
            [{"id": 9, "name": "Dera Ghazi Khan"}, {"id": 18, "name": "Dera Ismail Khan"}],
            [
                {"properties": {"shapeName": "D.G. Khan"}, "geometry": {"type": "Polygon", "coordinates": []}},
                {"properties": {"shapeName": "D.I. Khan"}, "geometry": {"type": "Polygon", "coordinates": []}},
            ],
        )
        self.assertEqual([(row["id"], row["name"]) for row in live], [(9, "Dera Ghazi Khan"), (18, "Dera Ismail Khan")])


if __name__ == "__main__":
    unittest.main()
