from __future__ import annotations

import hashlib
import json
import re

from project_model.models import (
    AutomationBindingCreate,
    AutomationBindingStatus,
    AutomationStatus,
    FrameworkType,
    ModernTestModel,
    TestCaseCreate,
    TestCaseUpdate,
)
from pydantic import BaseModel, Field

from app.repositories.project_repo import ProjectRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services.api_case_service import ApiAssertion, ApiCaseRequest, ApiHeader, compile_api_case
from app.services.automation_binding_service import AutomationBindingService
from app.services.recorder_service import BrowserRecorderService, RecorderSaveCaseRequest, RecorderSessionCreate
from app.services.workspace_service import WorkspaceService


class RecorderWorkflowService:
    """Application use cases that coordinate recorder state and project persistence."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        test_case_repo: TestCaseRepository,
        binding_service: AutomationBindingService,
        recorder: BrowserRecorderService,
        workspace_service: WorkspaceService | None = None,
    ) -> None:
        self.project_repo = project_repo
        self.test_case_repo = test_case_repo
        self.binding_service = binding_service
        self.recorder = recorder
        self.workspace_service = workspace_service or WorkspaceService()

    async def create_session(self, owner_id: str, request: RecorderSessionCreate):
        if not await self.project_repo.get_by_id(request.project_id):
            raise LookupError("Project not found")
        return await self.recorder.create_session(owner_id, request)

    async def save_case(self, session_id: str, owner_id: str, request: RecorderSaveCaseRequest) -> dict:
        recording = await self.recorder.get(session_id, owner_id)
        if not recording:
            raise LookupError("Recorder session not found")
        if request.test_case.project_id != recording.project_id:
            raise ValueError("Test case project must match the recorder project")

        identity = hashlib.sha256(
            f"{recording.project_id}\0{request.file_path}\0{request.test_name}".encode("utf-8")
        ).hexdigest()[:29]
        case_id = f"tc_rec_{identity}"
        case_data = request.test_case.model_copy(
            update={
                "automation_status": AutomationStatus.AUTOMATED,
                "external_system": "RECORDER",
                "external_case_id": identity,
            }
        )
        existing = await self.test_case_repo.get_by_id(case_id)
        if existing:
            if (
                existing.project_id != recording.project_id
                or existing.external_system != "RECORDER"
                or existing.external_case_id != identity
            ):
                raise FileExistsError("Recorder case identity conflicts with an existing case")
            saved_case = await self.test_case_repo.update(
                case_id,
                TestCaseUpdate.model_validate(case_data.model_dump(exclude={"project_id"})),
            )
            reused = True
        else:
            saved_case = await self.test_case_repo.create(case_data, case_id=case_id)
            reused = False

        nodeid = f"{request.file_path}::{request.test_name}"
        binding = await self.binding_service.bind_test_case(
            AutomationBindingCreate(
                test_case_id=case_id,
                workspace_id=recording.project_id,
                nodeid=nodeid,
                file_path=request.file_path,
                framework=FrameworkType.PLAYWRIGHT_PYTHON,
                status=AutomationBindingStatus.ACTIVE,
            )
        )
        evidence_bundle = self.recorder.element_evidence_bundle(recording)
        evidence_bundle.update(binding_id=binding.id, test_case_id=case_id)
        await self.binding_service.binding_repo.update_recorder_evidence_bundle(case_id, evidence_bundle)
        return {"test_case": saved_case, "binding": binding, "nodeid": nodeid, "reused": reused}

    async def save_api_case(self, session_id: str, owner_id: str, request: RecorderSaveApiCaseRequest) -> dict:
        recording = await self.recorder.get(session_id, owner_id)
        if not recording:
            raise LookupError("Recorder session not found")
        call = next((item for item in self.recorder.api_calls(recording) if item["id"] == request.call_id), None)
        if call is None:
            raise ValueError("Captured API call not found")
        headers = [
            ApiHeader(name=name, value=value)
            for name, value in (call.get("request_headers") or {}).items()
            if value is not None
        ]
        raw_body = call.get("request_body")
        json_body = None
        body = None
        if raw_body:
            try:
                json_body = json.loads(raw_body)
            except ValueError:
                body = raw_body
        compiled = compile_api_case(
            ApiCaseRequest(
                test_name=_api_case_test_name(call["method"], call["url"], request.test_name),
                method=call["method"],
                url=call["url"],
                headers=headers,
                json_body=json_body,
                body=body,
                assertions=[ApiAssertion(kind="status", expected=call.get("status") or 200)],
            )
        )
        file_path = f"tests/{compiled['test_name']}.py"
        await self.workspace_service.write_file(recording.project_id, file_path, compiled["code"])

        identity = hashlib.sha256(
            f"{recording.project_id}\0{file_path}\0{compiled['test_name']}".encode("utf-8")
        ).hexdigest()[:29]
        case_id = f"tc_api_{identity}"
        title = f"API {call['method']} {call['url'].split('?')[0]}"
        model = ModernTestModel(display_id=compiled["test_name"], intent=title)
        existing = await self.test_case_repo.get_by_id(case_id)
        if existing:
            saved_case = await self.test_case_repo.update(
                case_id,
                TestCaseUpdate(title=title, steps=[f"{call['method']} {call['url']}"], test_model=model),
            )
            reused = True
        else:
            saved_case = await self.test_case_repo.create(
                TestCaseCreate(
                    project_id=recording.project_id,
                    title=title,
                    steps=[f"{call['method']} {call['url']}"],
                    test_model=model,
                    automation_status=AutomationStatus.AUTOMATED,
                    external_system="RECORDER_API",
                    external_case_id=identity,
                ),
                case_id=case_id,
            )
            reused = False
        nodeid = f"{file_path}::{compiled['test_name']}"
        binding = await self.binding_service.bind_test_case(
            AutomationBindingCreate(
                test_case_id=case_id,
                workspace_id=recording.project_id,
                nodeid=nodeid,
                file_path=file_path,
                framework=FrameworkType.PLAYWRIGHT_PYTHON,
                status=AutomationBindingStatus.ACTIVE,
            )
        )
        return {
            "test_case": saved_case,
            "binding": binding,
            "file_path": file_path,
            "nodeid": nodeid,
            "reused": reused,
            "code": compiled["code"],
        }


class RecorderSaveApiCaseRequest(BaseModel):
    """Save one captured API call as a pytest API case bound to the recorder project."""

    call_id: str = Field(min_length=1, max_length=64)
    test_name: str | None = Field(default=None, max_length=120)


def _api_case_test_name(method: str, url: str, override: str | None) -> str:
    if override:
        candidate = re.sub(r"\W+", "_", override).strip("_") or "api_case"
    else:
        path = re.sub(r"^https?://[^/]+", "", url).strip("/")
        candidate = "_".join(part for part in re.split(r"[^A-Za-z0-9]+", f"{method}_{path}") if part) or "api_case"
    candidate = candidate.lower()
    if candidate[0].isdigit():
        candidate = "api_" + candidate
    if not candidate.startswith("test_"):
        candidate = "test_" + candidate
    return candidate[:60]
