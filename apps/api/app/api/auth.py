from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from project_model.models import (
    ApiKey,
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    LoginRequest,
    LoginResponse,
    User,
)

from app.api.authz import get_current_user
from app.repositories.api_key_repo import ApiKeyRepository
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()
api_key_repo = ApiKeyRepository()


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    await auth_service.ensure_default_users()
    res = await auth_service.login(email=request.email, password=request.password)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return res


@router.get("/me", response_model=LoginResponse)
async def get_current_user_profile(request: Request) -> LoginResponse:
    user = await get_current_user(request)
    _, perms = await auth_service.authenticate_token_or_key(request.headers.get("authorization"))
    return LoginResponse(
        access_token="",
        token_type="bearer",
        user=user,
        permissions=perms,
    )


@router.post("/api-keys", response_model=ApiKeyCreatedResponse)
async def create_api_key(
    request: ApiKeyCreate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiKeyCreatedResponse:
    request.user_id = current_user.id
    return await api_key_repo.create(request)


@router.get("/api-keys", response_model=list[ApiKey])
async def list_api_keys(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ApiKey]:
    return await api_key_repo.list_by_user(current_user.id)


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    success = await api_key_repo.delete(key_id)
    return {"success": success}
