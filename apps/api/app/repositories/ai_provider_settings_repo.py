from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import AIProviderConfigORM, DecisionProviderConfigORM


class AIProviderSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_default(self) -> AIProviderConfigORM | None:
        result = await self.session.execute(select(AIProviderConfigORM).where(AIProviderConfigORM.id == "default"))
        return result.scalar_one_or_none()

    async def save_default(self, values: dict) -> AIProviderConfigORM:
        row = await self.get_default()
        if row is None:
            row = AIProviderConfigORM(id="default")
            self.session.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        await self.session.flush()
        return row


class DecisionProviderSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_jev(self) -> DecisionProviderConfigORM | None:
        return await self.session.get(DecisionProviderConfigORM, "jev")

    async def save_jev(self, values: dict) -> DecisionProviderConfigORM:
        row = await self.get_jev()
        if row is None:
            row = DecisionProviderConfigORM(provider="jev", **values)
            self.session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await self.session.flush()
        return row
