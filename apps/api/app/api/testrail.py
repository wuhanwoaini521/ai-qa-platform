from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from project_model.models import (
    TestRailCase,
    TestRailPublishPreview,
    TestRailPublishRequest,
    TestRailPublishResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.integration_audit_repo import IntegrationAuditRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.testrail_service import TestRailService

router = APIRouter(prefix="/testrail", tags=["TestRail Integration"])


def get_testrail_service(session: AsyncSession = Depends(get_db)) -> TestRailService:
    test_run_repo = TestRunRepository(session)
    test_case_repo = TestCaseRepository(session)
    audit_repo = IntegrationAuditRepository(session)
    return TestRailService(
        test_run_repo=test_run_repo,
        test_case_repo=test_case_repo,
        audit_repo=audit_repo,
    )


@router.get("/cases", response_model=list[TestRailCase])
async def list_testrail_cases(
    suite_id: str = Query(default="S101"),
    limit: int = Query(default=50, ge=1, le=200),
    service: TestRailService = Depends(get_testrail_service),
):
    return service.list_cases(suite_id=suite_id, limit=limit)


@router.get("/cases/{case_id}", response_model=TestRailCase)
async def get_testrail_case(
    case_id: str,
    service: TestRailService = Depends(get_testrail_service),
):
    case = service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"TestRail case '{case_id}' not found")
    return case


@router.get("/runs/{run_id}/preview", response_model=TestRailPublishPreview)
async def preview_testrail_publish(
    run_id: str,
    suite_id: str = Query(default="S101"),
    service: TestRailService = Depends(get_testrail_service),
):
    return await service.preview_publish(run_id=run_id, suite_id=suite_id)


@router.post("/publish", response_model=TestRailPublishResponse)
async def publish_testrail_results(
    body: TestRailPublishRequest,
    service: TestRailService = Depends(get_testrail_service),
):
    return await service.publish_results(body)
