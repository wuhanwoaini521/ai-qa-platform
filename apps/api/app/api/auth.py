from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from project_model.models import (
    ApiKey,
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    LoginRequest,
    LoginResponse,
    User,
)

from app.repositories.api_key_repo import ApiKeyRepository
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()
api_key_repo = ApiKeyRepository()


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    await auth_service.ensure_default_users()
    user, _ = await auth_service.authenticate_token_or_key(authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


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
async def get_current_user_profile(
    authorization: Annotated[str | None, Header()] = None,
) -> LoginResponse:
    user = await get_current_user(authorization)
    _, perms = await auth_service.authenticate_token_or_key(authorization)
    return LoginResponse(
        access_token="",
        token_type="bearer",
        user=user,
        permissions=perms,
    )


@router.post("/api-keys", response_model=ApiKeyCreatedResponse)
async def create_api_key(
    request: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
) -> ApiKeyCreatedResponse:
    request.user_id = current_user.id
    return await api_key_repo.create(request)


@router.get("/api-keys", response_model=list[ApiKey])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
) -> list[ApiKey]:
    return await api_key_repo.list_by_user(current_user.id)


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    success = await api_key_repo.delete(key_id)
    return {"success": success}
