from __future__ import annotations

from project_model.models import (
    AutomationBinding,
    AutomationBindingCreate,
    AutomationBindingStatus,
    AutomationStatus,
    FrameworkType,
    TestCaseUpdate,
)

from app.persistence.models import AutomationBindingORM
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.workspace_service import WorkspaceService


class AutomationBindingService:
    def __init__(
        self,
        binding_repo: AutomationBindingRepository,
        test_case_repo: TestCaseRepository,
        workspace_repo: WorkspaceRepository,
        workspace_service: WorkspaceService,
    ) -> None:
        self.binding_repo = binding_repo
        self.test_case_repo = test_case_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service

    def _to_dto(self, orm: AutomationBindingORM) -> AutomationBinding:
        return AutomationBinding(
            id=orm.id,
            test_case_id=orm.test_case_id,
            workspace_id=orm.workspace_id,
            nodeid=orm.nodeid,
            file_path=orm.file_path,
            framework=FrameworkType(orm.framework),
            status=AutomationBindingStatus(orm.status),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def get_binding(self, test_case_id: str) -> AutomationBinding | None:
        orm = await self.binding_repo.get_by_test_case_id(test_case_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def bind_test_case(self, data: AutomationBindingCreate) -> AutomationBinding:
        orm = await self.binding_repo.create_or_update(data)
        # Also update TestCase automation status
        auto_status = (
            AutomationStatus.AUTOMATED if data.status == AutomationBindingStatus.ACTIVE else AutomationStatus.DRAFT
        )
        await self.test_case_repo.update(
            data.test_case_id,
            TestCaseUpdate(automation_status=auto_status),
        )
        return self._to_dto(orm)

    async def unbind_test_case(self, test_case_id: str) -> bool:
        success = await self.binding_repo.delete_by_test_case_id(test_case_id)
        if success:
            await self.test_case_repo.update(
                test_case_id,
                TestCaseUpdate(automation_status=AutomationStatus.MANUAL),
            )
        return success

    async def generate_automation_draft(self, test_case_id: str) -> tuple[AutomationBinding, str]:
        """Generates a test automation draft from TestCase and creates a draft binding."""
        test_case = await self.test_case_repo.get_by_id(test_case_id)
        if not test_case:
            raise ValueError(f"Test case not found: {test_case_id}")

        workspace = await self.workspace_repo.get_by_project_id(test_case.project_id)
        if not workspace:
            raise ValueError(f"No workspace initialized for project: {test_case.project_id}")

        # Construct clean function & file names
        slug = test_case.title.lower().replace(" ", "_").replace("-", "_")
        slug = "".join(c for c in slug if c.isalnum() or c == "_")[:40].strip("_")
        func_name = f"test_{slug}"
        file_rel_path = f"tests/test_{slug}.py"

        steps_comment = "\n    ".join(f"# {i + 1}. {step}" for i, step in enumerate(test_case.steps))
        code_content = f'''import pytest
from playwright.sync_api import Page, expect

@pytest.mark.ui
def {func_name}(page: Page):
    """
    Test Case: {test_case.title}
    Preconditions: {test_case.preconditions or "None"}
    """
    # Steps:
    {steps_comment or "# No explicit steps recorded."}

    page.goto("/")
    # Expected Result: {test_case.expected_result or "Verify expected business condition"}
    expect(page).to_have_title(r".*")
'''
        # Write to workspace
        await self.workspace_service.write_file(workspace.id, file_rel_path, code_content)

        # Create binding
        nodeid = f"{file_rel_path}::{func_name}"
        binding = await self.bind_test_case(
            AutomationBindingCreate(
                test_case_id=test_case_id,
                workspace_id=workspace.id,
                nodeid=nodeid,
                file_path=file_rel_path,
                framework=FrameworkType.PLAYWRIGHT_PYTHON,
                status=AutomationBindingStatus.DRAFT,
            )
        )
        return binding, code_content
