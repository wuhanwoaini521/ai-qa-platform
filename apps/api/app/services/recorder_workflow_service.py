from __future__ import annotations

import hashlib

from project_model.models import (
    AutomationBindingCreate,
    AutomationBindingStatus,
    AutomationStatus,
    FrameworkType,
    TestCaseUpdate,
)

from app.repositories.project_repo import ProjectRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services.automation_binding_service import AutomationBindingService
from app.services.recorder_service import BrowserRecorderService, RecorderSaveCaseRequest, RecorderSessionCreate


class RecorderWorkflowService:
    """Application use cases that coordinate recorder state and project persistence."""

    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        test_case_repo: TestCaseRepository,
        binding_service: AutomationBindingService,
        recorder: BrowserRecorderService,
    ) -> None:
        self.project_repo = project_repo
        self.test_case_repo = test_case_repo
        self.binding_service = binding_service
        self.recorder = recorder

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
