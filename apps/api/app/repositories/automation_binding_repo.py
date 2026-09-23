from __future__ import annotations

import uuid

from project_model.models import AutomationBindingCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import AutomationBindingORM, utc_now


class AutomationBindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_test_case_id(self, test_case_id: str) -> AutomationBindingORM | None:
        result = await self.session.execute(
            select(AutomationBindingORM).where(AutomationBindingORM.test_case_id == test_case_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, binding_id: str) -> AutomationBindingORM | None:
        result = await self.session.execute(select(AutomationBindingORM).where(AutomationBindingORM.id == binding_id))
        return result.scalar_one_or_none()

    async def create_or_update(self, data: AutomationBindingCreate) -> AutomationBindingORM:
        existing = await self.get_by_test_case_id(data.test_case_id)
        now = utc_now()
        if existing:
            existing.workspace_id = data.workspace_id
            existing.nodeid = data.nodeid
            existing.file_path = data.file_path
            existing.framework = data.framework.value
            existing.status = data.status.value
            existing.updated_at = now
            await self.session.flush()
            return existing

        binding_id = f"bind_{uuid.uuid4().hex[:12]}"
        orm = AutomationBindingORM(
            id=binding_id,
            test_case_id=data.test_case_id,
            workspace_id=data.workspace_id,
            nodeid=data.nodeid,
            file_path=data.file_path,
            framework=data.framework.value,
            status=data.status.value,
            created_at=now,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def delete_by_test_case_id(self, test_case_id: str) -> bool:
        existing = await self.get_by_test_case_id(test_case_id)
        if not existing:
            return False
        await self.session.delete(existing)
        await self.session.flush()
        return True
