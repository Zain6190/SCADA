"""
gee/validate_dataset.py
AquaVision - Validate the GEE-derived dataset before it feeds the risk workflow.

Checks:
  1. Row/source integrity (regions, months, duplicates)
  2. Missing-data coverage per feature
  3. Sentinel handling (water_extent == -1 after JRC ends ~2021)
  4. Distribution sanity (ranges, zero/negative values)
  5. Label sanity (WAI 0-100, severity consistency with thresholds)

Exit code non-zero on FAILURE (so CI/pipeline can gate on it).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW_CSV = Path(__file__).resolve().parent.parent / "Data" / "raw" / "region_features.csv"
DSET_CSV = Path(__file__).resolve().parent.parent / "Data" / "features" / "dataset.csv"

FEATURES = ["rainfall_mm", "et_mm", "water_extent", "ndvi"]
EXPECTED_REGION_IDS = set(range(1, 19))  # shared.regions ids 1..18
EXPECTED_SENTINEL = -1.0

SEVERITY_BOUNDS = [
    ("Normal", 70, 101),
    ("Moderate", 55, 70),
    ("Stressed", 40, 55),
    ("Severe", 25, 40),
    ("Critical", 0, 25),
]


def severity_of(wai: float) -> str:
    for name, lo, hi in SEVERITY_BOUNDS:
        if lo <= wai < hi:
            return name
    return "Unknown"


def main() -> int:
    failures = []

    raw = pd.read_csv(RAW_CSV)
    ds = pd.read_csv(DSET_CSV)
    raw["month"] = pd.to_datetime(raw["month"])
    ds["month"] = pd.to_datetime(ds["month"])

    # ---- 1. Integrity ----
    n_regions_raw = raw["region_id"].nunique()
    missing_ids = EXPECTED_REGION_IDS - set(raw["region_id"].unique())
    if missing_ids:
        failures.append(f"MISSING regions in raw: {sorted(missing_ids)}")
    if n_regions_raw != 18:
        failures.append(f"raw has {n_regions_raw} regions, expected 18")

    dups = raw.duplicated(["region_id", "month"]).sum()
    if dups:
        failures.append(f"{dups} duplicate (region,month) rows in raw")

    # ---- 2. Missing data ----
    print("\nMissing-data coverage (raw):")
    for c in FEATURES:
        n = raw[c].isna().sum()
        print(f"  {c:14s} missing={n:5d} ({100*n/len(raw):.1f}%)")

    # ---- 3. Sentinel handling ----
    n_sentinel = int((raw["water_extent"] == EXPECTED_SENTINEL).sum())
    print(f"\nwater_extent == -1 sentinel (JRC no-data) count: {n_sentinel}")
    yrs = raw[raw["water_extent"] == EXPECTED_SENTINEL]["month"].dt.year.unique()
    print(f"sentinel present in years: {sorted(yrs)}")

    other_sentinel_bad = (raw[FEATURES].drop(columns=["et_mm"]) == EXPECTED_SENTINEL).sum().sum()
    if other_sentinel_bad - (raw["water_extent"] == EXPECTED_SENTINEL).sum() > 0:
        failures.append("-1 sentinel leaking into non-water_extent features (means it's real data)")

    # ensure -1s were converted to NaN downstream before training
    ds_water = ds.get("water_extent")
    if ds_water is not None and (ds_water == -1).any():
        failures.append("dataset.csv still contains -1 in water_extent (should be NaN)")

    # ---- 4. Distributions / ranges ----
    print("\nFeature ranges (raw, ignoring sentinel):")
    for c in FEATURES:
        subsample = raw[c].replace(-1, np.nan)
        if subsample.notna().any():
            print(f"  {c:16s} min={subsample.min():.3f} max={subsample.max():.3f} mean={subsample.mean():.3f}")
        else:
            print(f"  {c:16s} (all missing)")

    if ds["wai_score"].min() < 0 or ds["wai_score"].max() > 100:
        failures.append(f"WAI out of [0,100]: [{ds['wai_score'].min()}, {ds['wai_score'].max()}]")

    # rainfall can't be negative in reality (CHIRPS >= 0)
    if (raw["rainfall_mm"] < 0).any():
        failures.append("negative rainfall_mm found (should be >= 0)")

    # ---- 5. Label sanity ----
    expected_sev = ds["wai_score"].apply(severity_of)
    wrong = (expected_sev != ds["severity"]).sum()
    if wrong:
        failures.append(f"{wrong} rows have severity label inconsistent with wai_score thresholds")

    print("\nDataset label ranges:")
    print(f"  target wai_score: [{ds['wai_score'].min():.2f}, {ds['wai_score'].max():.2f}]")
    print(f"  rows: {len(ds)}, regions: {ds['region_id'].nunique()}, "
          f"months: {ds['month'].nunique()}")
    print(f"  severity counts:\n{ds['severity'].value_counts().to_string()}")

    # ---- Summary ----
    print("\n=================== VALIDATION ===================")
    if failures:
        for f in failures:
            print(f"  [FAIL] {f}")
        print(f"\nDataset INVALID: {len(failures)} issue(s)")
        sys.exit(1)
    else:
        print("  Dataset VALID - passed all checks")
        sys.exit(0)


if __name__ == "__main__":
    main()