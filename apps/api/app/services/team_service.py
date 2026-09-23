from __future__ import annotations

from project_model.models import Team, TeamCreate, TeamMember, TeamUpdate, User

from app.repositories.security_audit_repo import SecurityAuditRepository
from app.repositories.team_repo import TeamRepository


class TeamService:
    def __init__(
        self,
        team_repo: TeamRepository | None = None,
        audit_repo: SecurityAuditRepository | None = None,
    ) -> None:
        self.team_repo = team_repo or TeamRepository()
        self.audit_repo = audit_repo or SecurityAuditRepository()

    async def get_team(self, team_id: str) -> Team | None:
        return await self.team_repo.get_by_id(team_id)

    async def list_teams(self, limit: int = 100) -> list[Team]:
        return await self.team_repo.list_all(limit=limit)

    async def create_team(self, data: TeamCreate, actor: User | None = None) -> Team:
        team = await self.team_repo.create(data)
        await self.audit_repo.log(
            action="TEAM_CREATE",
            actor_id=actor.id if actor else "system",
            actor_email=actor.email if actor else "system",
            target_resource=f"team:{team.id}",
            status="SUCCESS",
            details={"name": team.name},
        )
        return team

    async def update_team(self, team_id: str, data: TeamUpdate, actor: User | None = None) -> Team | None:
        return await self.team_repo.update(team_id, data)

    async def delete_team(self, team_id: str, actor: User | None = None) -> bool:
        success = await self.team_repo.delete(team_id)
        if success:
            await self.audit_repo.log(
                action="TEAM_DELETE",
                actor_id=actor.id if actor else "system",
                actor_email=actor.email if actor else "system",
                target_resource=f"team:{team_id}",
                status="SUCCESS",
            )
        return success

    async def add_member(
        self, team_id: str, user_id: str, role: str = "MEMBER", actor: User | None = None
    ) -> TeamMember:
        member = await self.team_repo.add_member(team_id, user_id, role)
        await self.audit_repo.log(
            action="TEAM_ADD_MEMBER",
            actor_id=actor.id if actor else "system",
            actor_email=actor.email if actor else "system",
            target_resource=f"team:{team_id}/user:{user_id}",
            status="SUCCESS",
            details={"role": role},
        )
        return member

    async def remove_member(self, team_id: str, user_id: str, actor: User | None = None) -> bool:
        return await self.team_repo.remove_member(team_id, user_id)
