from datetime import datetime, date
from types import SimpleNamespace

from ml.features.feature_engineering import FloodFeatureBuilder


class _FakeResult:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        if not self._results:
            raise AssertionError(f"unexpected query #{self.calls}")
        return self._results.pop(0)


def _make_session():
    threshold = SimpleNamespace(warning_level_ft=10.0, danger_level_ft=12.0)
    ffd_rows = [
        (datetime(2026, 5, 1, tzinfo=None), "LOW"),
        (datetime(2026, 5, 2, tzinfo=None), "HIGH"),
    ]
    weather_rows = [
        SimpleNamespace(
            forecast_date=date(2026, 4, 28),
            horizon_days=3,
            fetched_at=datetime(2026, 4, 27),
            precip_sum_mm=99.0,
            temp_max_c=31.0,
            humidity_mean_pct=60.0,
        ),
        SimpleNamespace(
            forecast_date=date(2026, 4, 25),
            horizon_days=7,
            fetched_at=datetime(2026, 4, 20),
            precip_sum_mm=10.0,
            temp_max_c=30.0,
            humidity_mean_pct=50.0,
        ),
    ]
    return _FakeSession([
        _FakeResult(scalar=threshold),
        _FakeResult(rows=ffd_rows),
        _FakeResult(rows=weather_rows),
        _FakeResult(rows=[]),
    ])


def test_prefetch_replaces_per_row_lookups():
    session = _make_session()
    builder = FloodFeatureBuilder(session)

    builder.prefetch_asset_features(
        asset_id=1,
        start_date=datetime(2026, 4, 1),
        end_date=datetime(2026, 5, 31),
        dates={datetime(2026, 4, 30)},
    )
    assert session.calls == 4

    assert builder._get_threshold(1).warning_level_ft == 10.0
    assert builder._get_ffd_status(1, datetime(2026, 5, 1, 12)) == "LOW"
    assert builder._get_ffd_status(1, datetime(2026, 5, 2, 6)) == "HIGH"
    assert builder._get_ffd_status(1, datetime(2026, 5, 3)) is None
    assert session.calls == 4

    weather = builder._get_weather_forecast(1, datetime(2026, 4, 30))
    assert weather["precip_sum_mm"] == 99.0
    assert builder._get_weather_forecast(1, datetime(2026, 5, 10)) is None
    assert session.calls == 4

    assert builder._get_gee_row(1, datetime(2026, 4, 30)) is None
    assert session.calls == 4


def test_out_of_span_date_falls_back_to_query():
    session = _make_session()
    session._results.append(_FakeResult(scalar=None))
    builder = FloodFeatureBuilder(session)

    builder.prefetch_asset_features(
        asset_id=1,
        start_date=datetime(2026, 4, 1),
        end_date=datetime(2026, 5, 31),
        dates=set(),
    )
    assert session.calls == 4

    assert builder._get_ffd_status(1, datetime(2026, 6, 10)) is None
    assert session.calls == 5


def test_prefetch_fills_gee_cache_and_span():
    from datetime import date

    session = _make_session()
    session._results[3] = _FakeResult(rows=[
        {"observed_on": date(2026, 4, 30), "rainfall_mm": 12.5, "et_mm": 3.1, "ndvi": 0.42},
        {"observed_on": date(2026, 4, 25), "rainfall_mm": 7.0, "et_mm": None, "ndvi": None},
    ])
    builder = FloodFeatureBuilder(session)

    builder.prefetch_asset_features(
        asset_id=1,
        start_date=datetime(2026, 4, 1),
        end_date=datetime(2026, 5, 31),
        dates=set(),
    )
    assert session.calls == 4

    row = builder._get_gee_row(1, datetime(2026, 4, 30))
    assert row["rainfall_mm"] == 12.5
    assert builder._get_gee_row(1, datetime(2026, 4, 26)) is None
    assert session.calls == 4


def test_gee_rain_window_sums_most_recent_rows_in_lookback():
    from datetime import date

    builder = FloodFeatureBuilder(session=None)
    span_start, span_end = date(2026, 1, 1), date(2026, 12, 31)
    builder._gee_span = (span_start, span_end)
    builder._gee_cache[(7, date(2026, 9, 30))] = {"observed_on": date(2026, 9, 30), "rainfall_mm": 5.0, "et_mm": 2.0, "ndvi": 0.5}
    builder._gee_cache[(7, date(2026, 9, 29))] = {"observed_on": date(2026, 9, 29), "rainfall_mm": 3.5, "et_mm": None, "ndvi": None}
    builder._gee_cache[(7, date(2026, 9, 20))] = {"observed_on": date(2026, 9, 20), "rainfall_mm": 10.0, "et_mm": 1.0, "ndvi": 0.3}

    assert builder._gee_rain_window(7, datetime(2026, 9, 30), 1) == 5.0
    assert builder._gee_rain_window(7, datetime(2026, 9, 30), 3) == 18.5
    assert builder._gee_recent_value(7, datetime(2026, 9, 30), "et_mm") == 2.0
    assert builder._gee_recent_value(7, datetime(2026, 9, 30), "ndvi") == 0.5


def test_gee_lookback_covers_catalog_lag():
    from datetime import date

    builder = FloodFeatureBuilder(session=None)
    builder._gee_span = (date(2026, 1, 1), date(2026, 12, 31))
    builder._gee_cache[(7, date(2026, 8, 30))] = {"observed_on": date(2026, 8, 30), "rainfall_mm": 8.0, "et_mm": 2.5, "ndvi": 0.4}

    assert builder._gee_rain_window(7, datetime(2026, 9, 25), 1) == 8.0
    assert builder._gee_recent_value(7, datetime(2026, 9, 25), "et_mm") == 2.5


def test_gee_no_coverage_in_lookback_returns_zero():
    builder = FloodFeatureBuilder(session=None)
    builder._gee_span = (date(2020, 1, 1), date(2026, 12, 31))

    assert builder._gee_rain_window(7, datetime(2023, 6, 1), 7) == 0.0
    assert builder._gee_recent_value(7, datetime(2023, 6, 1), "ndvi") == 0.0


def test_gee_out_of_span_fetch_resolves_whole_lookback_once():
    session = _FakeSession([
        _FakeResult(rows=[
            {"observed_on": date(2026, 6, 10), "rainfall_mm": 4.0, "et_mm": None, "ndvi": None},
        ]),
    ])
    builder = FloodFeatureBuilder(session)

    assert builder._gee_rain_window(1, datetime(2026, 6, 20), 3) == 4.0
    assert session.calls == 1
    assert builder._gee_recent_value(1, datetime(2026, 6, 20), "et_mm") == 0.0
    assert builder._get_gee_row(1, datetime(2026, 6, 19)) is None
    assert session.calls == 1
