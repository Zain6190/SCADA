# packages/backend/app/core/rbac.py
# Role-based access control: decodes the JWT, resolves the user's permissions
# and geographic scope from PostgreSQL (shared.users -> user_roles ->
# role_permissions -> permissions; shared.user_region_scopes -> regions),
# and enforces them per endpoint.
from datetime import UTC, datetime
from typing import List, Optional, Union

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import or_, select

from app.core.security import SECRET_KEY, ALGORITHM
from app.core.database import get_db
from app.models import db as orm
from app.services.audit_service import log_security_event

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def decode_user_id(token: str) -> int:
    """Return the numeric user id from a valid JWT, or 401."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return int(sub)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def get_permissions(user_id: int, db) -> List[str]:
    """All permission names granted to a user through their roles."""
    rows = db.execute(
        select(orm.Permission.name)
        .join(orm.RolePermission, orm.RolePermission.permission_id == orm.Permission.id)
        .join(orm.UserRole, orm.UserRole.role_id == orm.RolePermission.role_id)
        .where(orm.UserRole.user_id == user_id)
    ).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# Geographic scope (FAIL-CLOSED)
#
# A user is given explicit grants via shared.user_region_scopes:
#   NATIONAL  -> access to every region (region_id/asset_id must be NULL)
#   PROVINCE  -> one region_id = a province (grants the province + its districts)
#   DISTRICT  -> one region_id = a single district
#   ASSET     -> one asset_id (resolved to its owning region)
#
# Fail-closed rule: NO active scope => DENIED. Missing rows are never
# interpreted as national access. Expired or inactive scopes grant nothing.
# ---------------------------------------------------------------------------
def get_active_scopes(user_id: int, db) -> List[orm.UserRegionScope]:
    """All currently-granted scopes for a user (active, not expired)."""
    now = datetime.now(UTC)
    rows = db.execute(
        select(orm.UserRegionScope).where(
            orm.UserRegionScope.user_id == user_id,
            orm.UserRegionScope.is_active.is_(True),
            or_(
                orm.UserRegionScope.expires_at.is_(None),
                orm.UserRegionScope.expires_at > now,
            ),
        )
    ).scalars().all()
    return list(rows)


def _province_descendants(province_id: int, db) -> List[int]:
    """District (child) region ids belonging to a province."""
    return list(db.execute(
        select(orm.Region.id).where(orm.Region.parent_region_id == province_id)
    ).scalars().all())


def _region_descendants(region_id: int, db) -> List[int]:
    """Region id plus all descendant region ids (province -> its districts)."""
    out = {region_id}
    frontier = [region_id]
    while frontier:
        children = db.execute(
            select(orm.Region.id).where(orm.Region.parent_region_id.in_(frontier))
        ).scalars().all()
        nxt = [c for c in children if c not in out]
        out.update(nxt)
        frontier = nxt
    return list(out)


def _resolve_scope(scopes: List[orm.UserRegionScope], db) -> Optional[List[int]]:
    """Resolve a set of active scopes to the explicit list of allowed region
    ids. Returns None only when NATIONAL scope is held. Otherwise DENIED unless
    a concrete region/asset target exists."""
    region_ids: set[int] = set()
    for s in scopes:
        if s.scope_type in ("PROVINCE", "DISTRICT") and s.region_id:
            region_ids.add(s.region_id)
            if s.scope_type == "PROVINCE":
                region_ids.update(_region_descendants(s.region_id, db))
        elif s.scope_type == "ASSET" and s.asset_id:
            asset = db.get(orm.Asset, s.asset_id)
            if asset is not None and asset.region_id:
                region_ids.add(asset.region_id)
    return list(region_ids)


def get_region_scope(user_id: int, db) -> dict:
    """Return the user's geographic access as an explicit scope object.

    Result keys:
      access     (bool)   True if the user has ANY active scope
      has_scope  (bool)   True if the user has ANY active scope
      scope_type (str)    'NATIONAL' / 'PROVINCE' / 'DISTRICT' / 'ASSET' / None
      region_ids (list)   Explicit allowed region ids; None means NATIONAL.
      restricted (bool)   True when the user is restricted to a subset.
    """
    scopes = get_active_scopes(user_id, db)
    if not scopes:
        return {
            "access": False,
            "has_scope": False,
            "scope_type": None,
            "region_ids": None,
            "restricted": True,
        }
    has_national = any(s.scope_type == "NATIONAL" for s in scopes)
    scope_type = "NATIONAL" if has_national else "/".join(
        sorted({s.scope_type for s in scopes})
    )
    region_ids = None if has_national else _resolve_scope(scopes, db)
    return {
        "access": True,
        "has_scope": True,
        "scope_type": scope_type,
        "region_ids": region_ids,
        "restricted": not has_national,
    }


def require_permissions(*required: str):
    """Factory: returns a FastAPI dependency that enforces a permission set AND
    a valid (fail-closed) geographic scope.

    The dependency result carries the current user id, permissions, and an
    explicit scope object. If the user has NO active scope, access is denied
    (403), even if they hold the right permissions.

    Usage:  Depends(require_permissions("AQUAVISION_READ"))
    """
    async def checker(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
        user_id = decode_user_id(token)
        if user_id <= 0:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
        user = db.get(orm.User, user_id)
        if user is None or not user.is_active:
            log_security_event(action="AUTH_FAILED_INACTIVE_USER", user_id=user_id)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        perms = get_permissions(user_id, db)
        user_permissions = set(perms)
        needs = set(required)
        if not needs.issubset(user_permissions):
            log_security_event(
                action="ACCESS_DENIED_MISSING_PERMISSION",
                user_id=user_id,
                details={"required": sorted(needs), "required_permission": sorted(required)[:1]},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission(s): {', '.join(sorted(needs - user_permissions))}",
            )
        scope = get_region_scope(user_id, db)
        if not scope["access"]:
            log_security_event(action="ACCESS_DENIED_NO_GEO_SCOPE", user_id=user_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active geographic scope assigned; access denied",
            )
        return {
            "user_id": user_id,
            "permissions": perms,
            "region_scope": scope,
        }
    return checker


def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)) -> orm.User:
    """Resolve the JWT to a live, active user from shared.users."""
    user_id = decode_user_id(token)
    user = db.get(orm.User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def get_user_roles(user_id: int, db) -> List[str]:
    """Role names assigned to a user (user_roles -> roles)."""
    rows = db.execute(
        select(orm.Role.name)
        .join(orm.UserRole, orm.UserRole.role_id == orm.Role.id)
        .where(orm.UserRole.user_id == user_id)
    ).scalars().all()
    return list(rows)


def require_admin(user: orm.User = Depends(get_current_user), db=Depends(get_db)) -> orm.User:
    """Only users holding the admin role may pass."""
    if "admin" not in get_user_roles(user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return user