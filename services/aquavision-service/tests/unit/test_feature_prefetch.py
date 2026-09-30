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
    assert session.calls == 3

    assert builder._get_threshold(1).warning_level_ft == 10.0
    assert builder._get_ffd_status(1, datetime(2026, 5, 1, 12)) == "LOW"
    assert builder._get_ffd_status(1, datetime(2026, 5, 2, 6)) == "HIGH"
    assert builder._get_ffd_status(1, datetime(2026, 5, 3)) is None
    assert session.calls == 3

    weather = builder._get_weather_forecast(1, datetime(2026, 4, 30))
    assert weather["precip_sum_mm"] == 99.0
    assert builder._get_weather_forecast(1, datetime(2026, 5, 10)) is None
    assert session.calls == 3


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
    assert session.calls == 3

    assert builder._get_ffd_status(1, datetime(2026, 6, 10)) is None
    assert session.calls == 4
