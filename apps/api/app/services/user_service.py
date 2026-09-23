from __future__ import annotations

from project_model.models import User, UserCreate, UserUpdate

from app.repositories.security_audit_repo import SecurityAuditRepository
from app.repositories.user_repo import UserRepository


class UserService:
    def __init__(
        self,
        user_repo: UserRepository | None = None,
        audit_repo: SecurityAuditRepository | None = None,
    ) -> None:
        self.user_repo = user_repo or UserRepository()
        self.audit_repo = audit_repo or SecurityAuditRepository()

    async def get_user(self, user_id: str) -> User | None:
        return await self.user_repo.get_by_id(user_id)

    async def list_users(self, limit: int = 100) -> list[User]:
        return await self.user_repo.list_all(limit=limit)

    async def create_user(self, data: UserCreate, actor: User | None = None) -> User:
        user = await self.user_repo.create(data)
        await self.audit_repo.log(
            action="USER_CREATE",
            actor_id=actor.id if actor else "system",
            actor_email=actor.email if actor else "system",
            target_resource=f"user:{user.id}",
            status="SUCCESS",
            details={"email": user.email, "role": user.role.value},
        )
        return user

    async def update_user(self, user_id: str, data: UserUpdate, actor: User | None = None) -> User | None:
        updated = await self.user_repo.update(user_id, data)
        if updated:
            await self.audit_repo.log(
                action="USER_UPDATE",
                actor_id=actor.id if actor else "system",
                actor_email=actor.email if actor else "system",
                target_resource=f"user:{user_id}",
                status="SUCCESS",
                details={"role": updated.role.value, "is_active": updated.is_active},
            )
        return updated

    async def delete_user(self, user_id: str, actor: User | None = None) -> bool:
        success = await self.user_repo.delete(user_id)
        if success:
            await self.audit_repo.log(
                action="USER_DELETE",
                actor_id=actor.id if actor else "system",
                actor_email=actor.email if actor else "system",
                target_resource=f"user:{user_id}",
                status="SUCCESS",
            )
        return success
