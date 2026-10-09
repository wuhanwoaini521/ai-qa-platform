from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from project_model.models import (
    ApiKey,
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    LoginRequest,
    LoginResponse,
    Permission,
    User,
)
from pydantic import BaseModel, Field

from app.api.authz import get_current_user, has_permission
from app.container import get_api_key_service, get_stream_resource_service
from app.services.api_read_service import ApiKeyService, StreamResourceService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()


class StreamTicketRequest(BaseModel):
    kind: Literal["run", "task", "recorder", "debug", "lsp"]
    resource_id: str = Field(min_length=1, max_length=128)


@router.post("/stream-ticket")
async def create_stream_ticket(
    payload: StreamTicketRequest,
    user: User = Depends(get_current_user),
    resources: StreamResourceService = Depends(get_stream_resource_service),
) -> dict[str, str | int]:
    permission = {
        "run": Permission.PROJECT_READ,
        "task": Permission.PROJECT_READ,
        "recorder": Permission.AUTOMATION_EDIT,
        "debug": Permission.RUN_EXECUTE,
        "lsp": Permission.PROJECT_READ,
    }[payload.kind]
    if not has_permission(user, permission):
        raise HTTPException(status_code=403, detail="Insufficient permission for this stream")

    exists = await resources.exists(payload.kind, payload.resource_id, str(user.id))
    if not exists:
        raise HTTPException(status_code=404, detail="Stream resource not found")

    scope = f"{payload.kind}:{payload.resource_id}"
    return {
        "stream_ticket": auth_service.issue_stream_ticket(str(user.id), scope),
        "expires_in": 300,
    }


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
    service: Annotated[ApiKeyService, Depends(get_api_key_service)],
) -> ApiKeyCreatedResponse:
    return await service.create(request.model_copy(update={"user_id": current_user.id}))


@router.get("/api-keys", response_model=list[ApiKey])
async def list_api_keys(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ApiKeyService, Depends(get_api_key_service)],
) -> list[ApiKey]:
    return await service.list_by_user(current_user.id)


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ApiKeyService, Depends(get_api_key_service)],
) -> dict[str, bool]:
    success = await service.delete(key_id)
    return {"success": success}
