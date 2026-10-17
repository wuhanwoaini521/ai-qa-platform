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
from app.services.ai_runtime import build_ai_orchestrator
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
        test_case = await self.test_case_repo.get_by_id(data.test_case_id)
        if test_case is None:
            raise ValueError("Test case not found")
        workspace = await self.workspace_repo.get_by_id(data.workspace_id)
        if workspace is None:
            workspace = await self.workspace_repo.get_by_project_id(data.workspace_id)
        if workspace is None or workspace.project_id != test_case.project_id:
            raise ValueError("Workspace does not belong to the test case project")
        data = data.model_copy(update={"workspace_id": workspace.project_id})
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

    async def generate_automation_draft(
        self, test_case_id: str, *, idempotency_key: str | None = None
    ) -> tuple[AutomationBinding, str]:
        """Generates a test automation draft from TestCase and creates a draft binding."""
        test_case = await self.test_case_repo.get_by_id(test_case_id)
        if not test_case:
            raise ValueError(f"Test case not found: {test_case_id}")

        workspace = await self.workspace_repo.get_by_project_id(test_case.project_id)
        if not workspace:
            raise ValueError(f"No workspace initialized for project: {test_case.project_id}")

        # Use the existing governed provider and project context instead of a demo template.
        import ast
        import hashlib
        from uuid import uuid4

        from qa_core.ai.context import ContextSelector

        # Filesystem workspaces use the project key, not WorkspaceORM's separate row ID.
        workspace_key = test_case.project_id
        root = self.workspace_service.get_workspace_dir(workspace_key)
        bundle = ContextSelector().select(root, query=test_case.title)
        key_digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16] if idempotency_key else None
        default_path = (
            f"tests/test_case_{test_case.id.replace('-', '')[:12]}_qd_{key_digest}.py"
            if key_digest
            else f"tests/test_case_{test_case.id.replace('-', '')[:12]}_{uuid4().hex[:6]}.py"
        )
        action_marker = f"# Quality Discovery action: {key_digest}" if key_digest else None
        code_content = None
        if key_digest:
            try:
                existing_content = await self.workspace_service.read_file(workspace_key, default_path)
            except FileNotFoundError:
                pass
            else:
                if action_marker not in existing_content.splitlines():
                    raise FileExistsError("The deterministic automation draft path is already occupied.")
                code_content = existing_content

        if code_content is None:
            await trace_progress("context.loaded", "用例、工作区与项目上下文已加载")
            await trace_progress("model.started", "生成自动化草稿")
            result = await build_ai_orchestrator().assist_code_chat(
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
                raise ValueError(
                    "No grounded real-AI draft is available. Inspect evidence and provider status in Studio."
                )
            code_content = result.suggested_code
            if action_marker:
                code_content = f"{code_content.rstrip()}\n\n{action_marker}\n"

        def validated_functions(source: str) -> list[str]:
            tree = ast.parse(source)
            functions = [
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            ]
            if not functions or not any(
                isinstance(node, ast.Assert)
                or isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr.startswith(("assert", "to_have", "to_be"))
                for node in ast.walk(tree)
            ):
                raise ValueError("AI draft contains no test function or meaningful assertion.")
            return functions

        await trace_progress("validation.started", "校验测试语法与断言")
        functions = validated_functions(code_content)
        # New drafts never overwrite a current file. DRAFT remains distinct from validated automation.
        await trace_progress("validation.completed", "语法与断言校验完成")
        file_rel_path = default_path
        if key_digest:
            try:
                await self.workspace_service.write_file_if_unchanged(
                    workspace_key, file_rel_path, code_content, expected_exists=False, expected_sha256=None
                )
            except FileExistsError:
                # A concurrent retry may have written this same action's draft first.
                existing_content = await self.workspace_service.read_file(workspace_key, file_rel_path)
                if action_marker not in existing_content.splitlines():
                    raise
                code_content = existing_content
                functions = validated_functions(code_content)
        else:
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
