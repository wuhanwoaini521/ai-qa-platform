from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from project_model.models import IntegrationAuditEntry
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.integration_audit_repo import IntegrationAuditRepository

router = APIRouter(prefix="/audit", tags=["Integration Audit"])


def get_audit_repo(session: AsyncSession = Depends(get_db)) -> IntegrationAuditRepository:
    return IntegrationAuditRepository(session)


@router.get("/integrations", response_model=list[IntegrationAuditEntry])
async def list_integration_audits(
    system: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    repo: IntegrationAuditRepository = Depends(get_audit_repo),
):
    orms = await repo.list_recent(system=system, limit=limit)
    return [
        IntegrationAuditEntry(
            id=orm.id,
            system=orm.system,
            action=orm.action,
            target_id=orm.target_id,
            user_id=orm.user_id,
            status=orm.status,
            details=orm.details or {},
            created_at=orm.created_at,
        )
        for orm in orms
    ]
