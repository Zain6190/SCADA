"""Weather history bridge: archive backfill mapping + forecast slicing.

Training features read DAILY (horizon 0) weather rows; forward aggregates
(7/14/16) must cover only the future window — past_days must never leak
into them.
"""
from datetime import date, timedelta

from ml.features.weather_service import WeatherService
from scripts.backfill_weather import rows_from_daily


class TestRowsFromDaily:
    DAILY = {
        "time": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "precipitation_sum": [1.5, None, 0.0],
        "temperature_2m_max": [20.0, 21.0, 22.0],
        "temperature_2m_min": [5.0, 6.0, 7.0],
        "relative_humidity_2m_mean": [60, 61, 62],
        "wind_speed_10m_max": [10.0, 11.0, 12.0],
    }

    def test_maps_arrays_to_rows(self):
        rows = rows_from_daily(self.DAILY, asset_id=2, horizon_days=0)
        assert len(rows) == 3
        assert rows[0] == {
            "asset_id": 2,
            "forecast_date": "2026-01-01",
            "horizon_days": 0,
            "precip_sum_mm": 1.5,
            "temp_max_c": 20.0,
            "temp_min_c": 5.0,
            "humidity_mean_pct": 60,
            "wind_speed_kmh": 10.0,
        }

    def test_keeps_days_without_rain_but_skips_fully_empty(self):
        rows = rows_from_daily(self.DAILY, asset_id=1)
        # 2026-01-02 has null precip but valid temp/humidity -> kept
        assert len(rows) == 3
        assert rows[1]["precip_sum_mm"] is None
        # fully empty day (no precip/temp/humidity) -> dropped
        sparse = {"time": ["2026-01-04"], "precipitation_sum": [None]}
        assert rows_from_daily(sparse, asset_id=1) == []

    def test_handles_short_arrays(self):
        rows = rows_from_daily({"time": ["2026-01-01", "2026-01-02"],
                                "precipitation_sum": [3.0]},
                               asset_id=1)
        # second day has no values at all -> dropped, not emitted as nulls
        assert len(rows) == 1
        assert rows[0]["precip_sum_mm"] == 3.0


class TestForecastSlicing:
    def _service_with(self, dates, precip):
        ws = WeatherService(session=None)
        n = len(dates)
        ws.get_forecast = lambda asset_id, lat, lon: {
            "dates": dates,
            "precip_sum": precip,
            "temp_max": [20.0] * n,
            "temp_min": [5.0] * n,
            "humidity_mean": [60.0] * n,
            "wind_speed": [10.0] * n,
            "_ts": 0.0,
        }
        return ws

    def test_past_days_never_enter_forward_aggregate(self):
        today = date.today()
        past = [(today - timedelta(days=i)).isoformat() for i in range(7, 0, -1)]
        future = [(today + timedelta(days=i)).isoformat() for i in range(1, 17)]
        dates = past + [today.isoformat()] + future
        precip = [1000.0] * len(past) + [5.0] + [1.0] * len(future)

        ws = self._service_with(dates, precip)
        agg = ws.get_forecasts_for_horizon(1, 0.0, 0.0, horizon_days=7)
        # 7 days from TODAY inclusive: 5.0 + 6x1.0 — the 1000mm past week
        # must not count
        assert agg["precip_sum_mm"] == 11.0

    def test_aggregate_capped_at_horizon(self):
        today = date.today().isoformat()
        dates = [today] + [
            date.fromordinal(date.today().toordinal() + i).isoformat()
            for i in range(16)
        ]
        precip = [50.0] * len(dates)
        ws = self._service_with(dates, precip)
        agg = ws.get_forecasts_for_horizon(1, 0.0, 0.0, horizon_days=7)
        assert agg["precip_sum_mm"] == 350.0  # 7 x 50, not 17 days
