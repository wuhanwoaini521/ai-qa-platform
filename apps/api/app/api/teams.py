from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import Team, TeamCreate, TeamMember, TeamUpdate, User
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.services.team_service import TeamService

router = APIRouter(prefix="/teams", tags=["teams"])
team_service = TeamService()


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "MEMBER"


@router.get("", response_model=list[Team])
async def list_teams(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> list[Team]:
    return await team_service.list_teams(limit=limit)


@router.post("", response_model=Team, status_code=status.HTTP_201_CREATED)
async def create_team(
    request: TeamCreate,
    current_user: User = Depends(get_current_user),
) -> Team:
    return await team_service.create_team(request, actor=current_user)


@router.get("/{team_id}", response_model=Team)
async def get_team(
    team_id: str,
    current_user: User = Depends(get_current_user),
) -> Team:
    team = await team_service.get_team(team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.put("/{team_id}", response_model=Team)
async def update_team(
    team_id: str,
    request: TeamUpdate,
    current_user: User = Depends(get_current_user),
) -> Team:
    team = await team_service.update_team(team_id, request, actor=current_user)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.delete("/{team_id}")
async def delete_team(
    team_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    success = await team_service.delete_team(team_id, actor=current_user)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return {"success": True}


@router.post("/{team_id}/members", response_model=TeamMember, status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: str,
    request: AddMemberRequest,
    current_user: User = Depends(get_current_user),
) -> TeamMember:
    return await team_service.add_member(team_id, request.user_id, request.role, actor=current_user)


@router.delete("/{team_id}/members/{user_id}")
async def remove_team_member(
    team_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    success = await team_service.remove_member(team_id, user_id, actor=current_user)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in team")
    return {"success": True}
