from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import IntegrationAuditORM, utc_now


class IntegrationAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_recent(self, system: str | None = None, limit: int = 50) -> list[IntegrationAuditORM]:
        query = select(IntegrationAuditORM).order_by(IntegrationAuditORM.created_at.desc())
        if system:
            query = query.where(IntegrationAuditORM.system == system.upper())
        query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def record(
        self,
        system: str,
        action: str,
        target_id: str,
        user_id: str = "user",
        status: str = "SUCCESS",
        details: dict[str, Any] | None = None,
    ) -> IntegrationAuditORM:
        audit_id = f"audit_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = IntegrationAuditORM(
            id=audit_id,
            system=system.upper(),
            action=action.upper(),
            target_id=target_id,
            user_id=user_id,
            status=status.upper(),
            details=details or {},
            created_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm
