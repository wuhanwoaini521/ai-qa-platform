"""Project-scoped access decisions.

The role policy (``authz.py``) answers "may this role use this feature"; this service answers "may
this caller touch *this* project". Administrators stay unrestricted so the single-operator workflow
is unchanged. Everyone else is limited to projects they own or share through one of their teams. A
project with neither owner nor team ("legacy") is admin-only until a security admin claims it.
"""

from __future__ import annotations

from project_model.models import User, UserRole

from app.repositories.project_access_repo import ProjectAccessRepository

#: resource kind -> repository method, used by the route guards.
RESOLVERS = {
    "artifact": "project_of_artifact",
    "run": "project_of_run",
    "failure": "project_of_failure",
    "workspace": "project_of_workspace",
    "requirement": "project_of_requirement",
    "test_design": "project_of_test_design",
    "case": "project_of_case",
    "release": "project_of_release",
    "discovery_run": "project_of_discovery_run",
}


def is_admin(user: User) -> bool:
    return user.role is UserRole.ADMIN


class ProjectAccessService:
    def __init__(self, access: ProjectAccessRepository) -> None:
        self.access = access

    async def visible_project_ids(self, user: User) -> set[str] | None:
        """Project ids this caller may access; ``None`` means every project (administrators)."""
        if is_admin(user):
            return None
        return await self.access.owned_or_shared_project_ids(str(user.id))

    async def can_access(self, user: User, project_id: str | None) -> bool:
        if is_admin(user):
            return True
        if not project_id:
            return False
        allowed = await self.visible_project_ids(user)
        return allowed is not None and project_id in allowed

    async def project_of(self, kind: str, resource_id: str) -> str | None:
        method = RESOLVERS.get(kind)
        if method is None:
            raise ValueError(f"unknown ACL resource kind: {kind}")
        return await getattr(self.access, method)(resource_id)
