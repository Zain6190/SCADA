"""GRDC archive parsing: header metadata + daily/monthly series.

Pure-function tests over real export-format snippets plus one trip through the
actual files committed in data/raw/grdc.
"""
import os
from datetime import date

from scripts.ingest_grdc import parse_header, parse_series, read_file

DATA_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'data', 'raw', 'grdc'
)

HEADER = """# Title:                 GRDC STATION DATA FILE
# file generation date:  2026-09-21
#
# GRDC-No.:              2240100
# River:                 KABUL RIVER
# Station:               DAKAH
# Country:               AF
# Latitude (DD):       34.233333
# Longitude (DD):      71.033333
# Catchment area (km\xb2):      67370.0
# Altitude (m ASL):        420.0
# Next downstream station:      2335200
# Owner of original data: United States of America - US Geological Survey
#
# Table Header:
#     YYYY-MM-DD - Date
"""

DAILY = HEADER + """#
1968-02-21;--:--;     206.000;   -999.000;   0
1968-02-22;--:--;     217.000;   -999.000;   0
1968-02-23;--:--;    -999.000;   -999.000;   1
garbage-line
1968-02-26;--:;199.500
"""

MONTHLY = HEADER + """#
1973-01-01;--:--;    165.000;   -999.000;   0
1973-02-01;--:--;     95.000;   -999.000;   0
1973-03-01;--:--;    -999.000;   -999.000;   1
"""


class TestParseHeader:
    def test_full_metadata(self):
        meta = parse_header(HEADER.splitlines())
        assert meta['grdc_no'] == '2240100'
        assert meta['river'] == 'KABUL RIVER'
        assert meta['station'] == 'DAKAH'
        assert meta['country'] == 'AF'
        assert meta['latitude'] == 34.233333
        assert meta['longitude'] == 71.033333
        # superscript-2 byte varies with encoding - key match is prefix-based
        assert meta['catchment_km2'] == 67370.0
        assert meta['altitude_m'] == 420.0
        assert meta['next_downstream_grdc_no'] == '2335200'
        assert meta['owner'].startswith('United States')

    def test_sentinels_become_none(self):
        lines = [
            '# GRDC-No.:  2335200',
            '# Altitude (m ASL):        -999.00',
            '# Next downstream station:      -',
            '# Catchment area (km2): not-a-number',
            '# Table Header:',
            '1973-01-01;--:--;1.000',
        ]
        meta = parse_header(lines)
        assert meta['altitude_m'] is None
        assert meta['next_downstream_grdc_no'] is None
        assert meta['catchment_km2'] is None

    def test_stops_at_data_section(self):
        lines = HEADER.splitlines() + ['1968-02-21;--:--;206.000']
        meta = parse_header(lines)
        assert meta['grdc_no'] == '2240100'


class TestParseSeries:
    def test_daily_values_and_skips(self):
        obs = parse_series(DAILY.splitlines())
        # -999 row, garbage line and 2-column line all dropped
        assert obs == [
            (date(1968, 2, 21), 206.0),
            (date(1968, 2, 22), 217.0),
            (date(1968, 2, 26), 199.5),
        ]

    def test_monthly_dated_first_of_month(self):
        obs = parse_series(MONTHLY.splitlines())
        assert obs == [
            (date(1973, 1, 1), 165.0),
            (date(1973, 2, 1), 95.0),
        ]

    def test_no_data_before_table_header(self):
        # column-header line and junk must not produce rows without a gate
        obs = parse_series(['# GRDC-No.: 1', 'YYYY-MM-DD;hh:mm; Value',
                            'not-a-date;--:--;50.000'])
        assert obs == []


class TestRealFiles:
    def test_daily_file(self):
        path = os.path.join(DATA_DIR, '2240100_Q_Day.Cmd.txt')
        lines = read_file(path)
        meta = parse_header(lines)
        assert meta['grdc_no'] == '2240100'
        assert meta['catchment_km2'] == 67370.0
        obs = parse_series(lines)
        assert len(obs) == 4536
        assert obs[0] == (date(1968, 2, 21), 206.0)

    def test_monthly_file_for_empty_daily_station(self):
        # Indus @ Kotri: daily file is header-only, monthly spans 1936-1979
        path = os.path.join(DATA_DIR, '2335950_Q_Month.txt')
        lines = read_file(path)
        meta = parse_header(lines)
        assert meta['station'] == 'KOTRI'
        assert meta['catchment_km2'] == 832418.0
        obs = parse_series(lines)
        # 519 months in span minus 153 -999 gaps = 366 real values
        assert len(obs) == 366
        assert obs[0] == (date(1936, 10, 1), 1670.0)
        assert obs[-1] == (date(1979, 12, 1), 145.0)
