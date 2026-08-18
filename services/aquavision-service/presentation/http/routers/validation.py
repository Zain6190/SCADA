# presentation/http/routers/validation.py
# ML Validation reports API.
# Phase 3: ML Validation

import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger("aquavision.api.validation")

router = APIRouter(prefix="/validation", tags=["ML Validation"])


class ValidationReportResponse(BaseModel):
    id: int
    asset_id: int
    model_type: str
    model_version: str
    horizon: int
    metrics: dict
    data_info: dict
    recommendation: str
    reasons: Optional[list] = None
    fold_details: Optional[list] = None
    validated_at: str
    created_at: str


class ValidationSummary(BaseModel):
    total_reports: int
    assets_validated: int
    recommendations: dict  # {EXPERIMENTAL: N, SHADOW: N, REJECTED: N}
    best_asset: Optional[str] = None
    worst_asset: Optional[str] = None
    overall_status: str  # All models status


@router.get("/reports", response_model=List[ValidationReportResponse])
def list_validation_reports(
    asset_id: Optional[int] = None,
    model_type: Optional[str] = None,
    recommendation: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """List validation reports with optional filters."""
    from infrastructure.db.engine import SessionLocal
    from infrastructure.db.models import ValidationReportDB

    db = SessionLocal()
    try:
        q = db.query(ValidationReportDB)
        if asset_id:
            q = q.filter(ValidationReportDB.asset_id == asset_id)
        if model_type:
            q = q.filter(ValidationReportDB.model_type == model_type)
        if recommendation:
            q = q.filter(ValidationReportDB.recommendation == recommendation)

        reports = q.order_by(ValidationReportDB.created_at.desc()).limit(limit).all()

        return [
            ValidationReportResponse(
                id=r.id,
                asset_id=r.asset_id,
                model_type=r.model_type,
                model_version=r.model_version,
                horizon=r.horizon,
                metrics=r.metrics,
                data_info=r.data_info,
                recommendation=r.recommendation,
                reasons=r.reasons,
                fold_details=r.fold_details,
                validated_at=r.validated_at.isoformat() if r.validated_at else "",
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in reports
        ]
    finally:
        db.close()


@router.get("/reports/summary", response_model=ValidationSummary)
def get_validation_summary():
    """Get summary of all validation reports."""
    from infrastructure.db.engine import SessionLocal
    from infrastructure.db.models import ValidationReportDB, WaterAsset
    from sqlalchemy import func

    db = SessionLocal()
    try:
        reports = db.query(ValidationReportDB).all()

        recommendations = {}
        asset_results = {}
        for r in reports:
            rec = r.recommendation
            recommendations[rec] = recommendations.get(rec, 0) + 1

            asset = db.get(WaterAsset, r.asset_id)
            name = asset.canonical_name if asset else f"Asset {r.asset_id}"
            if name not in asset_results:
                asset_results[name] = []
            asset_results[name].append(r.metrics.get("mae", 999999))

        # Find best/worst by MAE
        best_asset = None
        worst_asset = None
        if asset_results:
            avg_mae = {name: sum(maes) / len(maes) for name, maes in asset_results.items()}
            best_asset = min(avg_mae, key=avg_mae.get)
            worst_asset = max(avg_mae, key=avg_mae.get)

        # Overall status
        if recommendations.get("PRODUCTION", 0) > 0:
            overall = "PRODUCTION"
        elif recommendations.get("APPROVED", 0) > 0:
            overall = "APPROVED"
        elif recommendations.get("SHADOW", 0) > 0:
            overall = "SHADOW"
        else:
            overall = "EXPERIMENTAL"

        return ValidationSummary(
            total_reports=len(reports),
            assets_validated=len(asset_results),
            recommendations=recommendations,
            best_asset=best_asset,
            worst_asset=worst_asset,
            overall_status=overall,
        )
    finally:
        db.close()


@router.get("/reports/{report_id}", response_model=ValidationReportResponse)
def get_validation_report(report_id: int):
    """Get a specific validation report by ID."""
    from infrastructure.db.engine import SessionLocal
    from infrastructure.db.models import ValidationReportDB

    db = SessionLocal()
    try:
        r = db.get(ValidationReportDB, report_id)
        if not r:
            raise HTTPException(status_code=404, detail="Validation report not found")

        return ValidationReportResponse(
            id=r.id,
            asset_id=r.asset_id,
            model_type=r.model_type,
            model_version=r.model_version,
            horizon=r.horizon,
            metrics=r.metrics,
            data_info=r.data_info,
            recommendation=r.recommendation,
            reasons=r.reasons,
            fold_details=r.fold_details,
            validated_at=r.validated_at.isoformat() if r.validated_at else "",
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
    finally:
        db.close()


@router.post("/run")
def run_validation(
    asset_id: Optional[int] = None,
    horizon: int = Query(7, ge=1, le=30),
):
    """Run validation for an asset (or all assets if asset_id=None)."""
    from infrastructure.db.engine import SessionLocal
    from infrastructure.db.models import WaterAsset
    from ml.validation.validation_framework import ValidationFramework

    db = SessionLocal()
    try:
        framework = ValidationFramework(db)

        if asset_id:
            asset = db.get(WaterAsset, asset_id)
            if not asset:
                raise HTTPException(status_code=404, detail="Asset not found")
            report = framework.validate_asset(
                asset_id=asset_id,
                asset_name=asset.canonical_name,
                horizon=horizon,
            )
            report_id = framework.save_report(report)
            return {
                "status": "ok",
                "report_id": report_id,
                "asset": asset.canonical_name,
                "recommendation": report.recommendation,
                "mae": report.mae,
                "r2": report.r2,
            }
        else:
            reports = framework.validate_all_assets(horizons=[horizon])
            saved = []
            for r in reports:
                rid = framework.save_report(r)
                saved.append({
                    "asset": r.asset_name,
                    "recommendation": r.recommendation,
                    "mae": r.mae,
                    "r2": r.r2,
                    "report_id": rid,
                })
            return {
                "status": "ok",
                "total": len(saved),
                "reports": saved,
            }
    finally:
        db.close()
