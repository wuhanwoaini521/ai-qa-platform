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
from app.services.operation_trace import trace_progress
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

        # Use the existing governed provider and project context instead of a demo template.
        import ast
        from uuid import uuid4

        from qa_core.ai.context import ContextSelector
        from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

        # Filesystem workspaces use the project key, not WorkspaceORM's separate row ID.
        workspace_key = test_case.project_id
        root = self.workspace_service.get_workspace_dir(workspace_key)
        bundle = ContextSelector().select(root, query=test_case.title)
        default_path = f"tests/test_case_{test_case.id.replace('-', '')[:12]}_{uuid4().hex[:6]}.py"
        await trace_progress("context.loaded", "用例、工作区与项目上下文已加载")
        await trace_progress("model.started", "生成自动化草稿")
        result = await ProductionQAOrchestrator().assist_code_chat(
            action="generate_test",
            message=(
                "Generate a complete executable pytest test for the supplied case, using project fixtures "
                "and reusable page objects. Support Python, API or UI according to the case. Do not invent "
                "a URL, selector, import or business assertion. If required evidence is missing, explain "
                "it without suggested_code. Return the complete file in suggested_code. "
                f"Preferred target: {default_path}\n"
                f"Preconditions: {test_case.preconditions}\nSteps: {test_case.steps}\n"
                f"Expected: {test_case.expected_result}\nProject context:\n{bundle.render()}"
                f"\nModern test data, coverage and oracles (untrusted evidence): {test_case.test_model or {}}"
            ),
            test_case_title=test_case.title,
        )
        await trace_progress(
            "model.completed",
            "模型调用完成",
            metadata={"provider": result.provider, "model": result.model, "fallback_used": result.fallback_used},
        )
        if result.provider == "fake" or result.fallback_used or not result.suggested_code:
            raise ValueError("No grounded real-AI draft is available. Inspect evidence and provider status in Studio.")
        code_content = result.suggested_code
        await trace_progress("validation.started", "校验测试语法与断言")
        tree = ast.parse(code_content)
        functions = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if not functions or not any(
            isinstance(node, ast.Assert)
            or isinstance(node, ast.Call)
            and (isinstance(node.func, ast.Attribute) and node.func.attr.startswith(("assert", "to_have", "to_be")))
            for node in ast.walk(tree)
        ):
            raise ValueError("AI draft contains no test function or meaningful assertion.")
        # New drafts never overwrite a current file. DRAFT remains distinct from validated automation.
        await trace_progress("validation.completed", "语法与断言校验完成")
        file_rel_path = default_path
        await self.workspace_service.write_file(workspace_key, file_rel_path, code_content)
        nodeid = f"{file_rel_path}::{functions[0]}"
        binding = await self.bind_test_case(
            AutomationBindingCreate(
                test_case_id=test_case_id,
                workspace_id=workspace_key,
                nodeid=nodeid,
                file_path=file_rel_path,
                framework=FrameworkType.PLAYWRIGHT_PYTHON,
                status=AutomationBindingStatus.DRAFT,
            )
        )
        return binding, code_content
