from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from project_model.models import IntegrationAuditEntry

from app.container import get_audit_query_service
from app.services.api_read_service import AuditQueryService

router = APIRouter(prefix="/audit", tags=["Integration Audit"])


@router.get("/integrations", response_model=list[IntegrationAuditEntry])
async def list_integration_audits(
    system: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    service: AuditQueryService = Depends(get_audit_query_service),
):
    return await service.list_integrations(system=system, limit=limit)


@router.get("/security")
async def list_security_audits(
    actor_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    service: AuditQueryService = Depends(get_audit_query_service),
):
    return await service.list_security(actor_id=actor_id, action=action, limit=limit)
