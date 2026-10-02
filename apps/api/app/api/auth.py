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
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import get_current_user, has_permission
from app.persistence.database import get_db
from app.repositories.api_key_repo import ApiKeyRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.auth_service import AuthService
from app.services.debug_session_service import debug_session_service
from app.services.recorder_service import recorder_service

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()
api_key_repo = ApiKeyRepository()


class StreamTicketRequest(BaseModel):
    kind: Literal["run", "task", "recorder", "debug", "lsp"]
    resource_id: str = Field(min_length=1, max_length=128)


@router.post("/stream-ticket")
async def create_stream_ticket(
    payload: StreamTicketRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
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

    exists = False
    if payload.kind == "run":
        exists = await TestRunRepository(session).get_by_id(payload.resource_id) is not None
    elif payload.kind == "task":
        exists = await TaskRepository(session).get(payload.resource_id, str(user.id)) is not None
    elif payload.kind == "recorder":
        exists = await recorder_service.get(payload.resource_id, str(user.id)) is not None
    elif payload.kind == "debug":
        exists = await debug_session_service.get(payload.resource_id, str(user.id)) is not None
    elif payload.kind == "lsp":
        from app.repositories.project_repo import ProjectRepository

        exists = await ProjectRepository(session).get_by_id(payload.resource_id) is not None
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
