# presentation/http/routers/registry.py
# Model registry API: list model versions and drive lifecycle transitions.
# Phase 3: ML Validation

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from infrastructure.auth.rbac import get_db_user, require_permissions
from infrastructure.db.models import User
from ml.validation.model_registry import ModelRegistry, ModelStatus

logger = logging.getLogger("aquavision.api.registry")

router = APIRouter(prefix="/registry", tags=["Model Registry"])

APPROVE_GUARD = require_permissions("AQUAVISION_APPROVE_REPORT")

TRANSITION_ACTIONS = {
    "approve": ModelStatus.APPROVED,
    "promote": ModelStatus.PRODUCTION,
    "reject": ModelStatus.REJECTED,
}


class ModelVersionResponse(BaseModel):
    id: int
    model_type: str
    asset_id: Optional[int] = None
    version: str
    status: str
    metrics: dict
    validation_report_id: Optional[int] = None
    validation_recommendation: Optional[str] = None
    trained_at: Optional[str] = None
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    notes: Optional[str] = None
    allowed_transitions: List[str] = []


class TransitionBody(BaseModel):
    notes: Optional[str] = None


def _to_response(mv, recommendation: Optional[str] = None) -> ModelVersionResponse:
    try:
        current = ModelStatus(mv.status)
        allowed = ModelRegistry.VALID_TRANSITIONS.get(current, [])
    except ValueError:
        allowed = []
    return ModelVersionResponse(
        id=mv.id,
        model_type=mv.model_type,
        asset_id=mv.asset_id,
        version=mv.version,
        status=mv.status,
        metrics=mv.metrics or {},
        validation_report_id=mv.validation_report_id,
        validation_recommendation=recommendation,
        trained_at=mv.trained_at.isoformat() if mv.trained_at else None,
        approved_at=mv.approved_at.isoformat() if mv.approved_at else None,
        approved_by=mv.approved_by,
        notes=mv.notes,
        allowed_transitions=[s.value for s in allowed],
    )


@router.get("/models", response_model=List[ModelVersionResponse])
def list_model_versions(
    model_type: Optional[str] = None,
    status: Optional[str] = None,
    asset_id: Optional[int] = None,
    limit: int = Query(100, le=500),
):
    """List registered model versions with linked validation recommendations."""
    from infrastructure.db.engine import SessionLocal
    from infrastructure.db.models import ModelVersionDB, ValidationReportDB

    db = SessionLocal()
    try:
        q = db.query(ModelVersionDB)
        if model_type:
            q = q.filter(ModelVersionDB.model_type == model_type)
        if status:
            q = q.filter(ModelVersionDB.status == status)
        if asset_id is not None:
            q = q.filter(ModelVersionDB.asset_id == asset_id)
        rows = q.order_by(ModelVersionDB.created_at.desc()).limit(limit).all()

        report_ids = [r.validation_report_id for r in rows if r.validation_report_id]
        recommendations = {}
        if report_ids:
            recommendations = dict(
                db.query(ValidationReportDB.id, ValidationReportDB.recommendation)
                .filter(ValidationReportDB.id.in_(report_ids))
                .all()
            )
        return [
            _to_response(mv, recommendations.get(mv.validation_report_id))
            for mv in rows
        ]
    finally:
        db.close()


def _transition(model_version_id: int, target: ModelStatus, operator: User, notes: Optional[str]) -> ModelVersionResponse:
    from infrastructure.db.engine import SessionLocal
    from infrastructure.db.models import ModelVersionDB

    db = SessionLocal()
    try:
        mv = db.get(ModelVersionDB, model_version_id)
        if mv is None:
            raise HTTPException(status_code=404, detail="Model version not found")
        try:
            current = ModelStatus(mv.status)
        except ValueError:
            raise HTTPException(status_code=409, detail=f"Unknown status: {mv.status}")
        if target not in ModelRegistry.VALID_TRANSITIONS.get(current, []):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot transition {current.value} → {target.value}",
            )
        approved_by = operator.name or operator.email
        registry = ModelRegistry(db)
        if not registry.transition(model_version_id, target, approved_by=approved_by, notes=notes):
            raise HTTPException(status_code=409, detail="Transition rejected")
        mv = db.get(ModelVersionDB, model_version_id)
        logger.info(f"Registry {target.value}: {mv.version} (asset={mv.asset_id}) by {approved_by}")
        return _to_response(mv)
    finally:
        db.close()


def _transition_action(action: str, model_version_id: int, operator: User, body: Optional[TransitionBody]) -> ModelVersionResponse:
    return _transition(
        model_version_id,
        TRANSITION_ACTIONS[action],
        operator,
        body.notes if body else None,
    )


@router.post("/models/{model_version_id}/approve", response_model=ModelVersionResponse, dependencies=[Depends(APPROVE_GUARD)])
def approve_model_version(
    model_version_id: int,
    operator: User = Depends(get_db_user),
    body: Optional[TransitionBody] = None,
):
    """SHADOW → APPROVED: human sign-off after review."""
    return _transition_action("approve", model_version_id, operator, body)


@router.post("/models/{model_version_id}/promote", response_model=ModelVersionResponse, dependencies=[Depends(APPROVE_GUARD)])
def promote_model_version(
    model_version_id: int,
    operator: User = Depends(get_db_user),
    body: Optional[TransitionBody] = None,
):
    """APPROVED → PRODUCTION: release to production serving."""
    return _transition_action("promote", model_version_id, operator, body)


@router.post("/models/{model_version_id}/reject", response_model=ModelVersionResponse, dependencies=[Depends(APPROVE_GUARD)])
def reject_model_version(
    model_version_id: int,
    operator: User = Depends(get_db_user),
    body: Optional[TransitionBody] = None,
):
    """Any status → REJECTED: fails validation or review."""
    return _transition_action("reject", model_version_id, operator, body)
