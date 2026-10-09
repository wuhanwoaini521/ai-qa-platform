from __future__ import annotations

import ast
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

from project_model.task_models import EvidenceType, TaskType
from qa_core.ai.context import ContextSelector

from app.domain.task_records import TaskRecord as TaskExecutionRecord
from app.services.task_approval import approval_granted
from app.services.task_errors import ApprovalRequired, TaskBlocked
from app.services.task_execution_ports import TaskExecutionPorts
from app.services.workspace_service import WorkspaceService


class TaskCodeGenerationService:
    """Own task source inspection, generation, validation, review and approved writes."""

    def __init__(self, context: TaskExecutionPorts) -> None:
        self.context = context

    async def _inspect_source(
        self, task: TaskExecutionRecord, outputs: dict[str, Any], path: str | None = None
    ) -> dict[str, Any]:
        file_path = path or str(self.context.input(task, "file_path", ""))
        if not file_path:
            raise TaskBlocked("This task requires a workspace-relative file_path.")
        service = WorkspaceService()
        content = await service.read_file(task.workspace_id or "", file_path)
        if len(content) > 60000:
            raise TaskBlocked("Source file exceeds the review context limit (60,000 characters).")
        tree = ast.parse(content, filename=file_path)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        return {
            "file_path": file_path,
            "source": content,
            "functions": functions,
            "_evidence": [
                await self.context.evidence(
                    task,
                    "inspect",
                    EvidenceType.SOURCE_CODE,
                    "workspace.read_file",
                    f"Read {file_path} ({len(content)} characters; {len(functions)} functions).",
                    content,
                    {"file_path": file_path, "functions": functions},
                )
            ],
        }

    async def _review_source(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        source_info = outputs.get("inspect") or outputs.get("inspect_source") or outputs.get("inspect_failure", {})
        source = source_info.get("source", "")
        path = source_info.get("file_path", self.context.input(task, "file_path", ""))
        if not source:
            raise TaskBlocked("Source review requires a completed source inspection step.")
        tree = ast.parse(source, filename=path or "source.py")
        findings: list[dict[str, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant) and node.test.value is True:
                findings.append(
                    {
                        "severity": "HIGH",
                        "code": "ASSERT_ALWAYS_TRUE",
                        "line": str(node.lineno),
                        "message": "Assertion always passes.",
                    }
                )
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if name == "sleep":
                    findings.append(
                        {
                            "severity": "MEDIUM",
                            "code": "FIXED_SLEEP",
                            "line": str(node.lineno),
                            "message": "Fixed sleeps increase test flakiness; wait for a specific condition.",
                        }
                    )
                if (
                    name == "locator"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    selector = node.args[0].value
                    if selector.startswith("//") or selector.startswith("xpath="):
                        findings.append(
                            {
                                "severity": "MEDIUM",
                                "code": "FRAGILE_XPATH",
                                "line": str(node.lineno),
                                "message": "XPath locator may be structurally fragile.",
                            }
                        )
        tests = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if not tests:
            findings.append(
                {
                    "severity": "HIGH",
                    "code": "NO_TEST_FUNCTION",
                    "line": "1",
                    "message": "No pytest test function was found.",
                }
            )
        result = {
            "file_path": path,
            "findings": findings,
            "test_functions": [test.name for test in tests],
            "locators": sum(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "locator"
                for node in ast.walk(tree)
            ),
            "waits": sum(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"wait_for", "wait_for_timeout", "wait_for_selector"}
                for node in ast.walk(tree)
            ),
            "assertions": sum(
                isinstance(node, ast.Assert)
                or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "assert")
                for node in ast.walk(tree)
            ),
        }
        result["_evidence"] = [
            await self.context.evidence(
                task,
                "review",
                EvidenceType.ANALYSIS,
                "python.ast",
                f"Static review found {len(findings)} issue(s) in {path}.",
                json.dumps(result, ensure_ascii=False),
                result,
            )
        ]
        return result

    async def _review_report(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        review = outputs.get("review", {})
        browser = outputs.get("browser", {})
        findings = review.get("findings", [])
        return {
            "file_path": review.get("file_path"),
            "findings": findings,
            "finding_count": len(findings),
            "metrics": review.get("metrics", {}),
            "browser_observation": browser or None,
            "evidence_backed": bool(review.get("findings") is not None),
        }

    async def _generate_test(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        recorded_steps = self.context.input(task, "recorded_steps")
        default_name = str(self.context.input(task, "test_name", "test_goal_flow"))
        file_path = str(self.context.input(task, "file_path", f"tests/{default_name}.py"))
        case_bindings: list[dict[str, str]] = []
        if task.type == TaskType.QA_GOAL.value and self.context.input(task, "requirement_id"):
            case_ids = (outputs.get("coverage") or {}).get("unbound_case_ids", [])
            if len(case_ids) > 20:
                raise TaskBlocked("Automation generation is limited to 20 uncovered cases per goal.")
            async with self.context.repository_scope() as repositories:
                cases = await repositories.test_cases.list_by_ids(
                    case_ids,
                    project_id=task.project_id or "",
                    requirement_id=self.context.input(task, "requirement_id"),
                )
            by_id = {case.id: case for case in cases}
            case_bindings = [
                {
                    "case_id": case_id,
                    "test_name": f"test_case_{case_id.replace('-', '_')}",
                    "title": by_id[case_id].title,
                    "preconditions": by_id[case_id].preconditions,
                    "steps": by_id[case_id].steps,
                    "expected_result": by_id[case_id].expected_result,
                }
                for case_id in case_ids
                if case_id in by_id
            ]
            if case_ids and len(case_bindings) != len(case_ids):
                raise TaskBlocked("One or more uncovered cases no longer belong to the selected requirement.")
            if not case_bindings:
                raise TaskBlocked("No uncovered cases remain; automation generation was skipped safely.")
            file_path = f"tests/test_qa_goal_{task.id[:8]}.py"
        if recorded_steps:
            from app.services.recorder_service import RecorderGenerateRequest, RecorderStep, generate_python_case

            request = RecorderGenerateRequest(
                case_name=str(self.context.input(task, "case_name", task.goal[:120])),
                file_path=file_path,
                test_name=default_name,
                steps=[RecorderStep.model_validate(step) for step in recorded_steps],
            )
            code = generate_python_case(request)
            source = {"suggested_code": code, "target_file": file_path, "action_type": "generated_from_recording"}
        else:
            page = outputs.get("inspect", {})
            bundle = ContextSelector().select(WorkspaceService().get_workspace_dir(task.workspace_id), query=task.goal)
            case_instruction = (
                "Generate exactly one top-level pytest test for each listed case, named exactly as provided. Preserve each case's expected result; do not skip, xfail, weaken assertions, or add unrelated tests.\n"
                f"Cases: {json.dumps(case_bindings, ensure_ascii=False)}\n"
                if case_bindings
                else ""
            )
            prompt = (
                "Create one complete pytest test for this QA goal, choosing Python, API or Playwright based on the goal and project fixtures. Use only the observed page details, "
                "goal, requirement and supplied acceptance criteria. Do not invent selectors or APIs. "
                "Return the complete Python test file in suggested_code and a workspace-relative tests/*.py target_file.\n"
                f"{case_instruction}"
                f"Goal: {task.goal}\nRequirement: {self.context.input(task, 'requirement', '')}\n"
                f"Existing case: {json.dumps(self.context.input(task, 'case_context', {}), ensure_ascii=False)}\n"
                f"Acceptance criteria: {json.dumps(self.context.input(task, 'acceptance_criteria', []), ensure_ascii=False)}\n"
                f"Observed page: {json.dumps({k: page.get(k) for k in ('url', 'title', 'accessibility_tree', 'candidates')}, ensure_ascii=False)[:18000]}"
                f"\nRepository conventions, fixtures and reusable page objects:\n{bundle.render()}"
            )
            source = (await self.context.call_code_ai(task, prompt)).model_dump()
            file_path = file_path if case_bindings else source.get("target_file") or file_path
        code = str(source.get("suggested_code", ""))
        self._validate_python_test(code, file_path)
        if case_bindings:
            names = {
                node.name
                for node in ast.parse(code).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            }
            expected = {item["test_name"] for item in case_bindings}
            if names != expected:
                raise TaskBlocked("Generated automation must contain exactly one named test for each uncovered case.")
            self._validate_goal_generated_test(code, file_path)
        artifact = await self.context.artifact(
            task, "generate", Path(file_path).name, "GENERATED_TEST", code.encode("utf-8"), "text/x-python"
        )
        return {
            "target_file": file_path,
            "suggested_code": code,
            "action_type": source.get("action_type", "ai_generated"),
            "case_bindings": case_bindings,
            "artifact_id": artifact["artifact_id"],
            "_artifacts": [artifact],
            "_evidence": [
                await self.context.evidence(
                    task,
                    "generate",
                    EvidenceType.SOURCE_CODE,
                    "recorder.generate" if recorded_steps else "ai.code_assistant",
                    f"Generated test source for {task.goal!r}.",
                    code,
                    {
                        "target_file": file_path,
                        "provider": "recorder" if recorded_steps else source.get("provider", "unknown"),
                    },
                    artifact["artifact_id"],
                )
            ],
        }

    @staticmethod
    def _validate_goal_generated_test(code: str, file_path: str) -> None:
        tree = ast.parse(code, filename=file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant) and node.test.value is True:
                raise TaskBlocked("QA Goal tests may not pass through a constant-true assertion.")
            if (
                isinstance(node, ast.ExceptHandler)
                and node.body
                and all(isinstance(item, ast.Pass) for item in node.body)
            ):
                raise TaskBlocked("QA Goal tests may not swallow exceptions with a pass-only handler.")
            if isinstance(node, ast.Call):
                func = node.func
                called = (
                    f"{func.value.id}.{func.attr}"
                    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                if called in {"pytest.skip", "pytest.xfail", "pytest.importorskip"}:
                    raise TaskBlocked("QA Goal tests may not skip or xfail a requested scenario.")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for decorator in node.decorator_list:
                    target = decorator.func if isinstance(decorator, ast.Call) else decorator
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Attribute)
                        and isinstance(target.value.value, ast.Name)
                        and target.value.value.id == "pytest"
                        and target.value.attr == "mark"
                        and target.attr in {"skip", "skipif", "xfail"}
                    ):
                        raise TaskBlocked("QA Goal tests may not mark a requested scenario skipped or xfailed.")

    @staticmethod
    def _validate_python_test(code: str, file_path: str) -> None:
        path = Path(file_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.suffix != ".py"
            or not file_path.replace("\\", "/").startswith("tests/")
        ):
            raise TaskBlocked("Generated test path must stay under the workspace tests/ directory.")
        tree = ast.parse(code, filename=file_path)
        test_functions = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if not test_functions:
            raise TaskBlocked("Generated source contains no top-level pytest test function.")
        forbidden_imports = {
            "subprocess",
            "socket",
            "ctypes",
            "winreg",
            "sys",
            "pathlib",
            "shutil",
            "tempfile",
            "importlib",
            "multiprocessing",
            "threading",
            "http",
            "requests",
            "httpx",
            "ftplib",
            "telnetlib",
            "ssl",
            "builtins",
        }
        allowed_environment_variables = {
            "PLAYWRIGHT_CHANNEL",
            "BROWSER_PROXY_URL",
            "HTTPS_PROXY",
            "https_proxy",
            "HTTP_PROXY",
            "http_proxy",
            "BROWSER_PROXY_BYPASS",
            "NO_PROXY",
            "no_proxy",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "urllib" for alias in node.names):
                if any(alias.name != "urllib.parse" for alias in node.names):
                    raise TaskBlocked(
                        "Generated test imports a process/network/system-control module; refusing execution."
                    )
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "urllib":
                safe_url_parser = (
                    node.level == 0
                    and node.module == "urllib.parse"
                    and all(alias.name in {"unquote", "urlsplit"} and alias.asname is None for alias in node.names)
                )
                if not safe_url_parser:
                    raise TaskBlocked(
                        "Generated test imports a process/network/system-control module; refusing execution."
                    )
            if isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] in forbidden_imports for alias in node.names
            ):
                raise TaskBlocked("Generated test imports a process/network/system-control module; refusing execution.")
            if isinstance(node, ast.Import) and any(
                alias.name != "os" for alias in node.names if alias.name.split(".")[0] == "os"
            ):
                raise TaskBlocked("Generated test may use os.getenv only; refusing other operating-system imports.")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in forbidden_imports:
                raise TaskBlocked("Generated test imports a process/network/system-control module; refusing execution.")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "os":
                raise TaskBlocked("Generated test may use os.getenv only; refusing other operating-system imports.")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id
                in {
                    "eval",
                    "exec",
                    "compile",
                    "open",
                    "__import__",
                    "breakpoint",
                    "input",
                    "getattr",
                    "setattr",
                    "delattr",
                    "vars",
                    "globals",
                    "locals",
                }
            ):
                raise TaskBlocked(
                    "Generated test uses a prohibited dynamic-code or system-access operation; refusing execution."
                )
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise TaskBlocked("Generated test accesses Python internals; refusing execution.")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise TaskBlocked("Generated test accesses Python internals; refusing execution.")
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id
                in {
                    "__builtins__",
                    "globals",
                    "locals",
                }
            ):
                raise TaskBlocked("Generated test accesses Python internals; refusing execution.")
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr != "getenv"
            ):
                raise TaskBlocked("Generated test may only read approved browser environment settings.")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
            ):
                args = node.args
                if (
                    node.func.attr != "getenv"
                    or not args
                    or not isinstance(args[0], ast.Constant)
                    or args[0].value not in allowed_environment_variables
                ):
                    raise TaskBlocked("Generated test may only read approved browser environment settings.")

    async def _validate_generated(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        source = outputs.get("generate") or outputs.get("refactor") or outputs.get("repair", {})
        code, file_path = source.get("suggested_code", ""), source.get("target_file", source.get("file_path", ""))
        self._validate_python_test(code, file_path)
        if task.type == TaskType.QA_GOAL.value:
            self._validate_goal_generated_test(code, file_path)
        return {
            "valid": True,
            "file_path": file_path,
            "line_count": len(code.splitlines()),
            "_evidence": [
                await self.context.evidence(
                    task,
                    "validate",
                    EvidenceType.ANALYSIS,
                    "ast.parse + task source policy",
                    f"{file_path} parses and passed static generated-code policy checks.",
                    json.dumps({"file_path": file_path, "line_count": len(code.splitlines())}),
                    {"valid": True},
                )
            ],
        }

    async def _request_approval(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        repair_branch = False
        if task.current_step_id:
            async with self.context.repository_scope() as repositories:
                current_step = await repositories.tasks.get_step(task.current_step_id)
                repair_branch = bool(current_step and current_step.key.startswith("repair_"))
        change = (
            outputs.get("repair", {})
            if repair_branch
            else outputs.get("generate") or outputs.get("refactor") or outputs.get("repair", {})
        )
        path = change.get("target_file", change.get("file_path"))
        if not path:
            raise TaskBlocked("No source proposal is available for approval.")
        try:
            original = await WorkspaceService().read_file(task.workspace_id or "", path)
        except FileNotFoundError:
            original = None
        expected = change.get("old_code", outputs.get("inspect", {}).get("source", original))
        if original != expected:
            raise TaskBlocked("Source changed after the proposal was prepared. Replan before approval.")
        updated = str(change.get("suggested_code", change.get("new_code", "")))
        diff = "".join(
            difflib.unified_diff(
                (original or "").splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{path}" if original is not None else "/dev/null",
                tofile=f"b/{path}",
            )
        )
        if not diff:
            raise TaskBlocked("The proposal contains no source changes.")
        artifact = await self.context.artifact(
            task, "approval", Path(path).name + ".diff", "PATCH_PROPOSAL", diff.encode(), "text/x-diff"
        )
        summary = {
            "file_path": path,
            "change_kind": task.type,
            "preview": diff[:12000],
            "preview_truncated": len(diff) > 12000,
            "artifact_id": artifact["artifact_id"],
            "base_exists": original is not None,
            "base_sha256": hashlib.sha256(original.encode()).hexdigest() if original is not None else None,
        }
        async with self.context.repository_scope() as repositories:
            repo = repositories.tasks
            row = await repo.get(task.id)
            if row:
                await repo.update_context(task.id, pending_change_summary=summary)
                await self.context.persist_artifact(repositories.evidence, task.id, task.current_step_id, artifact)
                await repo.add_event(task.id, "step.progress", {"type": "approval.requested", **summary})
                await repositories.commit()
        raise ApprovalRequired()

    async def _write_approved_source(
        self, task: TaskExecutionRecord, outputs: dict[str, Any], path: str, code: str
    ) -> None:
        if not approval_granted(outputs):
            raise TaskBlocked("Source cannot be applied without explicit approval.")
        async with self.context.repository_scope() as repositories:
            row = await repositories.tasks.get(task.id)
            summary = (row.context or {}).get("pending_change_summary", {}) if row else {}
        if summary.get("file_path") != path or "base_exists" not in summary:
            raise TaskBlocked("Approval has no source baseline. Replan and review the Diff.")
        try:
            await WorkspaceService().write_file_if_unchanged(
                task.workspace_id or "", path, code, summary["base_exists"], summary.get("base_sha256")
            )
        except FileExistsError as exc:
            raise TaskBlocked(
                "Source changed while awaiting approval. Existing edits were preserved; replan and review a new Diff."
            ) from exc

    async def _write_generated(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        change = outputs.get("generate") or outputs.get("refactor")
        if not change:
            raise TaskBlocked("No approved generated source is available.")
        await self._write_approved_source(task, outputs, change["target_file"], change["suggested_code"])
        return {
            "written": True,
            "file_path": change["target_file"],
            "characters": len(change["suggested_code"]),
            "_evidence": [
                await self.context.evidence(
                    task,
                    "write",
                    EvidenceType.SOURCE_CODE,
                    "workspace.write_file",
                    f"Approved source written to {change['target_file']}.",
                    change["suggested_code"],
                    {"approved": True, "file_path": change["target_file"]},
                )
            ],
        }

    async def _generate_refactor(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        current = outputs.get("inspect", {})
        path, source = current.get("file_path"), current.get("source", "")
        review = outputs.get("review", {})
        supplied_code = self.context.input(task, "proposed_code")
        if supplied_code:
            updated = str(supplied_code)
            proposal_source = "user-provided-refactor"
        else:
            result = await self.context.call_code_ai(
                task,
                "Propose a focused refactor for this test file. Preserve test intent and public fixtures. "
                "Address only evidence-backed review findings. Return the complete replacement Python test module.\n"
                f"Goal: {task.goal}\nFindings: {json.dumps(review.get('findings', []), ensure_ascii=False)}\n"
                f"Path: {path}\nCurrent source:\n{source}",
            )
            updated = result.suggested_code or ""
            proposal_source = "ai.code_assistant"
        self._validate_python_test(updated, path)
        artifact = await self.context.artifact(
            task, "refactor", Path(path).name, "PATCH_PROPOSAL", updated.encode(), "text/x-python"
        )
        return {
            "target_file": path,
            "suggested_code": updated,
            "artifact_id": artifact["artifact_id"],
            "_artifacts": [artifact],
            "_evidence": [
                await self.context.evidence(
                    task,
                    "refactor",
                    EvidenceType.SOURCE_CODE,
                    proposal_source,
                    "Proposed full-file refactor, not yet applied.",
                    updated,
                    {"based_on_findings": review.get("findings", []), "proposal_source": proposal_source},
                    artifact["artifact_id"],
                )
            ],
        }
