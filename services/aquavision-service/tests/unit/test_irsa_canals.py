# tests/unit/test_irsa_canals.py
# Module 6.4 Phase 0: canal withdrawals parsed from the IRSA daily report.
#
# Split in two: pure-logic tests that always run, and archive tests that assert
# against all 29 real PDFs. The archive tests are the ones that matter - the
# previous parser was tuned against a single report and silently returned rows
# with every field empty for six of eleven assets.
import glob
import os
import re
import unittest
from datetime import date

from infrastructure.ingestion.irsa_scraper import (
    _match_header,
    parse_block,
    parse_irsa_pdf,
    split_station_blocks,
)

ARCHIVE = "infrastructure/ingestion/raw_archive/irsa"


class TestBlockParsing(unittest.TestCase):
    def test_named_canals_are_extracted_readings_are_not(self):
        lines = [
            "U/S DISCHARGE = 375909 Cs",
            "D/S DISCHARGE = 362309 Cs",
            "T-P Link = 5000 Cs",
            "Muzafarghar Canal = 0 Cs",
            "Dera Ghazi Khan Canal = 8100 Cs",
        ]
        readings, canals = parse_block(lines)
        self.assertEqual(readings["upstream_discharge_cusecs"], 375909)
        self.assertEqual(readings["downstream_discharge_cusecs"], 362309)
        self.assertEqual(canals, {
            "T-P Link": 5000.0,
            "Muzafarghar Canal": 0.0,
            "Dera Ghazi Khan Canal": 8100.0,
        })

    def test_zero_flow_is_captured_not_dropped(self):
        # A canal at 0 Cs is the signal, not missing data.
        _, canals = parse_block(["Muzafarghar Canal = 0 Cs"])
        self.assertIn("Muzafarghar Canal", canals)
        self.assertEqual(canals["Muzafarghar Canal"], 0.0)

    def test_aggregate_withdrawal_uses_the_total_key(self):
        _, canals = parse_block(["* Canal W/dls = 33875 Cs"])
        self.assertEqual(canals, {"_total": 33875.0})

    def test_report_furniture_is_not_read_as_a_canal(self):
        # These all match "<name> = <n> Cs" but are metrics or totals.
        _, canals = parse_block([
            "MEAN D/S DISCHARGE = 52446 Cs",
            "TOTAL = 319590 Cs",
            "MEAN INFLOW = 208200 Cs",
        ])
        self.assertEqual(canals, {})

    def test_level_is_a_reading_not_a_canal(self):
        readings, canals = parse_block(["LEVEL = 1550.00", "DEAD LEVEL = 1402.00"])
        self.assertEqual(readings["water_level_ft"], 1550.0)
        self.assertEqual(readings["dead_level_ft"], 1402.0)
        self.assertEqual(canals, {})


class TestHeaderMatching(unittest.TestCase):
    def test_recognises_station_headers(self):
        self.assertEqual(_match_header("TAUNSA:")[0], "Taunsa Barrage")
        self.assertEqual(_match_header("INDUS @ TARBELA")[0], "Tarbela Reservoir")
        self.assertEqual(_match_header("JHELUM @ MANGLA:")[0], "Mangla Reservoir")

    def test_ignores_ordinary_lines(self):
        self.assertIsNone(_match_header("U/S DISCHARGE = 375909 Cs"))
        self.assertIsNone(_match_header("Dera Ghazi Khan Canal = 8100 Cs"))

    def test_blocks_do_not_run_across_the_column_break(self):
        text = "TAUNSA:\nT-P Link = 5000 Cs\n\f\nGUDDU:\n* Canal W/dls = 33875 Cs"
        blocks = split_station_blocks(text)
        self.assertEqual(blocks["Taunsa Barrage"][1], ["T-P Link = 5000 Cs"])
        self.assertEqual(blocks["Guddu Barrage"][1], ["* Canal W/dls = 33875 Cs"])


def _archive_files():
    return sorted(glob.glob(os.path.join(ARCHIVE, "*.pdf")))


@unittest.skipUnless(_archive_files(), "IRSA archive PDFs not present")
class TestAgainstRealArchive(unittest.TestCase):
    """Assertions across every archived report, not a single sample."""

    @classmethod
    def setUpClass(cls):
        cls.by_asset = {}
        cls.canal_rows = 0
        for path in _archive_files():
            m = re.search(r"(\d{2})-(\d{2})-(\d{4})", os.path.basename(path))
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            for o in parse_irsa_pdf(path, d):
                cls.by_asset.setdefault(o.asset_name, []).append(o)
                cls.canal_rows += len(o.canal_withdrawals)

    def test_barrages_are_no_longer_empty(self):
        # These six previously parsed with every measurement field None, because
        # the two-column layout was being read as single lines.
        for name in ("Chashma Barrage", "Taunsa Barrage", "Guddu Barrage",
                     "Sukkur Barrage", "Kotri Barrage", "Panjnad"):
            rows = self.by_asset.get(name, [])
            self.assertTrue(rows, f"{name} not parsed at all")
            with_discharge = [
                o for o in rows
                if o.upstream_discharge_cusecs is not None
                or o.downstream_discharge_cusecs is not None
            ]
            self.assertEqual(len(with_discharge), len(rows),
                             f"{name}: {len(rows) - len(with_discharge)} rows still empty")

    def test_canal_withdrawals_found_in_every_report(self):
        for name in ("Chashma Barrage", "Taunsa Barrage", "Kalabagh (Indus)"):
            rows = self.by_asset.get(name, [])
            missing = [o for o in rows if not o.canal_withdrawals]
            self.assertFalse(missing,
                             f"{name}: {len(missing)} reports parsed no canals")

    def test_known_canals_are_present(self):
        taunsa = self.by_asset["Taunsa Barrage"]
        names = set()
        for o in taunsa:
            names.update(o.canal_withdrawals)
        for expected in ("T-P Link", "Muzafarghar Canal", "Dera Ghazi Khan Canal"):
            self.assertIn(expected, names)

    def test_no_metric_leaked_into_canal_names(self):
        for rows in self.by_asset.values():
            for o in rows:
                for label in o.canal_withdrawals:
                    self.assertNotIn("DISCHARGE", label.upper())
                    self.assertNotEqual(label.upper(), "TOTAL")

    def test_a_dry_canal_is_recorded(self):
        # Muzafarghar Canal sits at 0 Cs on part of the archive; if that stops
        # being captured, the module loses its only real DRY example.
        zeros = [o for o in self.by_asset["Taunsa Barrage"]
                 if o.canal_withdrawals.get("Muzafarghar Canal") == 0]
        self.assertTrue(zeros, "no zero-flow canal reading found in the archive")

    def test_extraction_volume_has_not_regressed(self):
        self.assertGreaterEqual(self.canal_rows, 200,
                                f"only {self.canal_rows} canal values extracted")


if __name__ == "__main__":
    unittest.main()
