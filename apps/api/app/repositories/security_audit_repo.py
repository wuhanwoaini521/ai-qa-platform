from __future__ import annotations

import uuid
from typing import Any

from project_model.models import SecurityAuditLogEntry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence import database
from app.persistence.models import SecurityAuditORM, utc_now


class SecurityAuditRepository:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self):
        if self._session_factory is not None:
            return self._session_factory

        return database.get_session

    async def log(
        self,
        action: str,
        actor_id: str,
        actor_email: str,
        target_resource: str,
        status: str = "SUCCESS",
        ip_address: str = "127.0.0.1",
        details: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> SecurityAuditLogEntry:
        entry_id = str(uuid.uuid4())
        orm = SecurityAuditORM(
            id=entry_id,
            action=action,
            actor_id=actor_id,
            actor_email=actor_email,
            target_resource=target_resource,
            ip_address=ip_address,
            status=status,
            details=details or {},
            created_at=utc_now(),
        )

        async def _exec(s: AsyncSession) -> SecurityAuditLogEntry:
            s.add(orm)
            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def list_logs(
        self,
        actor_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
        session: AsyncSession | None = None,
    ) -> list[SecurityAuditLogEntry]:
        async def _exec(s: AsyncSession) -> list[SecurityAuditLogEntry]:
            stmt = select(SecurityAuditORM)
            if actor_id:
                stmt = stmt.where(SecurityAuditORM.actor_id == actor_id)
            if action:
                stmt = stmt.where(SecurityAuditORM.action == action)
            stmt = stmt.order_by(SecurityAuditORM.created_at.desc()).limit(limit)
            res = await s.execute(stmt)
            return [self._to_model(orm) for orm in res.scalars().all()]

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    @staticmethod
    def _to_model(orm: SecurityAuditORM) -> SecurityAuditLogEntry:
        return SecurityAuditLogEntry(
            id=orm.id,
            action=orm.action,
            actor_id=orm.actor_id,
            actor_email=orm.actor_email,
            target_resource=orm.target_resource,
            ip_address=orm.ip_address,
            status=orm.status,
            details=orm.details or {},
            created_at=orm.created_at,
        )
