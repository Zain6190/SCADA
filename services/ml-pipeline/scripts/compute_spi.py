"""Compute SPI (Standardized Precipitation Index) from historical rainfall.

SPI is calculated per region by fitting a gamma distribution to monthly
rainfall totals, then converting to standard normal via inverse CDF.

Scales computed: SPI-1 (1-month), SPI-3 (3-month), SPI-6 (6-month), SPI-12 (12-month).

WMO Drought Classification:
  SPI > 2.0        Extremely wet
  1.5 to 2.0       Severely wet
  1.0 to 1.5       Moderately wet
  0.0 to 1.0       Near normal (wet)
  -1.0 to 0.0      Near normal (dry)
  -1.5 to -1.0     Moderately dry
  -2.0 to -1.5     Severely dry
  SPI < -2.0       Extremely dry
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from statistics import median

import numpy as np
from scipy import stats as scipy_stats
from sqlalchemy import create_engine, text

ML_ROOT = Path(__file__).resolve().parent.parent
DB_URL = "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"

SCALES = [1, 3, 6, 12]

DROUGHT_CLASSES = [
    (-999, -2.0, "extreme_drought"),
    (-2.0, -1.5, "severe_drought"),
    (-1.5, -1.0, "moderate_drought"),
    (-1.0, 0.0, "mild_drought"),
    (0.0, 1.0, "near_normal"),
    (1.0, 1.5, "moderately_wet"),
    (1.5, 2.0, "severely_wet"),
    (2.0, 999, "extremely_wet"),
]


def _classify_drought(spi: float) -> str:
    for lo, hi, label in DROUGHT_CLASSES:
        if lo <= spi < hi:
            return label
    return "near_normal"


def _gamma_fit_cdf(values: np.ndarray) -> np.ndarray | None:
    """Fit gamma distribution and return CDF values. Returns None if fit fails."""
    if len(values) < 12:
        return None
    try:
        # Remove zeros (SPI treats zero-rain months specially)
        positive = values[values > 0]
        if len(positive) < 6:
            return None
        shape, loc, scale = scipy_stats.gamma.fit(positive, floc=0)
        cdf = scipy_stats.gamma.cdf(values, shape, loc=loc, scale=scale)
        # Handle zero-rain: assign CDF = proportion of zero-rain months
        n_zeros = np.sum(values == 0)
        proportion_zero = n_zeros / len(values)
        cdf[values == 0] = proportion_zero * cdf[values == 0]
        return cdf
    except Exception:
        return None


def _cdf_to_spi(cdf: np.ndarray) -> np.ndarray:
    """Convert CDF to SPI via inverse normal CDF."""
    # Clamp to avoid infinities
    cdf = np.clip(cdf, 0.001, 0.999)
    return scipy_stats.norm.ppf(cdf)


def compute_spi_for_region(
    rainfall_monthly: list[tuple[str, float]],
) -> dict[str, float | None]:
    """Compute SPI for all scales given monthly rainfall data.

    Uses calendar-month grouping: each month is compared against
    the same calendar month in all prior years.

    Args:
        rainfall_monthly: [(month_str, rainfall_mm), ...] sorted chronologically

    Returns:
        {"spi_1": val, "spi_3": val, ...} for the most recent month
    """
    if len(rainfall_monthly) < 24:
        return {f"spi_{s}": None for s in SCALES}

    values = np.array([r for _, r in rainfall_monthly], dtype=float)
    months_idx = np.array([int(m.split("-")[1]) - 1 for m, _ in rainfall_monthly])
    results = {}

    for scale in SCALES:
        if len(values) < scale:
            results[f"spi_{scale}"] = None
            continue

        # Compute cumulative rainfall over the scale window
        cumsum = np.cumsum(values)
        cumsum[scale:] = cumsum[scale:] - cumsum[:-scale]
        cum_values = cumsum[scale - 1:]
        cum_months = months_idx[scale - 1:]

        if len(cum_values) < 24:
            results[f"spi_{scale}"] = None
            continue

        # Group cumulative values by calendar month
        last_month_idx = int(cum_months[-1])
        same_month_vals = cum_values[cum_months == last_month_idx]

        if len(same_month_vals) < 3:
            # Not enough same-month data, fall back to all-month fitting
            cdf = _gamma_fit_cdf(cum_values)
            if cdf is None:
                results[f"spi_{scale}"] = None
                continue
            spi_values = _cdf_to_spi(cdf)
            results[f"spi_{scale}"] = round(float(spi_values[-1]), 2)
        else:
            # Fit gamma on same calendar month historically, then evaluate last value
            try:
                positive = same_month_vals[same_month_vals > 0]
                if len(positive) < 3:
                    results[f"spi_{scale}"] = None
                    continue
                shape, loc, scale_param = scipy_stats.gamma.fit(positive, floc=0)
                cdf_val = scipy_stats.gamma.cdf(same_month_vals[-1], shape, loc=loc, scale=scale_param)
                # Handle zero-rain
                if same_month_vals[-1] == 0:
                    n_zeros = np.sum(same_month_vals == 0)
                    cdf_val = (n_zeros / len(same_month_vals)) * 0.5
                cdf_val = max(0.001, min(0.999, cdf_val))
                spi_val = float(scipy_stats.norm.ppf(cdf_val))
                results[f"spi_{scale}"] = round(spi_val, 2)
            except Exception:
                results[f"spi_{scale}"] = None

    return results


def load_csv(csv_path: Path) -> dict[int, list[tuple[str, float]]]:
    """Load region_features.csv, return {region_id: [(month, rainfall_mm), ...]}."""
    data: dict[int, list[tuple[str, float]]] = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = int(row["region_id"])
            month = row["month"]
            rainfall_str = row["rainfall_mm"].strip()
            rainfall = float(rainfall_str) if rainfall_str else 0.0
            data.setdefault(rid, []).append((month, rainfall))
    # Sort each region's data chronologically
    for rid in data:
        data[rid].sort(key=lambda x: x[0])
    return data


def write_spi_to_db(engine, spi_results: dict[int, dict]) -> int:
    """Write SPI values to water_indicators_weekly. Returns rows updated."""
    updated = 0
    with engine.begin() as conn:
        for region_id, spi in spi_results.items():
            # Find the latest week for this region
            latest = conn.execute(
                text(
                    "SELECT id FROM aquavision.water_indicators_weekly "
                    "WHERE region_id = :rid ORDER BY week_start_date DESC LIMIT 1"
                ),
                {"rid": region_id},
            ).scalar()
            if latest is None:
                continue
            conn.execute(
                text(
                    "UPDATE aquavision.water_indicators_weekly "
                    "SET spi_1 = :spi1, spi_3 = :spi3, spi_6 = :spi6, "
                    "spi_12 = :spi12, spi_drought_class = :dclass "
                    "WHERE id = :id"
                ),
                {
                    "spi1": spi.get("spi_1"),
                    "spi3": spi.get("spi_3"),
                    "spi6": spi.get("spi_6"),
                    "spi12": spi.get("spi_12"),
                    "dclass": _classify_drought(spi.get("spi_1")),
                    "id": latest,
                },
            )
            updated += 1
    return updated


def main(csv_path: Path | None = None) -> None:
    if csv_path is None:
        csv_path = ML_ROOT / "Data" / "raw" / "region_features.csv"

    if not csv_path.exists():
        print(f"[compute_spi] CSV not found: {csv_path}")
        sys.exit(1)

    print(f"[compute_spi] Loading {csv_path}")
    data = load_csv(csv_path)
    print(f"[compute_spi] {len(data)} regions, {sum(len(v) for v in data.values())} total months")

    engine = create_engine(DB_URL)
    spi_results: dict[int, dict] = {}

    for region_id in sorted(data.keys()):
        months_data = data[region_id]
        spi = compute_spi_for_region(months_data)
        spi_results[region_id] = spi
        spi1 = spi.get("spi_1")
        spi3 = spi.get("spi_3")
        drought = _classify_drought(spi1) if spi1 is not None else "N/A"
        print(f"  Region {region_id:2d}: SPI-1={spi1 or 'N/A':>6}  SPI-3={spi3 or 'N/A':>6}  class={drought}")

    updated = write_spi_to_db(engine, spi_results)
    print(f"[compute_spi] Updated {updated} rows in water_indicators_weekly")


if __name__ == "__main__":
    csv_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(Path(csv_arg) if csv_arg else None)
