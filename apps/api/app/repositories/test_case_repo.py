from __future__ import annotations

import uuid

from project_model.models import TestCaseCreate, TestCaseUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import TestCaseORM, utc_now


class TestCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_project(self, project_id: str) -> list[TestCaseORM]:
        result = await self.session.execute(
            select(TestCaseORM).where(TestCaseORM.project_id == project_id).order_by(TestCaseORM.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[TestCaseORM]:
        result = await self.session.execute(select(TestCaseORM).order_by(TestCaseORM.created_at.desc()))
        return list(result.scalars().all())

    async def get_by_id(self, case_id: str) -> TestCaseORM | None:
        result = await self.session.execute(select(TestCaseORM).where(TestCaseORM.id == case_id))
        return result.scalar_one_or_none()

    async def create(self, data: TestCaseCreate) -> TestCaseORM:
        case_id = f"tc_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = TestCaseORM(
            id=case_id,
            project_id=data.project_id,
            requirement_id=data.requirement_id,
            test_design_id=data.test_design_id,
            title=data.title,
            preconditions=data.preconditions,
            steps=data.steps,
            expected_result=data.expected_result,
            priority=data.priority.value,
            automation_status=data.automation_status.value,
            tags=data.tags,
            created_at=now,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def update(self, case_id: str, data: TestCaseUpdate) -> TestCaseORM | None:
        orm = await self.get_by_id(case_id)
        if not orm:
            return None
        values = data.model_dump(exclude_unset=True)
        if "priority" in values and values["priority"] is not None:
            values["priority"] = values["priority"].value
        if "automation_status" in values and values["automation_status"] is not None:
            values["automation_status"] = values["automation_status"].value
        for k, v in values.items():
            setattr(orm, k, v)
        orm.updated_at = utc_now()
        await self.session.flush()
        return orm
