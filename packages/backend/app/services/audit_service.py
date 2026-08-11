# packages/backend/app/services/audit_service.py
# Structured audit logging to system.audit_logs.
#
# IMPORTANT: never log passwords, tokens, or other secrets. Only structured
# action metadata. Callers should pass before/after values with sensitive
# fields already stripped.
from typing import Any, Dict, Optional

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import db as orm


def _get_role(user_id: Optional[int]) -> Optional[str]:
    """Best-effort primary role name for the audit row."""
    if not user_id:
        return None
    with SessionLocal() as db:
        role = db.execute(
            select(orm.Role.name)
            .join(orm.UserRole, orm.UserRole.role_id == orm.Role.id)
            .where(orm.UserRole.user_id == user_id)
            .limit(1)
        ).scalar_one_or_none()
        return role


def write_audit(
    *,
    action: str,
    module: Optional[str] = None,
    user_id: Optional[int] = None,
    role: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    region_id: Optional[int] = None,
    before_value: Optional[Dict[str, Any]] = None,
    after_value: Optional[Dict[str, Any]] = None,
    result: Optional[str] = None,
    request_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> int:
    """Persist an audit record. Returns the new row id.

    Used for both operational writes (result='success') and security events
    (result='denied', action='AUTH_FAILED'/'ACCESS_DENIED', etc.).
    """
    if role is None:
        role = _get_role(user_id)
    with SessionLocal() as db:
        entry = orm.AuditLog(
            user_id=user_id,
            role=role,
            module=module,
            resource_type=resource_type,
            resource_id=resource_id,
            region_id=region_id,
            before_value=before_value,
            after_value=after_value,
            details=details,
            result=result,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            action=action,
            entity_type=resource_type,
            entity_id=resource_id,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry.id


def log_security_event(
    *,
    action: str,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> int:
    """Record an unauthorized-access / security attempt (result='denied')."""
    return write_audit(
        action=action,
        module="security",
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        result="denied",
        details=details,
    )
