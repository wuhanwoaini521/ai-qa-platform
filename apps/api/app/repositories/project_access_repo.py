"""Read-only queries that answer "which project does this resource belong to?" for the ACL guards.

Kept in the repository layer so routers keep zero persistence knowledge; the guards in
``app/api/project_acl.py`` consume it through ``ProjectAccessService``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import (
    FailureRecordORM,
    ProjectORM,
    QualityDiscoveryRunORM,
    ReleaseORM,
    RequirementORM,
    TeamMemberORM,
    TestCaseORM,
    TestRunORM,
    WorkspaceORM,
)


class ProjectAccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def owned_or_shared_project_ids(self, user_id: str) -> set[str]:
        owned = select(ProjectORM.id).where(ProjectORM.owner_id == user_id)
        team_ids = select(TeamMemberORM.team_id).where(TeamMemberORM.user_id == user_id)
        shared = select(ProjectORM.id).where(ProjectORM.team_id.in_(team_ids))
        ids = set((await self.session.execute(owned)).scalars())
        ids.update((await self.session.execute(shared)).scalars())
        return ids

    async def project_of_run(self, run_id: str) -> str | None:
        return await self._scalar(select(TestRunORM.project_id).where(TestRunORM.id == run_id))

    async def project_of_failure(self, failure_id: str) -> str | None:
        return await self._scalar(
            select(TestRunORM.project_id)
            .join(FailureRecordORM, FailureRecordORM.run_id == TestRunORM.id)
            .where(FailureRecordORM.id == failure_id)
        )

    async def project_of_workspace(self, workspace_id: str) -> str | None:
        return await self._scalar(select(WorkspaceORM.project_id).where(WorkspaceORM.id == workspace_id))

    async def project_of_requirement(self, requirement_id: str) -> str | None:
        return await self._scalar(select(RequirementORM.project_id).where(RequirementORM.id == requirement_id))

    async def project_of_case(self, case_id: str) -> str | None:
        return await self._scalar(select(TestCaseORM.project_id).where(TestCaseORM.id == case_id))

    async def project_of_release(self, release_id: str) -> str | None:
        return await self._scalar(select(ReleaseORM.project_id).where(ReleaseORM.id == release_id))

    async def project_of_discovery_run(self, run_id: str) -> str | None:
        return await self._scalar(select(QualityDiscoveryRunORM.project_id).where(QualityDiscoveryRunORM.id == run_id))

    async def _scalar(self, query) -> str | None:
        return (await self.session.execute(query)).scalar_one_or_none()
