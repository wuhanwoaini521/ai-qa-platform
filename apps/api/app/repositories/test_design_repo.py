from __future__ import annotations

import uuid

from project_model.models import TestDesignCreate, TestDesignUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import TestDesignORM, utc_now


class TestDesignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_requirement(self, requirement_id: str) -> list[TestDesignORM]:
        result = await self.session.execute(
            select(TestDesignORM)
            .where(TestDesignORM.requirement_id == requirement_id)
            .order_by(TestDesignORM.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, design_id: str) -> TestDesignORM | None:
        result = await self.session.execute(select(TestDesignORM).where(TestDesignORM.id == design_id))
        return result.scalar_one_or_none()

    async def create(self, data: TestDesignCreate) -> TestDesignORM:
        design_id = f"des_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = TestDesignORM(
            id=design_id,
            requirement_id=data.requirement_id,
            title=data.title,
            category=data.category.value,
            description=data.description,
            risk=data.risk,
            status=data.status,
            created_at=now,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def update(self, design_id: str, data: TestDesignUpdate) -> TestDesignORM | None:
        orm = await self.get_by_id(design_id)
        if not orm:
            return None
        values = data.model_dump(exclude_unset=True)
        if "category" in values and values["category"] is not None:
            values["category"] = values["category"].value
        for k, v in values.items():
            setattr(orm, k, v)
        orm.updated_at = utc_now()
        await self.session.flush()
        return orm
