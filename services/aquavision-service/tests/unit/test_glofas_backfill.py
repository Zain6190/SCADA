import datetime as dt

import pytest

from ml.features.feature_engineering import keep_training_row, usable_for_training
from scripts.backfill_glofas import (
    AREA_NORTH_WEST_SOUTH_EAST,
    CUSECS_PER_M3S,
    build_request,
    extract_series,
    rows_for_asset,
)

WINDOW_START = dt.date(2022, 1, 1)
WINDOW_END = dt.date(2026, 9, 30)


def test_request_for_full_year():
    req = build_request(2023, WINDOW_START, WINDOW_END)
    assert req["hyear"] == ["2023"]
    assert req["hmonth"] == [f"{m:02d}" for m in range(1, 13)]
    assert req["data_format"] == "netcdf"
    assert req["area"] == AREA_NORTH_WEST_SOUTH_EAST
    assert req["product_type"] == ["consolidated"]


def test_request_trims_months_to_window():
    req = build_request(2022, dt.date(2022, 3, 15), dt.date(2022, 6, 5))
    assert req["hmonth"] == ["03", "04", "05", "06"]
    first = build_request(2022, WINDOW_START, dt.date(2022, 2, 10))
    assert first["hmonth"] == ["01", "02"]
    last = build_request(2026, dt.date(2026, 11, 1), dt.date(2026, 12, 15))
    assert last["hmonth"] == ["11", "12"]
    inverted = build_request(2026, dt.date(2026, 11, 1), WINDOW_END)
    assert inverted["hmonth"] == []


def test_rows_carry_honest_reanalysis_provenance():
    series = [(dt.date(2024, 6, 1), 2000.0)]
    rows = rows_for_asset(3, series, source_id=99)
    assert len(rows) == 1
    row = rows[0]
    assert row["asset_id"] == 3
    assert row["source_id"] == 99
    assert row["data_origin"] == "REANALYSIS"
    assert row["data_status"] == "GLOFAS_REANALYSIS"
    assert row["source_authority"] == "GLOFAS"
    assert row["source_priority"] == 5
    assert row["observed_at"] == dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc)
    assert row["discharge_cusecs"] == pytest.approx(2000.0 * CUSECS_PER_M3S, rel=1e-6)


def test_reanalysis_rows_train_but_below_real_and_never_as_soft_ot():
    assert usable_for_training("REANALYSIS", "GLOFAS") is True
    assert keep_training_row("REANALYSIS", "GLOFAS", real_only=True) is True
    assert usable_for_training("REANALYSIS", "SOFT_OT") is False
    assert keep_training_row("REANALYSIS", "SOFT_OT", real_only=True) is False
    assert keep_training_row("SYNTHETIC", "SYNTHETIC_HISTORICAL", real_only=True) is False
    assert keep_training_row("SCENARIO", "SOFT_OT", real_only=True) is False
    assert usable_for_training("REAL", "IRSA") is True


@pytest.fixture(scope="module")
def sample_nc(tmp_path_factory):
    netCDF4 = pytest.importorskip("netCDF4")
    path = tmp_path_factory.mktemp("glofas") / "sample.nc"
    nc = netCDF4.Dataset(str(path), "w", format="NETCDF4")
    nc.createDimension("time", 3)
    nc.createDimension("latitude", 2)
    nc.createDimension("longitude", 2)
    times = nc.createVariable("time", "f8", ("time",))
    times.units = "hours since 1900-01-01 00:00:00"
    times[:] = [
        (dt.datetime(2024, 6, d) - dt.datetime(1900, 1, 1)).total_seconds() / 3600
        for d in (1, 2, 3)
    ]
    lats = nc.createVariable("latitude", "f4", ("latitude",))
    lats[:] = [30.0, 32.0]
    lons = nc.createVariable("longitude", "f4", ("longitude",))
    lons[:] = [70.0, 72.0]
    dis = nc.createVariable("dis24", "f4", ("time", "latitude", "longitude"))
    dis.long_name = "River discharge in the last 24 hours"
    dis[:] = [
        [[100.0, 110.0], [120.0, 130.0]],
        [[101.0, 111.0], [-9999.0, 131.0]],
        [[102.0, 112.0], [122.0, float("nan")]],
    ]
    nc.close()
    return path


def test_extract_series_nearest_cell(sample_nc):
    series = extract_series(sample_nc, lat=31.5, lon=71.5)
    assert [d for d, _ in series] == [
        dt.date(2024, 6, 1),
        dt.date(2024, 6, 2),
    ]
    assert [v for _, v in series] == pytest.approx([130.0, 131.0])


def test_extract_series_skips_missing_and_dry_cells(sample_nc):
    series = extract_series(sample_nc, lat=32.0, lon=70.0)
    values = [v for _, v in series]
    assert values == pytest.approx([120.0, 122.0])
    assert -9999.0 not in values
    assert all(v > 0 for v in values)


def test_extract_series_skips_other_corner(sample_nc):
    series = extract_series(sample_nc, lat=30.0, lon=70.0)
    assert [v for _, v in series] == pytest.approx([100.0, 101.0, 102.0])
