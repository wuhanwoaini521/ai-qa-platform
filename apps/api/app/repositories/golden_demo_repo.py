from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import ProjectORM, RequirementORM, TaskORM, TestRunORM

ACTIVE_TASK_STATUSES = [
    "PENDING",
    "PLANNING",
    "RUNNING",
    "WAITING",
    "VERIFYING",
    "RETRYING",
    "REPLANNING",
    "BLOCKED",
]


class GoldenDemoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project_for_update(self, project_id: str) -> ProjectORM | None:
        result = await self.session.execute(select(ProjectORM).where(ProjectORM.id == project_id).with_for_update())
        return result.scalar_one_or_none()

    async def has_active_run(self, project_id: str) -> bool:
        result = await self.session.execute(
            select(TestRunORM.id)
            .where(TestRunORM.project_id == project_id, TestRunORM.status.in_(["QUEUED", "RUNNING"]))
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def has_active_task(self, project_id: str) -> bool:
        result = await self.session.execute(
            select(TaskORM.id)
            .where(TaskORM.project_id == project_id, TaskORM.status.in_(ACTIVE_TASK_STATUSES))
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_requirement(self, requirement_id: str) -> RequirementORM | None:
        return await self.session.get(RequirementORM, requirement_id)

    async def replace_seed(
        self, project, workspace, requirement, test_rows: list[tuple], *, replace_existing: bool
    ) -> None:
        if replace_existing:
            existing = await self.get_project_for_update(project["id"])
            if existing is None:
                raise ValueError("Demo project changed while reset was in progress")
            await self.session.delete(existing)
            await self.session.flush()
        project = ProjectORM(**project)
        self.session.add(project)
        await self.session.flush()
        from app.persistence.models import RequirementORM, WorkspaceORM

        self.session.add(WorkspaceORM(**workspace))
        self.session.add(RequirementORM(**requirement))
        await self.session.flush()
        for design, case, binding in test_rows:
            from app.persistence.models import AutomationBindingORM, TestCaseORM, TestDesignORM

            design = TestDesignORM(**design)
            case = TestCaseORM(**case)
            binding = AutomationBindingORM(**binding) if binding else None
            self.session.add(design)
            await self.session.flush()
            self.session.add(case)
            await self.session.flush()
            if binding is not None:
                self.session.add(binding)
