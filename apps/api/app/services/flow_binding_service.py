"""Bind a compiled flow to the requirement script map and a test case.

The flow canvas writes an ordinary pytest file. This service records the same identity the recorder
uses (nodeid + file path), maps the flow's assertion criteria onto the requirement's script pairing
(so `case_assertions` can derive nodeids at read time), and creates or refreshes the test case whose
`test_model.assertions` carry the criteria.
"""

from __future__ import annotations

import hashlib

from project_model.lifecycle import CaseAssertion
from project_model.models import (
    AutomationBindingCreate,
    AutomationBindingStatus,
    AutomationStatus,
    FrameworkType,
    ModernTestModel,
    RequirementDocument,
    TestCaseCreate,
    TestCaseUpdate,
)
from pydantic import BaseModel, Field

from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services.automation_binding_service import AutomationBindingService


class FlowAssertion(BaseModel):
    criterion_id: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=8, max_length=400)
    check: str = Field(default="", max_length=400)


class BindFlowRequest(BaseModel):
    project_id: str
    requirement_id: str
    scenario_id: str | None = None
    file_path: str = Field(min_length=1, max_length=500)
    test_name: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=250)
    steps: list[str] = Field(default_factory=list, max_length=100)
    assertions: list[FlowAssertion] = Field(default_factory=list, max_length=30)


class FlowBindingService:
    def __init__(
        self,
        requirement_repo: RequirementRepository,
        test_case_repo: TestCaseRepository,
        binding_repo: AutomationBindingRepository,
        binding_service: AutomationBindingService,
    ) -> None:
        self.requirement_repo = requirement_repo
        self.test_case_repo = test_case_repo
        self.binding_repo = binding_repo
        self.binding_service = binding_service

    async def bind(self, request: BindFlowRequest) -> dict:
        requirement = await self.requirement_repo.get_by_id(request.requirement_id)
        if requirement is None:
            raise LookupError("Requirement not found")
        if requirement.project_id != request.project_id:
            raise ValueError("Requirement belongs to another project")
        document = RequirementDocument.model_validate(requirement.qa_model or {})
        criteria = {item.id for item in document.criteria}

        unknown = sorted({item.criterion_id for item in request.assertions} - criteria)
        if unknown:
            raise ValueError(f"Unknown criteria: {', '.join(unknown)}")

        nodeid = f"{request.file_path}::{request.test_name}"
        # The case assertion rows carry the nodeid themselves, so the requirement's script map is not
        # modified here: it is owned by the generated-from-assertions path and requires requirement
        # assertions this flow may not have.
        case_id, created = await self._upsert_case(request, nodeid)
        await self.binding_service.bind_test_case(
            AutomationBindingCreate(
                test_case_id=case_id,
                workspace_id=request.project_id,
                nodeid=nodeid,
                file_path=request.file_path,
                framework=FrameworkType.PLAYWRIGHT_PYTHON,
                status=AutomationBindingStatus.ACTIVE,
            )
        )
        return {
            "case_id": case_id,
            "nodeid": nodeid,
            "created": created,
            "assertions": [
                {
                    "criterion_id": item.criterion_id,
                    "statement": item.statement,
                    "nodeid": nodeid,
                }
                for item in request.assertions
            ],
        }

    async def _upsert_case(self, request: BindFlowRequest, nodeid: str) -> tuple[str, bool]:
        identity = hashlib.sha256(
            f"{request.project_id}\0{request.file_path}\0{request.test_name}".encode("utf-8")
        ).hexdigest()[:29]
        case_id = f"tc_flow_{identity}"
        assertions = []
        for item in request.assertions:
            statement = item.statement.strip()
            if len(statement) < 8:
                statement = f"expects {statement}".strip()
            assertions.append(
                CaseAssertion(
                    id=f"TCA-{item.criterion_id}",
                    criterion_id=item.criterion_id,
                    statement=statement[:400],
                    check=item.check,
                    nodeid=nodeid,
                )
            )
        test_model = ModernTestModel(
            display_id=request.test_name,
            intent=request.title,
            scenario_id=request.scenario_id,
            assertions=assertions,
        )
        existing = await self.test_case_repo.get_by_id(case_id)
        if existing is not None:
            await self.test_case_repo.update(
                case_id,
                TestCaseUpdate(
                    title=request.title,
                    steps=request.steps,
                    requirement_id=request.requirement_id,
                    test_model=test_model,
                    automation_status=AutomationStatus.AUTOMATED,
                ),
            )
            return case_id, False
        await self.test_case_repo.create(
            TestCaseCreate(
                project_id=request.project_id,
                requirement_id=request.requirement_id,
                title=request.title,
                steps=request.steps,
                test_model=test_model,
                automation_status=AutomationStatus.AUTOMATED,
                external_system="FLOW_CANVAS",
                external_case_id=identity,
            ),
            case_id=case_id,
        )
        return case_id, True
