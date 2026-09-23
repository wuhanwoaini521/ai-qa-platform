"""Onboarding a real QA repository: preview, import, provision, collect, pilot-run, Allure import.

The host-filesystem routes (`preview`, `import`) read a path the caller supplies outside the platform
workspace, so they carry an explicit permission guard on top of the central policy table.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import Permission, User
from pydantic import BaseModel, Field
from qa_core.onboarding import AllureImportReport, CollectionOutcome, RuntimeProvisioningResult, SuiteRunOutcome
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import require_permission
from app.persistence.database import get_db
from app.repositories.project_repo import ProjectRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.onboarding_service import (
    DetectionPreview,
    ImportedProject,
    OnboardingError,
    OnboardingService,
)
from app.settings import settings

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class ImportRequest(BaseModel):
    source_path: str = Field(..., description="Absolute path of the QA repository to import")
    project_name: str | None = None
    overwrite: bool = False


class RunSelectionRequest(BaseModel):
    nodeids: list[str] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)
    #: Must be set explicitly to execute tests the safety policy flags (browser/network/slow).
    allow_unsafe: bool = False
    persist: bool = True


class CollectionResponse(BaseModel):
    project_id: str
    outcome: CollectionOutcome
    identity_summary: dict | None = None


class PilotRunResponse(BaseModel):
    project_id: str
    run_id: str | None = None
    outcome: SuiteRunOutcome
    executed_nodeids: list[str] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)
    persisted: bool = False


def get_onboarding_service(session: AsyncSession = Depends(get_db)) -> OnboardingService:
    return OnboardingService(
        project_repo=ProjectRepository(session),
        workspace_repo=WorkspaceRepository(session),
        run_repo=TestRunRepository(session),
        workspace_base_dir=settings.workspace_storage_dir,
    )


def _translate(error: OnboardingError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.post("/preview", response_model=DetectionPreview)
async def preview_import(
    request: ImportRequest,
    actor: Annotated[User, Depends(require_permission(Permission.SECURITY_ADMIN))],
    service: OnboardingService = Depends(get_onboarding_service),
) -> DetectionPreview:
    """Read-only inspection of a local QA repository: what would be imported, and what was detected."""
    _ = actor
    try:
        return await service.preview_import(request.source_path, request.project_name)
    except OnboardingError as error:
        raise _translate(error) from error


@router.post("/import", response_model=ImportedProject, status_code=status.HTTP_201_CREATED)
async def import_repository(
    request: ImportRequest,
    actor: Annotated[User, Depends(require_permission(Permission.SECURITY_ADMIN))],
    service: OnboardingService = Depends(get_onboarding_service),
) -> ImportedProject:
    """Copy a local QA repository into an isolated workspace. The source is never modified."""
    _ = actor
    try:
        return await service.import_repository(
            request.source_path, project_name=request.project_name, overwrite=request.overwrite
        )
    except OnboardingError as error:
        raise _translate(error) from error
    except FileExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/{project_id}", response_model=ImportedProject)
async def get_imported_project(
    project_id: str,
    service: OnboardingService = Depends(get_onboarding_service),
) -> ImportedProject:
    try:
        return await service.get_imported_project(project_id)
    except OnboardingError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/{project_id}/runtime", response_model=RuntimeProvisioningResult)
async def provision_runtime(
    project_id: str,
    service: OnboardingService = Depends(get_onboarding_service),
) -> RuntimeProvisioningResult:
    try:
        return await service.provision_runtime(project_id)
    except OnboardingError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/{project_id}/collect", response_model=CollectionResponse)
async def collect_project(
    project_id: str,
    service: OnboardingService = Depends(get_onboarding_service),
) -> CollectionResponse:
    try:
        report = await service.collect(project_id)
    except OnboardingError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return CollectionResponse(
        project_id=report.project_id,
        outcome=report.outcome,
        identity_summary=report.identity.model_dump(exclude={"identities"}) if report.identity else None,
    )


@router.post("/{project_id}/run", response_model=PilotRunResponse)
async def run_selection(
    project_id: str,
    request: RunSelectionRequest,
    service: OnboardingService = Depends(get_onboarding_service),
) -> PilotRunResponse:
    try:
        report = await service.run_selection(
            project_id,
            nodeids=request.nodeids,
            markers=request.markers,
            allow_unsafe=request.allow_unsafe,
            persist=request.persist,
        )
    except OnboardingError as error:
        raise _translate(error) from error
    return PilotRunResponse(
        project_id=report.project_id,
        run_id=report.run_id,
        outcome=report.outcome,
        executed_nodeids=report.executed_nodeids,
        rejected=[verdict.model_dump() for verdict in report.rejected],
        persisted=report.persisted,
    )


@router.post("/{project_id}/allure", response_model=AllureImportReport)
async def import_allure(
    project_id: str,
    service: OnboardingService = Depends(get_onboarding_service),
) -> AllureImportReport:
    try:
        return await service.import_allure_results(project_id)
    except OnboardingError as error:
        raise _translate(error) from error
