# infrastructure/auth/dependencies.py
# FastAPI dependencies for role-based and permission-based access control.
from functools import wraps
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, status

from infrastructure.auth.jwt import get_current_user


def require_role(*allowed_roles: str):
    """Dependency factory: require the current user to have one of the specified roles.
    
    Usage:
        @router.get("/admin", dependencies=[Depends(require_role("SYSTEM_ADMIN"))])
    """
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role", "")
        user_roles = user.get("roles", [])
        if not any(r in allowed_roles for r in [user_role] + user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(allowed_roles)}",
            )
        return user
    return _check


def require_permission(*required_perms: str):
    """Dependency factory: require the current user to have specific permissions.
    
    Usage:
        @router.post("/alerts/{id}/ack", dependencies=[Depends(require_permission("water:ack")))
    """
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        user_perms = set(user.get("permissions", []))
        if "*" in user_perms:
            return user
        if not any(p in user_perms for p in required_perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires permission: {', '.join(required_perms)}",
            )
        return user
    return _check
