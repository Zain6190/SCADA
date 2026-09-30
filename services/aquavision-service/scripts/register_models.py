"""
scripts/register_models.py
AquaVision - Register trained models in aquavision.model_versions and apply
validation-driven lifecycle transitions.

- Enumerates trained artifacts: flood predictors (3/7/14/30d), high-flow
  predictors (7/14/30d) and flood classifiers — one registry row per
  asset/type/horizon. Quantile interval companions are not separate
  lifecycle entries and are skipped.
- Links the latest walk-forward validation report where one exists and
  transitions EXPERIMENTAL rows per its recommendation:
  SHADOW -> SHADOW, REJECTED -> REJECTED, EXPERIMENTAL -> stays.
- Idempotent: re-running refreshes metrics/notes on existing rows.

Usage:
    python -m scripts.register_models   (run after validate_all_models)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("register_models")

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "flood_xgb"
CLASSIFIER_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
METADATA_PATH = CLASSIFIER_DIR / "model_metadata.json"
VERSION = "xgb-flood-v1.2"

FLOOD_HORIZONS = (3, 7, 14, 30)
HIGHFLOW_HORIZONS = (7, 14, 30)
METRIC_KEYS = ("mae", "rmse", "r2", "mape", "train_samples", "test_samples", "status")
WALK_FORWARD_KEYS = ("mae", "rmse", "r2", "mape", "score", "persistence_mae", "mae_improvement_pct")


def load_metadata() -> dict:
    if not METADATA_PATH.exists():
        logger.warning(f"No model metadata at {METADATA_PATH}; registry metrics will be empty")
        return {}
    with open(METADATA_PATH) as f:
        return json.load(f)


def metadata_entry(metadata: dict, asset_id: int, key: str) -> dict:
    assets = metadata.get("assets") or {}
    asset = assets.get(str(asset_id)) or assets.get(asset_id) or {}
    models = asset.get("models") or {}
    return models.get(key) or {}


def collect_models(metadata: dict) -> list:
    models = []
    for path in sorted(MODEL_DIR.glob("[0-9]*.joblib")):
        stem = path.stem
        if stem.endswith("_hf") or stem.endswith("_interval"):
            continue
        parts = stem.split("_")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        asset_id, horizon = int(parts[0]), int(parts[1])
        if horizon not in FLOOD_HORIZONS:
            continue
        models.append({
            "model_type": "flood_predictor",
            "asset_id": asset_id,
            "horizon": horizon,
            "metadata_key": f"flood_predictor_{horizon}",
        })
    for path in sorted(MODEL_DIR.glob("[0-9]*_*_hf.joblib")):
        parts = path.stem[: -len("_hf")].split("_")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        asset_id, horizon = int(parts[0]), int(parts[1])
        if horizon not in HIGHFLOW_HORIZONS:
            continue
        models.append({
            "model_type": "high_flow_predictor",
            "asset_id": asset_id,
            "horizon": horizon,
            "metadata_key": f"high_flow_{horizon}",
        })
    for path in sorted(CLASSIFIER_DIR.glob("flood_classifier_asset_*.pkl")):
        suffix = path.stem.rsplit("_", 1)[-1]
        if not suffix.isdigit():
            continue
        models.append({
            "model_type": "flood_classifier",
            "asset_id": int(suffix),
            "horizon": 7,
            "metadata_key": None,
        })
    for m in models:
        m["version"] = f"{VERSION}-h{m['horizon']}"
    return models


def main():
    from infrastructure.db.engine import SessionLocal
    from infrastructure.db.models import ModelVersionDB, ValidationReportDB
    from ml.validation.model_registry import ModelRegistry, ModelStatus

    metadata = load_metadata()
    models = collect_models(metadata)
    logger.info(f"Found {len(models)} trained models to register")

    registered = updated = to_shadow = to_rejected = stayed = 0

    with SessionLocal() as session:
        registry = ModelRegistry(session)

        reports = (
            session.query(ValidationReportDB)
            .filter(ValidationReportDB.model_type == "flood_predictor")
            .order_by(ValidationReportDB.validated_at.desc())
            .all()
        )
        latest = {}
        for report in reports:
            key = (report.asset_id, report.horizon)
            if key not in latest:
                latest[key] = report

        for m in models:
            entry = (
                metadata_entry(metadata, m["asset_id"], m["metadata_key"])
                if m["metadata_key"]
                else {}
            )
            metrics = {k: entry[k] for k in METRIC_KEYS if entry.get(k) is not None}
            report = latest.get((m["asset_id"], m["horizon"])) if m["model_type"] == "flood_predictor" else None
            if report is not None:
                metrics["walk_forward"] = {
                    k: report.metrics.get(k) for k in WALK_FORWARD_KEYS if report.metrics.get(k) is not None
                }

            existing = (
                session.query(ModelVersionDB)
                .filter(
                    ModelVersionDB.model_type == m["model_type"],
                    ModelVersionDB.asset_id == m["asset_id"],
                    ModelVersionDB.version == m["version"],
                )
                .first()
            )
            if existing:
                existing.metrics = metrics
                existing.validation_report_id = report.id if report else None
                existing.notes = f"Refreshed from retrain; validation: {report.recommendation if report else 'pending'}"
                session.commit()
                mv_id, status = existing.id, existing.status
                updated += 1
            else:
                mv_id = registry.register(
                    model_type=m["model_type"],
                    version=m["version"],
                    asset_id=m["asset_id"],
                    metrics=metrics,
                    notes=f"Validation: {report.recommendation if report else 'pending'}",
                )
                mv = session.get(ModelVersionDB, mv_id)
                mv.validation_report_id = report.id if report else None
                session.commit()
                status = ModelStatus.EXPERIMENTAL.value
                registered += 1

            target = None
            if report is not None:
                if report.recommendation == "SHADOW":
                    target = ModelStatus.SHADOW
                elif report.recommendation == "REJECTED":
                    target = ModelStatus.REJECTED

            if target is None:
                stayed += 1
            elif status != ModelStatus.EXPERIMENTAL.value:
                stayed += 1
                logger.info(
                    f"{m['model_type']} asset={m['asset_id']} h{m['horizon']}: "
                    f"already {status}, validation says {report.recommendation} (kept)"
                )
            elif registry.transition(mv_id, target, notes=f"Walk-forward report {report.id}"):
                if target == ModelStatus.SHADOW:
                    to_shadow += 1
                else:
                    to_rejected += 1
            else:
                logger.warning(
                    f"{m['model_type']} asset={m['asset_id']} h{m['horizon']}: transition to {target.value} failed"
                )

    logger.info("=" * 60)
    logger.info("REGISTRATION COMPLETE:")
    logger.info(f"  Registered (new):      {registered}")
    logger.info(f"  Refreshed (existing):  {updated}")
    logger.info(f"  Transitioned -> SHADOW:    {to_shadow}")
    logger.info(f"  Transitioned -> REJECTED:  {to_rejected}")
    logger.info(f"  Stayed EXPERIMENTAL/other: {stayed}")
    logger.info("=" * 60)

    return {"registered": registered, "updated": updated, "shadow": to_shadow, "rejected": to_rejected}


if __name__ == "__main__":
    main()
