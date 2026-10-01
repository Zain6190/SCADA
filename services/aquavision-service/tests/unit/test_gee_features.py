"""Tests for the GEE feature pipeline (P5) — parsing, merge, service with fake ee."""
from datetime import date, datetime, timezone

from ml.features.gee_service import (
    CHIRPS_ID,
    MOD13_ID,
    MOD16_ID,
    GeeFeatureService,
    merge_series,
    region_rows_to_series,
)

TS_0920 = int(datetime(2026, 9, 20, tzinfo=timezone.utc).timestamp() * 1000)
TS_0921 = int(datetime(2026, 9, 21, tzinfo=timezone.utc).timestamp() * 1000)
TS_0901 = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)


# ── region_rows_to_series ─────────────────────────────────────────────────

def test_parses_rows_and_applies_factor():
    rows = [[73.0, 34.0, TS_0920, 12500.0], [73.0, 34.0, TS_0921, 5000.0]]
    series = region_rows_to_series(rows, factor=0.0001)
    assert series == {date(2026, 9, 20): 1.25, date(2026, 9, 21): 0.5}


def test_factor_one_passthrough():
    series = region_rows_to_series([[73.0, 34.0, TS_0920, 12.5]], factor=1.0)
    assert series[date(2026, 9, 20)] == 12.5


def test_drops_fill_values_outside_valid_range():
    rows = [
        [73.0, 34.0, TS_0920, 5000],
        [73.0, 34.0, TS_0921, -3000],
    ]
    series = region_rows_to_series(rows, factor=0.0001, valid_raw=(-2000, 10000))
    assert list(series.values()) == [0.5]


def test_skips_null_and_malformed_rows():
    rows = [
        None,
        [],
        [73.0, 34.0],
        [73.0, 34.0, TS_0920, None],
        [73.0, 34.0, None, 5.0],
        [73.0, 34.0, TS_0920, "not-a-number"],
        [73.0, 34.0, TS_0921, 2.0],
    ]
    series = region_rows_to_series(rows)
    assert series == {date(2026, 9, 21): 2.0}


def test_empty_input_returns_empty():
    assert region_rows_to_series(None) == {}
    assert region_rows_to_series([]) == {}


def test_parses_real_getregion_format_with_header():
    rows = [
        ["id", "longitude", "latitude", "time", "precipitation"],
        ["20260820", 72.97, 33.97, TS_0920, 5.5],
        ["20260821", 72.97, 33.97, TS_0921, 14.0],
    ]
    series = region_rows_to_series(rows)
    assert series == {date(2026, 9, 20): 5.5, date(2026, 9, 21): 14.0}


def test_real_format_applies_scale_and_fill_filter():
    rows = [
        ["id", "longitude", "latitude", "time", "NDVI"],
        ["2026_09_01", 72.68, 34.08, TS_0901, 6500],
        ["2026_09_17", 72.68, 34.08, TS_0920, -3000],
    ]
    series = region_rows_to_series(rows, factor=0.0001, valid_raw=(-2000, 10000))
    assert series == {date(2026, 9, 1): 0.65}


# ── merge_series ──────────────────────────────────────────────────────────

def test_merge_combines_fields_per_day_sorted():
    merged = merge_series(
        {date(2026, 9, 21): 3.0, date(2026, 9, 20): 1.0},
        {date(2026, 9, 20): 8.0},
        {date(2026, 9, 1): 0.4},
    )
    assert list(merged.keys()) == [date(2026, 9, 1), date(2026, 9, 20), date(2026, 9, 21)]
    assert merged[date(2026, 9, 20)] == {"rainfall_mm": 1.0, "et_mm": 8.0}
    assert merged[date(2026, 9, 21)] == {"rainfall_mm": 3.0}
    assert merged[date(2026, 9, 1)] == {"ndvi": 0.4}


def test_merge_empty():
    assert merge_series({}, {}, {}) == {}


# ── GeeFeatureService.fetch_series with a fake ee module ─────────────────

class _FakeRegion:
    def __init__(self, rows):
        self._rows = rows

    def getInfo(self):
        return self._rows


_CANNED = {
    CHIRPS_ID: [[73.0, 34.0, TS_0920, 12.5], [73.0, 34.0, TS_0921, 0.5]],
    MOD16_ID: [[73.0, 34.0, TS_0920, 100.0]],
    MOD13_ID: [
        [73.0, 34.0, TS_0901, 5000],
        [73.0, 34.0, TS_0920, -3000],
    ],
}


class _FakeCollection:
    def __init__(self, image_id):
        self._rows = _CANNED[image_id]

    def filter(self, filt):
        return self

    def select(self, band):
        return self

    def size(self):
        return _FakeRegion(len(self._rows))

    def getRegion(self, point, scale):
        return _FakeRegion(self._rows)


class _FakeImageCollection:
    def __new__(cls, image_id):
        return _FakeCollection(image_id)


class _FakeFilter:
    @staticmethod
    def date(start, end):
        return ("date", start, end)


class _FakeGeometry:
    @staticmethod
    def Point(coords):
        return tuple(coords)


class _FakeEE:
    Geometry = _FakeGeometry
    Filter = _FakeFilter
    ImageCollection = _FakeImageCollection


def test_fetch_series_with_fake_ee():
    svc = GeeFeatureService(session=None, ee_module=_FakeEE)
    series = svc.fetch_series(34.0, 73.0, date(2026, 9, 1), date(2026, 9, 22))
    assert series[date(2026, 9, 20)] == {"rainfall_mm": 12.5, "et_mm": 10.0}
    assert series[date(2026, 9, 21)] == {"rainfall_mm": 0.5}
    assert series[date(2026, 9, 1)] == {"ndvi": 0.5}


# ── GeeFeatureService.store ───────────────────────────────────────────────

class _FakeExecResult:
    def mappings(self):
        return self

    def all(self):
        return []


class _FakeSession:
    def __init__(self):
        self.statements = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.statements.append((str(stmt), params))
        return _FakeExecResult()

    def commit(self):
        self.commits += 1


def test_store_upserts_with_coalesce():
    session = _FakeSession()
    svc = GeeFeatureService(session=session, ee_module=_FakeEE)
    svc.store(5, date(2026, 9, 20), {"rainfall_mm": 1.0, "ndvi": 0.4})
    sql, params = session.statements[-1]
    assert "ON CONFLICT (asset_id, observed_on)" in sql
    assert "COALESCE" in sql
    assert params == {
        "asset_id": 5,
        "observed_on": date(2026, 9, 20),
        "rainfall": 1.0,
        "et": None,
        "ndvi": 0.4,
    }
    assert session.commits == 1
