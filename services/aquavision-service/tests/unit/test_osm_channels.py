# tests/unit/test_osm_channels.py
# Module 6.4 Phase 3: OSM channel loader. Pure logic - no network.
import unittest

from infrastructure.ingestion.osm_channels import (
    IRSA_CANAL_SOURCE_ASSET,
    IRSA_TO_OSM,
    OVERPASS_MIRRORS,
    _length_km,
    build_query,
    export_geojson,
    match_irsa_label,
    summarise,
    to_features,
)


def _way(way_id, name=None, coords=None):
    return {
        "type": "way",
        "id": way_id,
        "tags": {"name": name} if name else {},
        "geometry": [{"lat": lat, "lon": lon} for lon, lat in (coords or
                     [(71.0, 30.0), (71.1, 30.1)])],
    }


class TestQueryBuilding(unittest.TestCase):
    def test_area_query_scopes_to_pakistan(self):
        q = build_query("canal")
        self.assertIn('area["ISO3166-1"="PK"]', q)
        self.assertIn('way["waterway"="canal"]', q)
        self.assertIn("out geom;", q)

    def test_named_only_adds_the_name_filter(self):
        self.assertIn('["name"]', build_query("canal", named_only=True))
        self.assertNotIn('["name"]', build_query("canal", named_only=False))

    def test_bbox_query_avoids_area_relations(self):
        # Not every mirror carries ISO3166-1 areas; one answered the area query
        # with 200 and zero elements.
        q = build_query("canal", use_bbox=True)
        self.assertNotIn("ISO3166-1", q)
        self.assertIn("(23.5,60.8,37.2,77.9)", q)


class TestLength(unittest.TestCase):
    def test_one_degree_of_latitude_is_about_111km(self):
        self.assertAlmostEqual(_length_km([[71.0, 30.0], [71.0, 31.0]]), 111.2, delta=1.0)

    def test_single_point_has_no_length(self):
        self.assertEqual(_length_km([[71.0, 30.0]]), 0.0)


class TestIrsaMatching(unittest.TestCase):
    def test_matches_report_shorthand_to_osm_names(self):
        self.assertEqual(match_irsa_label("Chashma Jhelum Link Canal"), "C-J Link")
        self.assertEqual(match_irsa_label("Taunsa Panjnad Link"), "T-P Link")
        self.assertEqual(match_irsa_label("Dera Ghazi Khan Canal"), "Dera Ghazi Khan Canal")

    def test_matching_is_case_insensitive(self):
        self.assertEqual(match_irsa_label("THAL CANAL"), "Thal")

    def test_unrelated_and_missing_names_do_not_match(self):
        self.assertIsNone(match_irsa_label("Some Other Canal"))
        self.assertIsNone(match_irsa_label(None))

    def test_hyphenation_does_not_break_a_match(self):
        # OSM writes "Chashma-Jhelum link canal"; the report writes "C-J Link".
        # Raw substring matching missed half the mapped canals.
        self.assertEqual(match_irsa_label("Chashma-Jhelum link canal"), "C-J Link")
        self.assertEqual(match_irsa_label("Thal Plain canal"), "Thal")

    def test_shared_way_resolves_deterministically(self):
        # One OSM way is named "Muzaffargarh Canal Taunsa-Panjnad Canal" and
        # matches two IRSA labels. Dict iteration order must not decide which.
        name = "Muzaffargarh Canal Taunsa-Panjnad Canal"
        first = match_irsa_label(name)
        self.assertIsNotNone(first)
        for _ in range(5):
            self.assertEqual(match_irsa_label(name), first)

    def test_a_similarly_named_but_different_canal_is_not_matched(self):
        # "Ghazi Canal" is Ghazi-Barotha on the upper Indus, NOT the Dera Ghazi
        # Khan Canal at Taunsa. Mapping it would attach Taunsa's discharge
        # readings to a canal 400 km away.
        self.assertIsNone(match_irsa_label("Ghazi Canal"))
        self.assertIsNone(match_irsa_label("Muzaffar Distributary"))

    def test_every_mapped_canal_has_a_feeding_asset(self):
        # Without feeds_from_asset_id a discharge reading cannot attach to a shape.
        for label in IRSA_TO_OSM:
            self.assertIn(label, IRSA_CANAL_SOURCE_ASSET, f"{label} has no source asset")
            self.assertIn(IRSA_CANAL_SOURCE_ASSET[label], range(1, 12))


class TestFeatureConversion(unittest.TestCase):
    def test_named_channels_are_monitored_unnamed_are_not(self):
        # The scope's filter: "major canals and wider segments". A 10m
        # distributary cannot be resolved by a 10m Sentinel-2 pixel.
        payload = {"elements": [_way(1, "Thal Canal"), _way(2, None)]}
        feats = to_features(payload, "canal")
        by_id = {f["properties"]["osm_id"]: f["properties"] for f in feats}
        self.assertTrue(by_id[1]["is_monitored"])
        self.assertFalse(by_id[2]["is_monitored"])

    def test_link_canals_get_their_own_type(self):
        payload = {"elements": [_way(1, "Chashma Jhelum Link Canal")]}
        self.assertEqual(to_features(payload, "canal")[0]["properties"]["channel_type"],
                         "link_canal")

    def test_irsa_label_and_feeding_asset_are_attached(self):
        payload = {"elements": [_way(1, "Dera Ghazi Khan Canal")]}
        props = to_features(payload, "canal")[0]["properties"]
        self.assertEqual(props["irsa_label"], "Dera Ghazi Khan Canal")
        self.assertEqual(props["feeds_from_asset_id"], 5)  # Taunsa Barrage

    def test_degenerate_ways_are_dropped(self):
        # A single node is not a channel and would break ST_GeomFromText.
        payload = {"elements": [_way(1, "Stub", coords=[(71.0, 30.0)])]}
        self.assertEqual(to_features(payload, "canal"), [])

    def test_non_way_elements_are_ignored(self):
        payload = {"elements": [{"type": "node", "id": 9, "lat": 30, "lon": 71}]}
        self.assertEqual(to_features(payload, "canal"), [])

    def test_geometry_is_lon_lat_order(self):
        # GeoJSON and PostGIS both expect lon,lat; OSM reports lat/lon named.
        payload = {"elements": [_way(1, "X", coords=[(71.0, 30.0), (71.5, 30.5)])]}
        self.assertEqual(to_features(payload, "canal")[0]["geometry"]["coordinates"],
                         [[71.0, 30.0], [71.5, 30.5]])


class TestSummaryAndExport(unittest.TestCase):
    def test_summary_counts_named_and_matched(self):
        payload = {"elements": [_way(1, "Thal Canal"), _way(2, None),
                                _way(3, "Unrelated Canal")]}
        s = summarise(to_features(payload, "canal"))
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["named"], 2)
        self.assertEqual(s["irsa_matched"], 1)
        self.assertEqual(s["irsa_labels"], ["Thal"])

    def test_export_refuses_to_write_an_empty_layer(self):
        # An empty FeatureCollection that exits 0 reads downstream as
        # "Pakistan has no canals" - this already happened once.
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                export_geojson([], Path(tmp) / "empty.geojson")

    def test_more_than_one_mirror_is_configured(self):
        self.assertGreater(len(OVERPASS_MIRRORS), 1)


if __name__ == "__main__":
    unittest.main()
