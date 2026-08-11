# packages/backend/app/api/v1/endpoints/auth.py
from datetime import UTC, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.core.security import (
    verify_password, get_password_hash, create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.rbac import (
    oauth2_scheme, decode_user_id, get_permissions, get_region_scope,
    get_user_roles, require_admin, require_permissions,
)
from app.services.audit_service import log_security_event, write_audit
from app.models import db as orm

router = APIRouter()


# ---------------------------------------------------------------------------
# Access lifecycle (Phase 2)
# ---------------------------------------------------------------------------
# PENDING/REJECTED -> the user has not been granted portal access yet.
# ACTIVE/APPROVED  -> access granted; may sign in.
# SUSPENDED/REVOKED / is_active=False -> account locked; may not sign in.
NON_ACCESS_STATUSES = {"PENDING", "REJECTED"}
DISABLED_STATUSES = {"SUSPENDED", "REVOKED"}

# The detail string the frontend uses to pick its status screen.
DETAIL_ACCESS_PENDING = "access-pending"
DETAIL_ACCOUNT_DISABLED = "account-disabled"


def _check_access_allowed(user: orm.User) -> None:
    """Raise 403 for accounts that must not authenticate, with a machine-
    readable detail string that the frontend maps to a status screen."""
    access = (user.access_status or "ACTIVE").upper()
    if not user.is_active or access in DISABLED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=DETAIL_ACCOUNT_DISABLED
        )
    if access in NON_ACCESS_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=DETAIL_ACCESS_PENDING
        )


def _user_payload(user: orm.User, db) -> dict:
    """Serialise a user with role names + permissions + geographic scope."""
    roles = db.execute(
        select(orm.Role.name)
        .join(orm.UserRole, orm.UserRole.role_id == orm.Role.id)
        .where(orm.UserRole.user_id == user.id)
    ).scalars().all()
    scope = get_region_scope(user.id, db)
    return {
        "id": user.id,
        "username": user.email.split("@")[0],
        "email": user.email,
        "full_name": user.name,
        "role": roles[0] if roles else "viewer",
        "roles": roles,
        "team": None,
        "is_active": user.is_active,
        "access_status": (user.access_status or "ACTIVE").upper(),
        "access_requested_at": (
            user.access_requested_at.isoformat() if user.access_requested_at else None
        ),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "permissions": get_permissions(user.id, db),
        "region_scope": scope,
        "region_ids": scope["region_ids"],
    }


# Roles that a user may never be assigned. SYSTEM_ADMIN / root escalation is
# reserved for pre-provisioned bootstrap accounts managed outside this endpoint.
_FORBIDDEN_ROLES = {"system_admin", "superuser", "root"}


@router.post("/register")
async def register(
    user_data: dict,
    admin: orm.User = Depends(require_admin),
    db=Depends(get_db),
):
    """Create a user. Admin-only. Public/self registration is disabled unless
    ALLOW_PUBLIC_REGISTRATION=True (explicit development flag), and even then a
    caller may NOT assign themselves roles or privileged roles."""
    username = user_data.get("username")
    email = user_data.get("email")
    password = user_data.get("password")
    full_name = user_data.get("full_name", username)
    role_name = user_data.get("role") or "viewer"
    access_status = (user_data.get("access_status") or "ACTIVE").upper()
    allowed_statuses = {"ACTIVE", "APPROVED", "PENDING", "SUSPENDED", "REVOKED", "REJECTED"}
    if access_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid access_status: {access_status}")

    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="Username, email and password required")

    if not settings.ALLOW_PUBLIC_REGISTRATION and "admin" not in get_user_roles(admin.id, db):
        raise HTTPException(status_code=403, detail="Registration is disabled for non-administrators")

    if role_name.lower() in _FORBIDDEN_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role_name}' cannot be assigned here")

    existing = db.execute(select(orm.User).where(orm.User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = orm.User(
        name=full_name,
        email=email,
        password_hash=get_password_hash(password),
        is_active=True,
        access_status=access_status,
    )
    db.add(user)
    db.flush()

    role = db.execute(select(orm.Role).where(orm.Role.name == role_name)).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=400, detail=f"Role does not exist: {role_name}")
    db.add(orm.UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    write_audit(
        action="USER_CREATED",
        module="auth",
        user_id=admin.id,
        role="admin",
        resource_type="user",
        resource_id=str(user.id),
        after_value={"email": email, "role": role_name, "access_status": access_status},
        result="success",
    )
    return {"message": "User created successfully", "user": _user_payload(user, db)}


@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    """Login against PostgreSQL, returns a JWT carrying the user id (sub)."""
    user = db.execute(
        select(orm.User).where(orm.User.email == form_data.username)
    ).scalar_one_or_none()
    if user is None or not verify_password(form_data.password, user.password_hash):
        log_security_event(
            action="AUTH_FAILED_LOGIN",
            user_id=user.id if user else None,
            details={"email": form_data.username},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _check_access_allowed(user)

    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": _user_payload(user, db),
    }


@router.get("/me")
async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    """Current user info + permissions from roles."""
    user_id = decode_user_id(token)
    user = db.get(orm.User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    _check_access_allowed(user)
    return _user_payload(user, db)


@router.post("/logout")
async def logout():
    """Logout (client-side token removal)."""
    return {"message": "Logged out successfully"}


# ---------------------------------------------------------------------------
# Admin user provisioning (Phase 2: portal access architecture)
# ---------------------------------------------------------------------------
def _role_id(db, role_name: str, label: str = "Role") -> int:
    role = db.execute(select(orm.Role).where(orm.Role.name == role_name)).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=400, detail=f"{label} does not exist: {role_name}")
    return role.id


def _replace_user_scope(db, admin: orm.User, target: orm.User, scope: dict) -> None:
    """Replace a user's geographic scope rows with the submitted value.

    scope: {scope_type, region_id|region_name|asset_id, expires_at}
    A NATIONAL scope clears region/asset targets. Passing scope=None removes
    all scope rows (fail-closed: the user then has NO geo access).
    """
    old = list(db.execute(
        select(orm.UserRegionScope).where(orm.UserRegionScope.user_id == target.id)
    ).scalars().all())
    for s in old:
        db.delete(s)
    db.flush()

    if not scope or scope.get("scope_type") is None:
        return
    scope_type = scope.get("scope_type", "NATIONAL").upper()
    if scope_type not in ("NATIONAL", "PROVINCE", "DISTRICT", "ASSET"):
        raise HTTPException(status_code=400, detail=f"Invalid scope_type: {scope_type}")

    region_id = scope.get("region_id")
    asset_id = scope.get("asset_id")
    if scope_type == "NATIONAL":
        region_id = asset_id = None
    elif scope_type == "ASSET":
        if not asset_id:
            raise HTTPException(status_code=400, detail="ASSET scope requires an asset_id")
        region_id = None
    else:
        if not region_id:
            raise HTTPException(status_code=400, detail=f"{scope_type} scope requires a region_id")
        asset_id = None

    new = orm.UserRegionScope(
        user_id=target.id,
        scope_type=scope_type,
        region_id=region_id,
        asset_id=asset_id,
        granted_by=admin.id,
        is_active=True,
        expires_at=scope.get("expires_at"),
    )
    db.add(new)
    db.flush()


def _parse_expiry(value) -> Optional[datetime]:
    """Accept an ISO-8601 expiry string or None. Validates the format."""
    if value in (None, "", "null"):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid expiry: {value!r}")


@router.post("/admin/users", response_model=dict, status_code=201)
async def create_user(
    payload: dict,
    admin: orm.User = Depends(require_admin),
    db=Depends(get_db),
):
    """Atomic (single-transaction) user provisioning for the admin workflow.

    Creates user + role + geographic scope + asset grants + account status in
    one commit so a failed scope/asset assignment can never leave a half
    configured account behind. Admin only.

    Payload:
      full_name, email, password (temporary, invite link follows later)
      role:            role name in shared.roles
      access_status:   ACTIVE | PENDING | ... (login gates non-ACTIVE)
      scope:           {scope_type, region_id|region_name|asset_id,
                        expires_at}  (optional; absent FAILS CLOSED -> no access)
      asset_ids:       [ids] extra ASSET-scope grants layered over the scope
    """
    full_name = (payload.get("full_name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password")
    role_name = payload.get("role") or "viewer"
    access_status = (payload.get("access_status") or "ACTIVE").upper()

    if not full_name or not email or not password:
        raise HTTPException(status_code=400, detail="full_name, email and password are required")
    if role_name.lower() in _FORBIDDEN_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{role_name}' cannot be assigned")
    if access_status not in {"ACTIVE", "APPROVED", "PENDING", "SUSPENDED", "REVOKED", "REJECTED"}:
        raise HTTPException(status_code=400, detail=f"Invalid access_status: {access_status}")

    existing = db.execute(select(orm.User).where(orm.User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    role_id = _role_id(db, role_name)

    user = orm.User(
        name=full_name,
        email=email,
        password_hash=get_password_hash(password),
        is_active=True,
        access_status=access_status,
        access_requested_at=datetime.now(UTC) if access_status in ("PENDING", "APPROVED") else None,
    )
    db.add(user)
    db.flush()
    db.add(orm.UserRole(user_id=user.id, role_id=role_id))

    scope = payload.get("scope")
    if scope and scope.get("scope_type"):
        _replace_user_scope(db, admin, user, {**scope, "expires_at": _parse_expiry(scope.get("expires_at"))})
    for asset_id in payload.get("asset_ids") or []:
        if db.get(orm.Asset, asset_id) is None:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Asset does not exist: {asset_id}")
        db.add(orm.UserRegionScope(
            user_id=user.id,
            scope_type="ASSET",
            asset_id=asset_id,
            granted_by=admin.id,
            is_active=True,
            expires_at=_parse_expiry(scope.get("expires_at")) if scope else None,
        ))

    db.commit()
    db.refresh(user)
    created = _user_payload(user, db)
    write_audit(
        action="USER_CREATED",
        module="auth",
        user_id=admin.id,
        role="admin",
        resource_type="user",
        resource_id=str(user.id),
        after_value={"email": email, "role": role_name, "access_status": access_status},
        result="success",
    )
    return {"message": "User created", "user": created}


@router.get("/roles", response_model=List[dict])
async def list_roles(admin: orm.User = Depends(require_admin), db=Depends(get_db)):
    """Roles with their permission names. Powers the admin's role dropdown and
    the live permission preview in the user-lifecycle form. Admin only."""
    rows = db.execute(
        select(orm.Role).order_by(orm.Role.name)
    ).scalars().all()
    return [
        {
            "name": r.name,
            "description": r.description,
            "permissions": list(db.execute(
                select(orm.Permission.name)
                .join(orm.RolePermission, orm.RolePermission.permission_id == orm.Permission.id)
                .where(orm.RolePermission.role_id == r.id)
                .order_by(orm.Permission.name)
            ).scalars().all()),
        }
        for r in rows
    ]


@router.get("/users", response_model=List[dict])
async def list_users(admin: orm.User = Depends(require_admin), db=Depends(get_db)):
    """List every user with roles, access status and geo scope. Admin only."""
    users = db.execute(
        select(orm.User).order_by(orm.User.created_at.desc())
    ).scalars().all()
    return [_user_payload(u, db) for u in users]


@router.patch("/users/{user_id}", response_model=dict)
async def update_user(
    user_id: int,
    patch: dict,
    admin: orm.User = Depends(require_admin),
    db=Depends(get_db),
):
    """Update a user's role, access lifecycle, active flag or region scope.
    Admin only. Never allows assigning system_admin/superuser/root."""
    target = db.get(orm.User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    before = _user_before(target, db)

    role_name = patch.get("role")
    if role_name is not None:
        if role_name.lower() in _FORBIDDEN_ROLES:
            raise HTTPException(status_code=400, detail=f"Role '{role_name}' cannot be assigned")
        for ur in db.execute(select(orm.UserRole).where(orm.UserRole.user_id == target.id)).scalars():
            db.delete(ur)
        db.flush()
        db.add(orm.UserRole(user_id=target.id, role_id=_role_id(db, role_name)))

    if "is_active" in patch:
        target.is_active = bool(patch["is_active"])

    if "access_status" in patch:
        status = patch["access_status"].upper()
        if status not in {"ACTIVE", "APPROVED", "PENDING", "SUSPENDED", "REVOKED", "REJECTED"}:
            raise HTTPException(status_code=400, detail=f"Invalid access_status: {status}")
        target.access_status = status

    if "scope" in patch:
        _replace_user_scope(
            db, admin, target,
            {**patch["scope"], "expires_at": _parse_expiry((patch["scope"] or {}).get("expires_at"))},
        )

    db.commit()
    db.refresh(target)

    after = _user_after(target, db)
    write_audit(
        action="USER_UPDATED",
        module="auth",
        user_id=admin.id,
        role="admin",
        resource_type="user",
        resource_id=str(user_id),
        before_value=before,
        after_value=after,
        result="success",
    )
    return {"message": "User updated", "user": after}  


def _user_before(user: orm.User, db) -> dict:
    roles = db.execute(
        select(orm.Role.name)
        .join(orm.UserRole, orm.UserRole.role_id == orm.Role.id)
        .where(orm.UserRole.user_id == user.id)
    ).scalars().all()
    return {
        "role": roles[0] if roles else "viewer",
        "is_active": user.is_active,
        "access_status": (user.access_status or "ACTIVE").upper(),
        "region_scope": get_region_scope(user.id, db),
    }


def _user_after(user: orm.User, db) -> dict:
    return _user_before(user, db)


# ---------------------------------------------------------------------------
# Supervisor delegation (MANAGE_OPERATORS) - District Supervisor -> Operator
# ---------------------------------------------------------------------------
# A supervisor may create / approve accounts ONLY inside the geographic scope
# they already hold (server clamps the new user's region to actor.region_ids),
# and may assign ONLY these delegated roles - never admin / supervisor.
_DELEGATED_ROLES = {
    "field_officer", "viewer",
    "aquavision_analyst", "crop_analyst", "geo_analyst",
}

# Dependency: requires the MANAGE_OPERATORS permission AND a valid geo scope
# (fail-closed: a supervisor with an expired scope cannot create accounts).
MANAGE_OPERATORS = require_permissions("MANAGE_OPERATORS")


def _actor_role(actor: dict, db) -> str:
    roles = get_user_roles(actor["user_id"], db)
    return roles[0] if roles else "supervisor"


def _supervisor_can_manage(actor: dict, user_id: int, db) -> bool:
    """Can this actor create/approve/update the given user?

    A restricted supervisor manages users whose active scope overlaps their
    own region_ids. A NATIONAL (unrestricted) actor manages everyone with an
    active scope.
    """
    scope = actor["region_scope"]
    target = get_region_scope(user_id, db)
    if not target["access"]:
        return False
    if scope["restricted"]:
        target_ids = set(target["region_ids"] or [])
        actor_ids = set(scope["region_ids"] or [])
        return bool(target_ids & actor_ids)
    return True


def _assert_operator_in_team(actor: dict, user_id: int, db) -> None:
    if not _supervisor_can_manage(actor, user_id, db):
        log_security_event(
            action="ACCESS_DENIED_OUT_OF_SCOPE",
            user_id=actor["user_id"],
            details={"resource_type": "operator_account", "user_id": user_id},
        )
        raise HTTPException(status_code=403, detail="User is outside your managed region")


##


@router.get("/operator-roles", response_model=List[dict])
async def list_operator_roles(actor: dict = Depends(MANAGE_OPERATORS), db=Depends(get_db)):
    """Delegable roles (with their permissions) for the supervisor form.
    Never exposes admin / supervisor / system roles."""
    names = sorted(_DELEGATED_ROLES)
    rows = db.execute(
        select(orm.Role).where(orm.Role.name.in_(names)).order_by(orm.Role.name)
    ).scalars().all()
    return [
        {
            "name": r.name,
            "description": r.description,
            "permissions": list(db.execute(
                select(orm.Permission.name)
                .join(orm.RolePermission, orm.RolePermission.permission_id == orm.Permission.id)
                .where(orm.RolePermission.role_id == r.id)
                .order_by(orm.Permission.name)
            ).scalars().all()),
        }
        for r in rows
    ]


@router.post("/operators", response_model=dict, status_code=201)
async def create_operator(
    payload: dict,
    actor: dict = Depends(MANAGE_OPERATORS),
    db=Depends(get_db),
):
    """Create a field operator inside the supervisor's OWN geographic scope.

    The region can never be picked out of scope (the endpoint clamps the new
    user's region to actor.region_ids). Only delegated roles may be assigned.

    Payload: full_name, email, password, role, access_status, region_id,
             expires_at (optional)
    """
    full_name = (payload.get("full_name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password")
    role_name = (payload.get("role") or "field_officer").lower()
    access_status = (payload.get("access_status") or "ACTIVE").upper()
    region_id = payload.get("region_id")

    if not full_name or not email or not password:
        raise HTTPException(status_code=400, detail="full_name, email and password are required")
    if role_name not in _DELEGATED_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role '{role_name}' cannot be delegated by a supervisor",
        )
    if access_status not in {"ACTIVE", "APPROVED", "PENDING", "SUSPENDED", "REVOKED"}:
        raise HTTPException(status_code=400, detail=f"Invalid access_status: {access_status}")

    scope = actor["region_scope"]
    region_label = db.execute(
        select(orm.Region.name).where(orm.Region.id == region_id)
    ).scalar_one_or_none()
    if region_label is None:
        raise HTTPException(status_code=400, detail=f"Region does not exist: {region_id}")
    if scope["restricted"] and region_id not in (scope["region_ids"] or []):
        log_security_event(
            action="ACCESS_DENIED_OUT_OF_SCOPE",
            user_id=actor["user_id"],
            details={"resource_type": "operator_region", "region_id": region_id},
        )
        raise HTTPException(status_code=403, detail="Region is outside your access scope")

    existing = db.execute(select(orm.User).where(orm.User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    role_id = _role_id(db, role_name)
    user = orm.User(
        name=full_name,
        email=email,
        password_hash=get_password_hash(password),
        is_active=True,
        access_status=access_status,
        access_requested_at=datetime.now(UTC) if access_status in ("PENDING", "APPROVED") else None,
    )
    db.add(user)
    db.flush()
    db.add(orm.UserRole(user_id=user.id, role_id=role_id))
    db.add(orm.UserRegionScope(
        user_id=user.id,
        scope_type="DISTRICT",
        region_id=region_id,
        granted_by=actor["user_id"],
        is_active=True,
        expires_at=_parse_expiry(payload.get("expires_at")),
    ))

    db.commit()
    db.refresh(user)
    created = _user_payload(user, db)
    write_audit(
        action="USER_CREATED",
        module="auth",
        user_id=actor["user_id"],
        role=_actor_role(actor, db),
        resource_type="user",
        resource_id=str(user.id),
        after_value={"email": email, "role": role_name, "access_status": access_status,
                     "region_id": region_id},
        result="success",
    )
    return {"message": "User created", "user": created}


@router.get("/operators", response_model=List[dict])
async def list_operators(actor: dict = Depends(MANAGE_OPERATORS), db=Depends(get_db)):
    """The supervisor's team: delegated-role users whose scope overlaps the
    caller's own scope (or everyone, for a NATIONAL supervisor)."""
    users = db.execute(
        select(orm.User)
        .join(orm.UserRole, orm.UserRole.user_id == orm.User.id)
        .join(orm.Role, orm.Role.id == orm.UserRole.role_id)
        .where(orm.Role.name.in_(sorted(_DELEGATED_ROLES)))
        .order_by(orm.User.created_at.desc())
    ).scalars().all()

    team = [u for u in users if _supervisor_can_manage(actor, u.id, db)]
    return [_user_payload(u, db) for u in team]


@router.patch("/operators/{user_id}", response_model=dict)
async def update_operator(
    user_id: int,
    patch: dict,
    actor: dict = Depends(MANAGE_OPERATORS),
    db=Depends(get_db),
):
    """Supervisor edits / approves / suspends one of their own operators.
    Region boundaries are enforced like create (no out-of-scope management)."""
    target = db.get(orm.User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    _assert_operator_in_team(actor, user_id, db)

    before = _user_before(target, db)

    role_name = patch.get("role")
    if role_name is not None:
        role_name = role_name.lower()
        if role_name not in _DELEGATED_ROLES:
            raise HTTPException(status_code=400, detail=f"Role '{role_name}' cannot be delegated")
        for ur in db.execute(select(orm.UserRole).where(orm.UserRole.user_id == target.id)).scalars():
            db.delete(ur)
        db.flush()
        db.add(orm.UserRole(user_id=target.id, role_id=_role_id(db, role_name)))

    if "is_active" in patch:
        target.is_active = bool(patch["is_active"])

    if "access_status" in patch:
        status = patch["access_status"].upper()
        if status not in {"ACTIVE", "APPROVED", "PENDING", "SUSPENDED", "REVOKED"}:
            raise HTTPException(status_code=400, detail=f"Invalid access_status: {status}")
        target.access_status = status

    db.commit()
    db.refresh(target)

    after = _user_after(target, db)
    write_audit(
        action="USER_UPDATED",
        module="auth",
        user_id=actor["user_id"],
        role=_actor_role(actor, db),
        resource_type="user",
        resource_id=str(user_id),
        before_value=before,
        after_value=after,
        result="success",
    )
    return {"message": "User updated", "user": after}