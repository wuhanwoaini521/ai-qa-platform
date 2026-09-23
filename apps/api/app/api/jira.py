from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from project_model.models import (
    JiraBugDraft,
    JiraBugDraftRequest,
    JiraCreateBugRequest,
    JiraCreateBugResponse,
    JiraImportRequest,
    JiraIssue,
    Requirement,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.integration_audit_repo import IntegrationAuditRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.jira_service import JiraService

router = APIRouter(prefix="/jira", tags=["Jira Integration"])


def get_jira_service(session: AsyncSession = Depends(get_db)) -> JiraService:
    req_repo = RequirementRepository(session)
    audit_repo = IntegrationAuditRepository(session)
    test_run_repo = TestRunRepository(session)
    return JiraService(
        requirement_repo=req_repo,
        audit_repo=audit_repo,
        test_run_repo=test_run_repo,
    )


@router.get("/issues", response_model=list[JiraIssue])
async def search_jira_issues(
    query: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    service: JiraService = Depends(get_jira_service),
):
    return service.search_issues(query=query, limit=limit)


@router.get("/issues/{key}", response_model=JiraIssue)
async def get_jira_issue(
    key: str,
    service: JiraService = Depends(get_jira_service),
):
    issue = service.get_issue(key)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Jira issue '{key}' not found")
    return issue


@router.post("/import", response_model=list[Requirement])
async def import_jira_issues(
    body: JiraImportRequest,
    service: JiraService = Depends(get_jira_service),
):
    return await service.import_requirements(
        issue_keys=body.issue_keys,
        project_id=body.project_id,
    )


@router.post("/bug-draft", response_model=JiraBugDraft)
async def generate_jira_bug_draft(
    body: JiraBugDraftRequest,
    service: JiraService = Depends(get_jira_service),
):
    try:
        return await service.create_bug_draft(body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/create-bug", response_model=JiraCreateBugResponse)
async def create_jira_bug(
    body: JiraCreateBugRequest,
    service: JiraService = Depends(get_jira_service),
):
    return await service.create_bug(body)
