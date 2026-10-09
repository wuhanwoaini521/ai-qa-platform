from __future__ import annotations

import ast
import re
from pathlib import Path

from project_model.models import FailureRepairWorkflow

ROOT = Path(__file__).resolve().parents[3]


def _python_files(path: Path):
    return path.rglob("*.py")


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_api_routers_do_not_own_persistence_access():
    api_root = ROOT / "apps/api/app/api"
    forbidden_imports = ("app.repositories", "sqlalchemy", "app.persistence.database")
    forbidden_methods = {"execute", "commit", "flush", "add", "delete", "get"}
    violations = []

    for path in _python_files(api_root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        if any(name.startswith(forbidden_imports) for name in _imports(tree)):
            violations.append(f"{path.relative_to(ROOT)} imports persistence directly")
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden_methods:
                if isinstance(node.value, ast.Name) and node.value.id in {"session", "db", "repo", "repository"}:
                    violations.append(f"{path.relative_to(ROOT)} calls persistence method {node.attr}")
                    break
    assert not violations, "\n".join(violations)


def test_runtime_projection_is_read_only():
    source = (ROOT / "apps/api/app/services/runtime_projection.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set(_imports(tree))
    assert not imported.intersection({"sqlalchemy.update", "sqlalchemy.delete", "sqlalchemy.insert"})
    writes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        receiver = node.func.value
        is_session = isinstance(receiver, ast.Name) and receiver.id == "session"
        is_service_session = isinstance(receiver, ast.Attribute) and receiver.attr == "session"
        if (is_session or is_service_session) and node.func.attr in {"commit", "flush", "add", "delete", "merge"}:
            writes.append(node.func.attr)
    assert writes == []


def test_application_services_delegate_persistence_to_repositories():
    service_root = ROOT / "apps/api/app/services"
    query_service = (service_root / "runtime_projection.py").resolve()
    forbidden = {"get", "execute", "scalar", "scalars", "add", "delete", "merge"}
    violations = []
    for path in _python_files(service_root):
        if path.resolve() == query_service:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = node.func.value
            direct_session = isinstance(receiver, ast.Name) and receiver.id in {"session", "db_session"}
            repository_session = isinstance(receiver, ast.Attribute) and receiver.attr == "session"
            if (direct_session or repository_session) and node.func.attr in forbidden:
                violations.append(f"{path.relative_to(ROOT)} calls persistence method {node.func.attr}")
    assert not violations, (
        "RuntimeProjection is the only application query layer allowed to execute direct SQL:\n" + "\n".join(violations)
    )


def test_failure_repair_history_uses_the_workflow_repository_scope():
    service = (ROOT / "apps/api/app/services/failure_workflow_service.py").read_text(encoding="utf-8")
    repository = (ROOT / "apps/api/app/repositories/failure_analysis_repo.py").read_text(encoding="utf-8")
    unit_of_work = (ROOT / "apps/api/app/repositories/task_unit_of_work.py").read_text(encoding="utf-8")
    assert "FailureAnalysisRepository" not in service
    assert "self.history" not in service
    assert "repositories.failure_analyses" in service
    assert "FailureAnalysisRepository(session)" in unit_of_work
    assert "async_session_factory" not in repository
    assert ".commit(" not in repository


def test_failure_application_service_does_not_hold_persistence_models():
    service = (ROOT / "apps/api/app/services/failure_service.py").read_text(encoding="utf-8")
    repository = (ROOT / "apps/api/app/repositories/failure_repo.py").read_text(encoding="utf-8")
    assert "FailureRecordORM" not in service
    assert "orm:" not in service
    assert "database.get_session" not in repository
    assert "await session.commit()" not in repository
    assert "set_committed_value" not in repository


def test_requirement_recovery_updates_state_through_repository_commands():
    service = (ROOT / "apps/api/app/services/requirement_lifecycle_service.py").read_text(encoding="utf-8")
    repository = (ROOT / "apps/api/app/repositories/requirement_repo.py").read_text(encoding="utf-8")
    assert "row.qa_model =" not in service
    assert 'update_qa_model(row["id"], changed)' in service
    assert "async def update_qa_model(" in repository


def test_playwright_lifecycle_is_owned_by_adapter():
    source_roots = [ROOT / "apps/api/app/api", ROOT / "apps/api/app/services"]
    allowed = (ROOT / "apps/api/app/adapters/playwright").resolve()
    violations = []
    for source_root in source_roots:
        for path in _python_files(source_root):
            if path.resolve().is_relative_to(allowed):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for name in _imports(tree):
                if name == "playwright.async_api":
                    violations.append(f"{path.relative_to(ROOT)} imports Playwright directly")
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in {"launch", "new_context", "new_page"}:
                        violations.append(f"{path.relative_to(ROOT)} calls browser lifecycle method {node.func.attr}")
                        break
    assert not violations, "\n".join(violations)


def test_onboarding_pilot_uses_the_canonical_test_run_service():
    source = (ROOT / "apps/api/app/services/onboarding_service.py").read_text(encoding="utf-8")
    assert "QAProjectRunner" not in source
    assert "TestRunRepository" not in source
    assert "self.run_service.create_and_execute_run(" in source
    assert "SafetyPolicy().split(requested, root)" in source


def test_browser_runtime_adapter_is_the_only_application_playwright_dependency():
    source_roots = [ROOT / "apps/api/app/api", ROOT / "apps/api/app/services", ROOT / "apps/api/app/ports"]
    violations = []
    for source_root in source_roots:
        for path in _python_files(source_root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for name in _imports(tree):
                if name.startswith("app.adapters.playwright"):
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not violations, "Playwright adapter imports belong in the composition root:\n" + "\n".join(violations)


def test_browser_executor_delegates_ai_and_jev_provider_calls():
    source = (ROOT / "apps/api/app/services/task_browser_executor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    provider_imports = {
        "qa_core.ai.registry",
        "app.services.decision_service",
    }
    imported = set(_imports(tree))
    assert not imported.intersection(provider_imports)
    provider_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in {"AIProviderRegistry", "DecisionService"}
    }
    assert not provider_names


def test_task_capabilities_depend_on_execution_ports_not_task_runtime_facade():
    service_root = ROOT / "apps/api/app/services"
    violations = []
    for path in service_root.glob("task_*.py"):
        if path.name in {"task_runtime_service.py", "task_execution_ports.py"}:
            continue
        source = path.read_text(encoding="utf-8")
        if "self.runtime" in source:
            violations.append(f"{path.relative_to(ROOT)} still depends on the TaskRuntime facade")
    runtime = (service_root / "task_runtime_service.py").read_text(encoding="utf-8")
    if "TaskBrowserExecutor(self)" in runtime:
        violations.append("TaskRuntimeService injects itself into TaskBrowserExecutor")
    assert not violations, "Task capabilities must use explicit execution ports:\n" + "\n".join(violations)


def test_task_runtime_is_a_composition_root_with_capability_owners():
    service_root = ROOT / "apps/api/app/services"
    runtime = (service_root / "task_runtime_service.py").read_text(encoding="utf-8")
    tree = ast.parse(runtime)
    runtime_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "TaskRuntimeService"
    )
    methods = {node.name for node in runtime_class.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert methods <= {"__init__", "start", "stop"}
    assert "async_session_factory" not in runtime
    assert "TaskORM" not in runtime
    assert "setattr(TaskRuntimeService" not in runtime

    command = (service_root / "task_command_service.py").read_text(encoding="utf-8")
    scheduler = (service_root / "task_scheduler_service.py").read_text(encoding="utf-8")
    execution = (service_root / "task_execution_orchestrator.py").read_text(encoding="utf-8")
    assert "class TaskCommandService" in command and "async def approve(" in command and "async def replan(" in command
    assert "class TaskSchedulerService" in scheduler and "async def _schedule_loop(" in scheduler
    assert "class TaskExecutionOrchestrator" in execution and "async def _execute_step(" in execution


def test_shared_packages_do_not_depend_on_application_or_web():
    roots = [ROOT / "packages/project-model/project_model", ROOT / "packages/qa-core/qa_core"]
    violations = []
    for source_root in roots:
        for path in _python_files(source_root):
            for name in _imports(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
                if name.startswith("app.api") or name.startswith("apps.web"):
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not violations, "\n".join(violations)


def test_failure_repair_typescript_contract_matches_pydantic_dto():
    schema_fields = set(FailureRepairWorkflow.model_json_schema()["properties"])
    typescript = (ROOT / "apps/web/src/types/index.ts").read_text(encoding="utf-8")
    match = re.search(r"export interface FailureRepairWorkflow\s*\{([^}]+)\}", typescript)
    assert match, "FailureRepairWorkflow TypeScript interface is missing"
    typescript_fields = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*):", match.group(1), re.MULTILINE))
    assert typescript_fields == schema_fields
    definitions = FailureRepairWorkflow.model_json_schema()["$defs"]
    for type_name in ("FailureRepairState", "FailureRepairAction"):
        values = set(definitions[type_name]["enum"])
        match = re.search(rf"export type {type_name}\s*=([^;]+);", typescript, re.DOTALL)
        assert match, f"{type_name} TypeScript union is missing"
        typescript_values = set(re.findall(r"'([^']+)'", match.group(1)))
        assert typescript_values == values, (
            f"{type_name} values differ: Python={values}, TypeScript={typescript_values}"
        )


def test_failure_page_renders_backend_owned_workflow_state_and_actions():
    source = (ROOT / "apps/web/src/pages/FailuresPage.tsx").read_text(encoding="utf-8")
    forbidden_helpers = ("deriveDiagnosisState", "trustedDiagnosis", "primaryActionFor(")
    assert not [helper for helper in forbidden_helpers if helper in source]
    assert "repairWorkflow?.state" in source
    assert "repairWorkflow?.allowed_actions" in source
    assert "startFailureRetry" in source
    assert "createTestRun(" not in source


def test_web_is_not_imported_by_backend_or_shared_core():
    roots = [ROOT / "apps/api/app", ROOT / "apps/worker", ROOT / "packages/qa-core/qa_core"]
    violations = []
    for source_root in roots:
        for path in _python_files(source_root):
            for name in _imports(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
                if name.startswith("apps.web") or name.startswith("apps.web."):
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not violations, "\n".join(violations)


def test_task_application_services_delegate_database_access_to_repositories():
    service_root = ROOT / "apps/api/app/services"
    forbidden = {"execute", "get", "scalar", "scalars", "add", "delete"}
    repository_reads = {"get", "get_by_id", "get_step", "get_steps", "steps_for_task", "get_steps_for_tasks"}
    violations = []
    for path in service_root.glob("task_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        repository_values = set()
        repository_collections = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.repositories.task_unit_of_work":
                violations.append(f"{path.relative_to(ROOT)} imports a SQLAlchemy UoW adapter directly")
            if isinstance(node, ast.ImportFrom) and node.module == "app.persistence.models":
                imported = {alias.name for alias in node.names}
                if imported & {"TaskORM", "TaskStepORM"}:
                    violations.append(f"{path.relative_to(ROOT)} imports SQLAlchemy task models")
            if isinstance(node, ast.Assign | ast.AnnAssign):
                value = node.value
                call = value.value if isinstance(value, ast.Await) else value
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr in repository_reads
                ):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            repository_values.add(target.id)
                            if call.func.attr in {"get_steps", "steps_for_task", "get_steps_for_tasks"}:
                                repository_collections.add(target.id)
        for node in ast.walk(tree):
            if isinstance(node, ast.For) and isinstance(node.iter, ast.Name) and node.iter.id in repository_collections:
                if isinstance(node.target, ast.Name):
                    repository_values.add(node.target.id)
            if isinstance(node, ast.AugAssign):
                targets = [node.target]
            elif isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id in repository_values
                ):
                    violations.append(
                        f"{path.relative_to(ROOT)} writes repository model field {target.value.id}.{target.attr} directly"
                    )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = node.func.value
            if (
                isinstance(receiver, ast.Name)
                and receiver.id in {"session", "db_session"}
                and node.func.attr in forbidden
            ):
                violations.append(f"{path.relative_to(ROOT)} calls session.{node.func.attr} directly")
    assert not violations, "\n".join(violations)
