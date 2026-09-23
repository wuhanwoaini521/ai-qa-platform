from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from project_model.models import (
    BranchInfo,
    GitBranchCreateRequest,
    GitChangedFile,
    GitCommitInfo,
    GitCommitRequest,
    GitPushResult,
    PRChecksSummary,
    PRDiagnosisRequest,
    PRDiagnosisResponse,
    PRSummarySuggestionRequest,
    PRSummarySuggestionResponse,
    PullRequestCreateRequest,
    PullRequestInfo,
)

from app.persistence.database import get_db
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.pr_service import PullRequestService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["Git & PR Workflow"])


def get_workspace_service() -> WorkspaceService:
    return WorkspaceService()


def get_pr_service(db=Depends(get_db)) -> PullRequestService:
    ws_service = WorkspaceService()
    return PullRequestService(
        workspace_service=ws_service,
        workspace_repo=WorkspaceRepository(db),
        project_repo=ProjectRepository(db),
        requirement_repo=RequirementRepository(db),
        test_case_repo=TestCaseRepository(db),
        binding_repo=AutomationBindingRepository(db),
        test_run_repo=TestRunRepository(db),
        run_history_repo=RunHistoryRepository(db),
    )


# --- Git Endpoints ---
@router.get("/git/status", response_model=list[GitChangedFile])
async def get_git_status(
    workspace_id: str,
    ws_service: WorkspaceService = Depends(get_workspace_service),
) -> list[GitChangedFile]:
    return await ws_service.get_git_status(workspace_id)


@router.get("/git/branches", response_model=list[BranchInfo])
async def get_git_branches(
    workspace_id: str,
    ws_service: WorkspaceService = Depends(get_workspace_service),
) -> list[BranchInfo]:
    return await ws_service.get_branches(workspace_id)


@router.get("/git/current-branch", response_model=str)
async def get_current_branch(
    workspace_id: str,
    ws_service: WorkspaceService = Depends(get_workspace_service),
) -> str:
    return await ws_service.get_current_branch(workspace_id)


@router.post("/git/branch", response_model=str)
async def create_git_branch(
    workspace_id: str,
    payload: GitBranchCreateRequest,
    ws_service: WorkspaceService = Depends(get_workspace_service),
) -> str:
    try:
        return await ws_service.create_branch(workspace_id, payload.branch_name, checkout=payload.checkout)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/switch-branch", response_model=str)
async def switch_git_branch(
    workspace_id: str,
    payload: GitBranchCreateRequest,
    ws_service: WorkspaceService = Depends(get_workspace_service),
) -> str:
    try:
        return await ws_service.switch_branch(workspace_id, payload.branch_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/commit", response_model=str)
async def commit_git_changes(
    workspace_id: str,
    payload: GitCommitRequest,
    ws_service: WorkspaceService = Depends(get_workspace_service),
) -> str:
    try:
        author_name = payload.author_name or "AI QA Platform"
        author_email = payload.author_email or "agent@ai-qa.local"
        return await ws_service.commit_changes(
            workspace_id, payload.message, author_name=author_name, author_email=author_email
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/git/push", response_model=GitPushResult)
async def push_git_branch(
    workspace_id: str,
    branch: str | None = None,
    remote: str = "origin",
    ws_service: WorkspaceService = Depends(get_workspace_service),
) -> GitPushResult:
    try:
        return await ws_service.push_branch(workspace_id, branch=branch, remote=remote)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/git/log", response_model=list[GitCommitInfo])
async def get_git_log(
    workspace_id: str,
    limit: int = Query(default=15, ge=1, le=100),
    ws_service: WorkspaceService = Depends(get_workspace_service),
) -> list[GitCommitInfo]:
    return await ws_service.get_git_log(workspace_id, limit=limit)


# --- PR Endpoints ---
@router.post("/pr/suggest-summary", response_model=PRSummarySuggestionResponse)
async def suggest_pr_summary(
    workspace_id: str,
    payload: PRSummarySuggestionRequest,
    pr_service: PullRequestService = Depends(get_pr_service),
) -> PRSummarySuggestionResponse:
    try:
        return await pr_service.suggest_pr_summary(
            workspace_id=workspace_id,
            requirement_ids=payload.requirement_ids,
            test_case_ids=payload.test_case_ids,
            include_diff=payload.include_diff,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pr/create", response_model=PullRequestInfo)
async def create_pull_request(
    workspace_id: str,
    payload: PullRequestCreateRequest,
    pr_service: PullRequestService = Depends(get_pr_service),
) -> PullRequestInfo:
    try:
        return await pr_service.create_pull_request(workspace_id=workspace_id, request=payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pr/{pr_number}/checks", response_model=PRChecksSummary)
async def get_pr_checks(
    workspace_id: str,
    pr_number: int,
    pr_service: PullRequestService = Depends(get_pr_service),
) -> PRChecksSummary:
    try:
        return await pr_service.get_pr_checks(workspace_id=workspace_id, pr_number=pr_number)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pr/diagnose", response_model=PRDiagnosisResponse)
async def diagnose_pr_failure(
    workspace_id: str,
    payload: PRDiagnosisRequest,
    pr_service: PullRequestService = Depends(get_pr_service),
) -> PRDiagnosisResponse:
    try:
        return await pr_service.diagnose_failure(payload.failure_logs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
