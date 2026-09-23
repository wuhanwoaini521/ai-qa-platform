from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import User, UserCreate, UserUpdate

from app.api.auth import get_current_user
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])
user_service = UserService()


@router.get("", response_model=list[User])
async def list_users(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> list[User]:
    return await user_service.list_users(limit=limit)


@router.post("", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreate,
    current_user: User = Depends(get_current_user),
) -> User:
    return await user_service.create_user(request, actor=current_user)


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> User:
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/{user_id}", response_model=User)
async def update_user(
    user_id: str,
    request: UserUpdate,
    current_user: User = Depends(get_current_user),
) -> User:
    user = await user_service.update_user(user_id, request, actor=current_user)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    success = await user_service.delete_user(user_id, actor=current_user)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"success": True}
