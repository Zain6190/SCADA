# presentation/http/routers/auth.py
# Authentication endpoints: login, me, token refresh.
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from infrastructure.auth.jwt import create_token, get_current_user
from infrastructure.auth.models import authenticate_user

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: str
    roles: list[str]
    permissions: list[str]
    region_ids: list[int]
    is_active: bool


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Authenticate user and return JWT token."""
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        roles=user["roles"],
        extra={"email": user["email"], "permissions": user["permissions"]},
    )
    return LoginResponse(
        access_token=token,
        user=user,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return UserResponse(
        id=user["sub"],
        username=user.get("username", ""),
        email=user.get("email", ""),
        full_name=user.get("full_name", ""),
        role=user.get("role", "VIEWER"),
        roles=user.get("roles", []),
        permissions=user.get("permissions", []),
        region_ids=user.get("region_ids", []),
        is_active=user.get("is_active", True),
    )
