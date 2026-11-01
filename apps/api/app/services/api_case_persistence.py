"""Persist an authored API case: file + test case + optional criterion assertions.

Same identity and binding rules as the recorder path, so an API case saved from the workbench or from
a recording is the same object shape: `tc_api_<hash>` plus a nodeid binding.
"""

from __future__ import annotations

import hashlib

from project_model.lifecycle import CaseAssertion
from project_model.models import (
    AutomationBinding,
    AutomationBindingCreate,
    AutomationBindingStatus,
    AutomationStatus,
    FrameworkType,
    ModernTestModel,
    RequirementDocument,
    TestCase,
    TestCaseCreate,
    TestCaseUpdate,
)
from pydantic import BaseModel, Field

from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services.api_case_service import ApiCaseRequest, compile_api_case
from app.services.automation_binding_service import AutomationBindingService
from app.services.workspace_service import WorkspaceService


class SaveApiCasePayload(BaseModel):
    project_id: str
    requirement_id: str | None = None
    scenario_id: str | None = None
    criterion_ids: list[str] = Field(default_factory=list, max_length=20)
    request: ApiCaseRequest


class ApiCaseSaveService:
    def __init__(
        self,
        project_repo: ProjectRepository,
        requirement_repo: RequirementRepository,
        test_case_repo: TestCaseRepository,
        binding_repo: AutomationBindingRepository,
        binding_service: AutomationBindingService,
        workspace_service: WorkspaceService,
    ) -> None:
        self.project_repo = project_repo
        self.requirement_repo = requirement_repo
        self.test_case_repo = test_case_repo
        self.binding_repo = binding_repo
        self.binding_service = binding_service
        self.workspace_service = workspace_service

    async def save(self, payload: SaveApiCasePayload) -> dict:
        if not await self.project_repo.get_by_id(payload.project_id):
            raise LookupError("Project not found")

        criteria: list[str] = []
        if payload.requirement_id:
            requirement = await self.requirement_repo.get_by_id(payload.requirement_id)
            if requirement is None:
                raise LookupError("Requirement not found")
            if requirement.project_id != payload.project_id:
                raise ValueError("Requirement belongs to another project")
            document = RequirementDocument.model_validate(requirement.qa_model or {})
            known = {item.id for item in document.criteria}
            unknown = sorted(set(payload.criterion_ids) - known)
            if unknown:
                raise ValueError(f"Unknown criteria: {', '.join(unknown)}")
            criteria = sorted(set(payload.criterion_ids))

        compiled = compile_api_case(payload.request)
        file_path = f"tests/{compiled['test_name']}.py"
        await self.workspace_service.write_file(payload.project_id, file_path, compiled["code"])

        identity = hashlib.sha256(
            f"{payload.project_id}\0{file_path}\0{compiled['test_name']}".encode("utf-8")
        ).hexdigest()[:29]
        case_id = f"tc_api_{identity}"
        nodeid = f"{file_path}::{compiled['test_name']}"
        title = f"API {payload.request.method} {payload.request.url.split('?')[0]}"
        assertions = [
            CaseAssertion(
                id=f"TCA-API-{criterion.replace('AC-', '')}",
                criterion_id=criterion,
                statement=f"{payload.request.method} {payload.request.url} returns the expected response",
                check=f"httpx {payload.request.method} {payload.request.url}",
                nodeid=nodeid,
            )
            for criterion in criteria
        ]
        test_model = ModernTestModel(
            display_id=compiled["test_name"],
            intent=title,
            scenario_id=payload.scenario_id,
            assertions=assertions,
        )
        existing = await self.test_case_repo.get_by_id(case_id)
        if existing is not None:
            saved_case = await self.test_case_repo.update(
                case_id,
                TestCaseUpdate(
                    title=title,
                    steps=[f"{payload.request.method} {payload.request.url}"],
                    requirement_id=payload.requirement_id,
                    test_model=test_model,
                    automation_status=AutomationStatus.AUTOMATED,
                ),
            )
            reused = True
        else:
            saved_case = await self.test_case_repo.create(
                TestCaseCreate(
                    project_id=payload.project_id,
                    requirement_id=payload.requirement_id,
                    title=title,
                    steps=[f"{payload.request.method} {payload.request.url}"],
                    test_model=test_model,
                    automation_status=AutomationStatus.AUTOMATED,
                    external_system="API_WORKBENCH",
                    external_case_id=identity,
                ),
                case_id=case_id,
            )
            reused = False

        binding = await self.binding_service.bind_test_case(
            AutomationBindingCreate(
                test_case_id=case_id,
                workspace_id=payload.project_id,
                nodeid=nodeid,
                file_path=file_path,
                framework=FrameworkType.PLAYWRIGHT_PYTHON,
                status=AutomationBindingStatus.ACTIVE,
            )
        )
        return {
            "test_case": TestCase.model_validate(saved_case, from_attributes=True).model_dump(mode="json"),
            "binding": AutomationBinding.model_validate(binding, from_attributes=True).model_dump(mode="json"),
            "file_path": file_path,
            "nodeid": nodeid,
            "reused": reused,
            "assertions": [item.model_dump(mode="json") for item in assertions],
        }
