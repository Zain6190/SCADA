# District territory rollup: prediction severity, population split, alert threshold.
import unittest

from infrastructure.flood.official_shapes import apply_official_geometries, normalize_district
from infrastructure.flood.territories import (
    TERRITORIES,
    AssetFlood,
    LocatedPoint,
    SegmentImpact,
    build_flood_territory,
    districts_on_segment,
)


def _props(result: dict) -> dict[str, dict]:
    return {feature["properties"]["district"]: feature["properties"] for feature in result["features"]}


class TestFloodTerritoryRollup(unittest.TestCase):
    def test_catalog_covers_every_segment_district_once(self):
        names = [territory.name for territory in TERRITORIES]
        self.assertEqual(len(names), len(set(names)))
        for (src, dst), expected in {
            (1, 4): ["Haripur", "Swabi", "Mardan", "Nowshera"],
            (11, 6): ["Muzaffargarh", "Rajanpur"],
        }.items():
            self.assertEqual(districts_on_segment(src, dst), expected)
        for territory in TERRITORIES:
            ring = territory.ring
            self.assertGreaterEqual(len(ring), 4)
            self.assertEqual(ring[0], ring[-1])

    def test_high_prediction_marks_downstream_districts_and_splits_population(self):
        result = build_flood_territory(
            {
                1: AssetFlood(1, "Tarbela Reservoir", 0.82, "HIGH", "Evacuate low areas"),
                10: AssetFlood(10, "Chenab @ Marala", 0.12, "LOW", "Monitor"),
            },
            {
                (1, 4): SegmentImpact(1000, 4, 2),
                (10, 11): SegmentImpact(90, 3, 0),
            },
        )
        props = _props(result)
        self.assertEqual(len(result["features"]), len(TERRITORIES))

        marked = districts_on_segment(1, 4)
        self.assertEqual(
            sum(props[name]["population_exposed"] for name in marked),
            1000,
        )
        self.assertEqual(sum(props[name]["bridges"] for name in marked), 4)
        self.assertEqual(sum(props[name]["hospitals"] for name in marked), 2)
        for name in marked:
            self.assertEqual(props[name]["flood_severity"], "HIGH")
            self.assertAlmostEqual(props[name]["flood_probability"], 0.82)
            self.assertTrue(props[name]["alert"])
            self.assertEqual(props[name]["source_asset_name"], "Tarbela Reservoir")

        low = districts_on_segment(10, 11)
        self.assertEqual(sum(props[name]["population_exposed"] for name in low), 90)
        for name in low:
            self.assertEqual(props[name]["flood_severity"], "LOW")
            self.assertFalse(props[name]["alert"])

        self.assertEqual(props["Hyderabad"]["flood_severity"], "NONE")
        self.assertEqual(props["Hyderabad"]["population_exposed"], 0)
        self.assertFalse(props["Hyderabad"]["alert"])

        alert_names = {row["district"] for row in result["alerts"]}
        self.assertEqual(alert_names, set(marked))
        for row in result["alerts"]:
            self.assertEqual(row["severity"], "HIGH")
            self.assertIn("population_exposed", row)
            self.assertIn("recommendation", row)

    def test_worst_severity_wins_and_population_adds_across_segments(self):
        result = build_flood_territory(
            {
                1: AssetFlood(1, "Tarbela Reservoir", 0.2, "LOW", "Watch"),
                9: AssetFlood(9, "Kabul @ Nowshera", 0.95, "EXTREME", "Evacuate now"),
                5: AssetFlood(5, "Taunsa Barrage", 0.4, "MODERATE", "Prepare"),
                11: AssetFlood(11, "Panjnad", 0.7, "HIGH", "Move to high ground"),
            },
            {
                (1, 4): SegmentImpact(400, 4, 0),
                (9, 4): SegmentImpact(300, 3, 3),
                (5, 6): SegmentImpact(400, 0, 0),
                (11, 6): SegmentImpact(200, 2, 0),
            },
        )
        props = _props(result)

        self.assertEqual(props["Haripur"]["flood_severity"], "LOW")
        self.assertFalse(props["Haripur"]["alert"])
        self.assertEqual(props["Haripur"]["population_exposed"], 100)

        self.assertEqual(props["Nowshera"]["flood_severity"], "EXTREME")
        self.assertEqual(props["Nowshera"]["source_asset_id"], 9)
        self.assertEqual(props["Nowshera"]["population_exposed"], 200)
        self.assertTrue(props["Nowshera"]["alert"])
        self.assertEqual(props["Mardan"]["flood_severity"], "EXTREME")
        self.assertEqual(props["Peshawar"]["flood_severity"], "EXTREME")
        self.assertEqual(props["Peshawar"]["population_exposed"], 100)

        indus = districts_on_segment(1, 4)
        self.assertEqual(sum(props[name]["population_exposed"] for name in indus if name not in {"Nowshera", "Mardan"}) + 100 + 100, 400)

        self.assertEqual(props["Rajanpur"]["flood_severity"], "HIGH")
        self.assertEqual(props["Rajanpur"]["source_asset_name"], "Panjnad")
        self.assertEqual(props["Rajanpur"]["population_exposed"], 200)
        self.assertEqual(props["Dera Ghazi Khan"]["flood_severity"], "MODERATE")
        self.assertTrue(props["Dera Ghazi Khan"]["alert"])
        self.assertEqual(props["Muzaffargarh"]["flood_severity"], "HIGH")

        alert_names = {row["district"] for row in result["alerts"]}
        self.assertIn("Nowshera", alert_names)
        self.assertIn("Peshawar", alert_names)
        self.assertNotIn("Haripur", alert_names)
        self.assertNotIn("Swabi", alert_names)
        self.assertEqual(result["alerts"][0]["severity"], "EXTREME")

    def test_danger_zone_marks_towns_assets_and_infrastructure_inside(self):
        result = build_flood_territory(
            {1: AssetFlood(1, "Tarbela Reservoir", 0.82, "HIGH", "Evacuate low areas")},
            {(1, 4): SegmentImpact(1000, 4, 2)},
            located=[LocatedPoint("Tarbela Reservoir", "asset", 34.00, 73.00)],
        )
        props = _props(result)
        haripur = props["Haripur"]["inside"]
        names = {item["name"] for item in haripur}
        self.assertIn("Haripur", names)
        self.assertIn("Khalabat", names)
        self.assertIn("Tarbela Reservoir", names)
        self.assertEqual(sum(1 for item in haripur if item["kind"] == "bridge"), props["Haripur"]["bridges"])
        self.assertEqual(sum(1 for item in haripur if item["kind"] == "hospital"), props["Haripur"]["hospitals"])
        self.assertTrue(all(item["district"] == "Haripur" for item in haripur))
        self.assertEqual(props["Hyderabad"]["inside"], [])
        self.assertEqual(props["Swabi"]["flood_severity"], "HIGH")
        self.assertTrue(any(item["name"] == "Swabi" for item in props["Swabi"]["inside"]))
        self.assertEqual(
            next(row for row in result["alerts"] if row["district"] == "Haripur")["inside_count"],
            len(haripur),
        )

    def test_official_polygon_replaces_the_box_for_a_matching_district(self):
        result = build_flood_territory(
            {1: AssetFlood(1, "Tarbela Reservoir", 0.82, "HIGH", "Evacuate")},
            {(1, 4): SegmentImpact(100, 1, 1)},
        )
        official = {
            "type": "Polygon",
            "coordinates": [[[71.0, 33.0], [72.0, 33.0], [72.0, 34.0], [71.0, 33.0]]],
        }
        apply_official_geometries(result, {normalize_district("D.G. Khan"): official, normalize_district("Nowshera"): official})
        props = _props(result)
        by_name = {feature["properties"]["district"]: feature for feature in result["features"]}
        self.assertEqual(by_name["Nowshera"]["geometry"], official)
        self.assertEqual(props["Nowshera"]["boundary"], "official")
        self.assertEqual(by_name["Dera Ghazi Khan"]["geometry"]["type"], "Polygon")
        self.assertEqual(props["Dera Ghazi Khan"]["boundary"], "official")
        self.assertEqual(props["Haripur"]["boundary"], "approximate")
        self.assertEqual(len(by_name["Haripur"]["geometry"]["coordinates"][0]), 5)


if __name__ == "__main__":
    unittest.main()
