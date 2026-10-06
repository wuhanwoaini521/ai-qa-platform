from __future__ import annotations

import uuid

from project_model.models import TestCaseCreate, TestCaseUpdate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.models import TestCaseORM, utc_now


class TestCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_project(self, project_id: str, limit: int | None = None) -> list[TestCaseORM]:
        query = (
            select(TestCaseORM)
            .options(selectinload(TestCaseORM.binding))
            .where(TestCaseORM.project_id == project_id)
            .order_by(TestCaseORM.created_at.desc())
        )
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_all(self) -> int:
        """Row count without materialising the table."""
        result = await self.session.execute(select(func.count()).select_from(TestCaseORM))
        return int(result.scalar() or 0)

    async def list_all(self, limit: int | None = None) -> list[TestCaseORM]:
        query = select(TestCaseORM).options(selectinload(TestCaseORM.binding)).order_by(TestCaseORM.created_at.desc())
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, case_id: str) -> TestCaseORM | None:
        result = await self.session.execute(
            select(TestCaseORM).options(selectinload(TestCaseORM.binding)).where(TestCaseORM.id == case_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: TestCaseCreate, *, case_id: str | None = None) -> TestCaseORM:
        case_id = case_id or f"tc_{uuid.uuid4().hex[:12]}"
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
            test_model=data.test_model.model_dump(mode="json") if data.test_model else None,
            priority=data.priority.value,
            automation_status=data.automation_status.value,
            tags=data.tags,
            external_system=data.external_system,
            external_case_id=data.external_case_id,
            external_url=data.external_url,
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
