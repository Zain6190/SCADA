"""Shared WAI feature contract for train / predict / risk stages.

Training and serving must feed the model the exact same columns. The contract
is the four raw GEE features from Data/raw/region_features.csv plus the
derived calendar-month index: the only fields the serving path can always
supply. Legacy dataset.csv also carried sm_rootzone/sm_surface, but no serving
script can rebuild those columns, so they are deliberately excluded: a feature
the server cannot reproduce must not be in the model.
"""
from __future__ import annotations

FEATURE_COLS = ["rainfall_mm", "et_mm", "water_extent", "ndvi", "month_idx"]
TARGET_COL = "wai_score"
SEVERITY_COL = "severity"
