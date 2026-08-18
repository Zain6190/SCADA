# ml/validation/model_registry.py
# Model version registry and status lifecycle management.
# Tracks EXPERIMENTAL → SHADOW → APPROVED → PRODUCTION transitions.
#
# Phase 3: ML Validation

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("aquavision.ml.validation")


class ModelStatus(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    SHADOW = "SHADOW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PRODUCTION = "PRODUCTION"


@dataclass
class ModelVersion:
    """Represents a trained model version."""
    id: Optional[int] = None
    model_type: str = ""  # xgb_flood, iforest_anomaly, persistence
    asset_id: Optional[int] = None  # None = global model
    version: str = ""
    status: str = ModelStatus.EXPERIMENTAL
    metrics: Dict = field(default_factory=dict)
    validation_report_id: Optional[int] = None
    trained_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class ModelRegistry:
    """Manages model versions and status transitions.
    
    Status lifecycle:
        EXPERIMENTAL → SHADOW → APPROVED → PRODUCTION
                  ↓
               REJECTED
    
    Transitions:
        EXPERIMENTAL → SHADOW: After passing walk-forward validation
        SHADOW → APPROVED: After shadow period + human review
        APPROVED → PRODUCTION: After explicit approval
        Any → REJECTED: If validation fails
    """

    VALID_TRANSITIONS = {
        ModelStatus.EXPERIMENTAL: [ModelStatus.SHADOW, ModelStatus.REJECTED],
        ModelStatus.SHADOW: [ModelStatus.APPROVED, ModelStatus.REJECTED],
        ModelStatus.APPROVED: [ModelStatus.PRODUCTION, ModelStatus.REJECTED],
        ModelStatus.PRODUCTION: [ModelStatus.REJECTED],
        ModelStatus.REJECTED: [],
    }

    def __init__(self, session):
        self.session = session

    def register(
        self,
        model_type: str,
        version: str,
        asset_id: Optional[int] = None,
        metrics: Optional[Dict] = None,
        notes: Optional[str] = None,
    ) -> int:
        """Register a new model version."""
        from infrastructure.db.models import ModelVersionDB
        now = datetime.now(timezone.utc)
        mv = ModelVersionDB(
            model_type=model_type,
            asset_id=asset_id,
            version=version,
            status=ModelStatus.EXPERIMENTAL,
            metrics=metrics or {},
            trained_at=now,
            created_at=now,
            notes=notes,
        )
        self.session.add(mv)
        self.session.commit()
        self.session.refresh(mv)
        logger.info(f"Registered model: {model_type} v{version} (asset={asset_id})")
        return mv.id

    def transition(
        self,
        model_version_id: int,
        new_status: ModelStatus,
        approved_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Transition a model version to a new status."""
        from infrastructure.db.models import ModelVersionDB
        mv = self.session.get(ModelVersionDB, model_version_id)
        if not mv:
            return False

        current = ModelStatus(mv.status)
        if new_status not in self.VALID_TRANSITIONS.get(current, []):
            logger.warning(
                f"Invalid transition: {current.value} → {new_status.value}"
            )
            return False

        now = datetime.now(timezone.utc)
        mv.status = new_status.value
        if new_status == ModelStatus.APPROVED:
            mv.approved_at = now
            mv.approved_by = approved_by
        if notes:
            mv.notes = notes
        self.session.commit()
        logger.info(
            f"Model transition: {mv.version} {current.value} → {new_status.value}"
        )
        return True

    def get_active_model(
        self, model_type: str, asset_id: Optional[int] = None
    ) -> Optional[ModelVersion]:
        """Get the active production model for a type/asset."""
        from infrastructure.db.models import ModelVersionDB
        q = self.session.query(ModelVersionDB).filter(
            ModelVersionDB.model_type == model_type,
            ModelVersionDB.status == ModelStatus.PRODUCTION.value,
        )
        if asset_id is not None:
            q = q.filter(
                (ModelVersionDB.asset_id == asset_id) |
                (ModelVersionDB.asset_id == None)
            )
        mv = q.order_by(ModelVersionDB.created_at.desc()).first()
        if mv:
            return ModelVersion(
                id=mv.id,
                model_type=mv.model_type,
                asset_id=mv.asset_id,
                version=mv.version,
                status=mv.status,
                metrics=mv.metrics or {},
                trained_at=mv.trained_at,
                approved_at=mv.approved_at,
                approved_by=mv.approved_by,
                notes=mv.notes,
            )
        return None

    def list_versions(
        self, model_type: Optional[str] = None, status: Optional[str] = None
    ) -> List[ModelVersion]:
        """List model versions with optional filters."""
        from infrastructure.db.models import ModelVersionDB
        q = self.session.query(ModelVersionDB)
        if model_type:
            q = q.filter(ModelVersionDB.model_type == model_type)
        if status:
            q = q.filter(ModelVersionDB.status == status)
        results = []
        for mv in q.order_by(ModelVersionDB.created_at.desc()).all():
            results.append(ModelVersion(
                id=mv.id,
                model_type=mv.model_type,
                asset_id=mv.asset_id,
                version=mv.version,
                status=mv.status,
                metrics=mv.metrics or {},
                trained_at=mv.trained_at,
                approved_at=mv.approved_at,
                approved_by=mv.approved_by,
                notes=mv.notes,
            ))
        return results
