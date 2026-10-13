from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.api.runs import open_run_service
from app.container import get_task_runtime_service
from app.persistence.models import TaskORM, TaskStepORM
from app.repositories.task_repo import TaskRepository
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.task_code_generation_service import TaskCodeGenerationService
from app.services.task_errors import TaskBlocked
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_workflows import build_plan, build_qa_goal_plan, parse_qa_goal
from app.settings import settings
from project_model.task_models import TaskStatus, TaskStepStatus, TaskType

pytestmark = pytest.mark.integration

task_runtime_service = get_task_runtime_service()
task_command_service = task_runtime_service.commands
task_execution_service = task_runtime_service.execution
task_scheduler_service = task_runtime_service.scheduler


@pytest.mark.asyncio
async def test_task_creation_uses_runtime_loaded_ai_call_limit(client, monkeypatch):
    from qa_core.ai.registry import AIProviderRegistry

    monkeypatch.setattr(AIProviderRegistry, "_runtime_config", {"max_task_calls": "3"})
    response = await client.post(
        "/api/tasks",
        json={
            "type": "EXPLORE_PAGE",
            "goal": "Explore the checkout page safely",
            "inputs": {"url": "https://example.com/checkout"},
            "max_ai_calls": 50,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["max_ai_calls"] == 3


@pytest.mark.asyncio
async def test_agent_goal_child_run_preserves_browser_environment_and_worker_configuration(monkeypatch):
    captured = []

    class CapturedRun(Exception):
        pass

    class RunService:
        async def create_and_execute_run(self, run_data, **_kwargs):
            captured.append(run_data)
            raise CapturedRun

    @asynccontextmanager
    async def open_service():
        yield RunService()

    monkeypatch.setattr("app.container.open_run_service", open_service)
    task = SimpleNamespace(
        id="task-context",
        project_id="project-context",
        workspace_id="project-context",
        owner_id="qa-engineer",
        type=TaskType.QA_GOAL.value,
        max_duration_seconds=60,
        inputs={
            "browser": "firefox",
            "environment": {"QA_ENVIRONMENT": "production"},
            "region": "EU",
            "parallel_workers": 3,
        },
    )

    with pytest.raises(CapturedRun):
        await TaskRuntimeService(
            repository_scope=TaskRepositoryScopeFactory()
        ).execution.test_execution._execute_pytest(task, ["tests/test_checkout.py::test_checkout"])

    assert len(captured) == 1
    assert captured[0].browser == "firefox"
    assert captured[0].environment == {"QA_ENVIRONMENT": "production", "QA_REGION": "EU"}
    assert captured[0].parallel_workers == 3


@pytest.mark.parametrize("task_type", [item for item in TaskType if item != TaskType.QA_GOAL])
def test_registered_task_workflows_are_valid_dags(task_type):
    plan = build_plan(task_type)
    keys = [step.key for step in plan]
    assert len(keys) == len(set(keys))
    known = set(keys)
    assert all(set(step.depends_on) <= known for step in plan)
    assert all(step.tool and step.name for step in plan)


def test_goal_plan_skips_automation_when_every_case_is_already_bound():
    contract = parse_qa_goal("帮我把这个需求测试完整", {"requirement_id": "req-1"})
    plan = build_qa_goal_plan(
        contract,
        {"analysis_ready": True, "case_count": 2, "unbound_case_count": 0, "context_label": "REQ-1"},
    )
    tools = [step.tool for step in plan]
    assert "tests.generate" not in tools
    assert "source.write_generated" not in tools
    assert "tests.resolve_requirement" in tools
    assert "tests.run_regression" in tools


def test_goal_parser_maps_natural_language_scope_to_capabilities():
    full = parse_qa_goal("帮我把这个需求测试完整", {"requirement_id": "req-1"})
    assert full["mode"] == "complete_requirement"
    assert full["create_cases"] and full["generate_automation"] and full["run_tests"]
    assert full["allow_source_changes"]

    existing_requirement = parse_qa_goal("使用 QA Agent 测试一个已有需求。", {"requirement_id": "req-1"})
    assert existing_requirement["mode"] == "complete_requirement"
    assert existing_requirement["generate_automation"] and existing_requirement["run_tests"]

    negated_existing_requirement = parse_qa_goal("不需要测试现有需求", {"requirement_id": "req-1"})
    assert negated_existing_requirement["mode"] == "coverage"
    assert not negated_existing_requirement["run_tests"] and not negated_existing_requirement["allow_source_changes"]

    negated_full_requirement = parse_qa_goal("不需要完整测试现有需求", {"requirement_id": "req-1"})
    assert negated_full_requirement["mode"] == "coverage"
    assert not negated_full_requirement["create_cases"] and not negated_full_requirement["run_tests"]

    negated_reordered_full_requirement = parse_qa_goal("不必把需求测试完整", {"requirement_id": "req-1"})
    assert negated_reordered_full_requirement["mode"] == "coverage"

    unrelated_generation_constraint = parse_qa_goal("不要生成代码，完整测试现有需求", {"requirement_id": "req-1"})
    assert unrelated_generation_constraint["mode"] == "complete_requirement"
    assert unrelated_generation_constraint["run_tests"] and not unrelated_generation_constraint["generate_automation"]
    assert not unrelated_generation_constraint["allow_source_changes"]

    english_negated_requirement = parse_qa_goal("Do not test this existing requirement", {"requirement_id": "req-1"})
    assert english_negated_requirement["mode"] == "coverage"
    assert not english_negated_requirement["generate_automation"] and not english_negated_requirement["run_tests"]

    english_negated_full_requirement = parse_qa_goal(
        "Do not fully test this existing requirement", {"requirement_id": "req-1"}
    )
    assert english_negated_full_requirement["mode"] == "coverage"
    assert not english_negated_full_requirement["create_cases"] and not english_negated_full_requirement["run_tests"]

    english_no_run = parse_qa_goal(
        "Do not run any tests, but fully test this existing requirement", {"requirement_id": "req-1"}
    )
    assert english_no_run["mode"] == "complete_requirement"
    assert english_no_run["no_run"] and not english_no_run["run_tests"]

    analysis = parse_qa_goal("分析这个已有需求", {"requirement_id": "req-1"})
    assert analysis["mode"] == "analysis"
    assert not analysis["run_tests"] and not analysis["allow_source_changes"]

    coverage = parse_qa_goal("只检查覆盖，不要生成代码", {"requirement_id": "req-1"})
    assert coverage["mode"] == "coverage"
    assert not coverage["create_cases"] and not coverage["generate_automation"] and not coverage["run_tests"]
    assert not coverage["allow_source_changes"]

    cases = parse_qa_goal("生成缺失 Case，但不要运行", {"requirement_id": "req-1"})
    assert cases["mode"] == "cases" and cases["create_cases"]
    assert not cases["run_tests"] and not cases["allow_source_changes"]

    run = parse_qa_goal("跑完这些测试，有问题告诉我", {"requirement_id": "req-1"})
    assert run["mode"] == "run_requirement" and run["run_tests"]
    assert not run["generate_automation"] and not run["allow_source_changes"]


def test_complete_requirement_plan_has_unique_keys_and_resolvable_dependencies():
    contract = parse_qa_goal("帮我把这个需求测试完整", {"requirement_id": "req-1"})
    plan = build_qa_goal_plan(
        contract,
        {
            "analysis_ready": False,
            "design_count": 1,
            "case_count": 1,
            "unbound_case_count": 1,
            "unbound_case_ids": ["case-1"],
            "context_label": "REQ-1",
        },
    )
    keys = [step.key for step in plan]
    assert len(keys) == len(set(keys))
    assert all(set(step.depends_on) <= set(keys) for step in plan)


@pytest.mark.asyncio
async def test_qa_goal_prefixed_repair_outputs_keep_tool_aliases(monkeypatch):
    task = SimpleNamespace(id="task-1", inputs={})
    steps = [
        SimpleNamespace(key="approval", status=TaskStepStatus.COMPLETED.value, outputs={"approved": False}, inputs={}),
        SimpleNamespace(
            key="failure_collect", status=TaskStepStatus.COMPLETED.value, outputs={"id": "failure-1"}, inputs={}
        ),
        SimpleNamespace(
            key="failure_classify",
            status=TaskStepStatus.COMPLETED.value,
            outputs={"classification": "LOCATOR_CHANGED"},
            inputs={},
        ),
        SimpleNamespace(
            key="failure_inspect",
            status=TaskStepStatus.COMPLETED.value,
            outputs={"file_path": "tests/test_shop.py"},
            inputs={},
        ),
        SimpleNamespace(
            key="failure_diagnose", status=TaskStepStatus.COMPLETED.value, outputs={"repairable": True}, inputs={}
        ),
        SimpleNamespace(
            key="repair_repair",
            status=TaskStepStatus.COMPLETED.value,
            outputs={"file_path": "tests/test_shop.py"},
            inputs={},
        ),
        SimpleNamespace(
            key="repair_approval", status=TaskStepStatus.COMPLETED.value, outputs={"approved": True}, inputs={}
        ),
        SimpleNamespace(
            key="repair_apply", status=TaskStepStatus.COMPLETED.value, outputs={"written": True}, inputs={}
        ),
        SimpleNamespace(
            key="repair_target_run", status=TaskStepStatus.COMPLETED.value, outputs={"run_id": "run-1"}, inputs={}
        ),
        SimpleNamespace(
            key="repair_regression", status=TaskStepStatus.SKIPPED.value, outputs={"skipped": True}, inputs={}
        ),
    ]
    captured = {}

    async def load(_task_id):
        return task, steps

    async def capture_apply(_task, outputs):
        captured["apply"] = outputs
        return {}

    async def capture_summary(_task, outputs):
        captured["summary"] = outputs
        return {}

    monkeypatch.setattr(task_execution_service.execution_ports, "load_task", load)
    monkeypatch.setattr(task_execution_service.failure_repair, "_apply_repair", capture_apply)
    monkeypatch.setattr(task_execution_service.goal_service, "_summarize_goal", capture_summary)

    await task_execution_service._run_tool("task-1", "repair_apply", "source.apply_repair")
    assert captured["apply"]["collect"]["id"] == "failure-1"
    assert captured["apply"]["diagnose"]["repairable"] is True
    assert captured["apply"]["repair"]["file_path"] == "tests/test_shop.py"
    assert captured["apply"]["approval"]["approved"] is True

    await task_execution_service._run_tool("task-1", "goal_summary", "goal.summary")
    assert captured["summary"]["diagnose"]["repairable"] is True
    assert captured["summary"]["apply"]["written"] is True
    assert captured["summary"]["target_run"]["run_id"] == "run-1"
    assert "regression" not in captured["summary"]


@pytest.mark.asyncio
async def test_repair_regression_failure_cannot_be_summarized_as_verified(test_db_session, monkeypatch):
    task = SimpleNamespace(id="missing-task", type=TaskType.QA_GOAL.value, goal="Repair and verify", inputs={})

    async def no_evidence(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(task_execution_service.execution_ports, "evidence", no_evidence)
    outputs = {
        "target_run": {"run_id": "target-1", "status": "PASSED", "total": 1, "passed": 1, "failed": 0},
        "regression": {"run_id": "regression-1", "status": "FAILED", "total": 2, "passed": 1, "failed": 1},
    }

    verification = await task_execution_service._verify_tests(task, outputs)
    assert not verification["verified"]
    assert verification["run_ids"] == ["target-1", "regression-1"]

    summary_result = await task_execution_service._summarize_goal(task, outputs)
    assert summary_result["summary"]["status"] == "COMPLETED_WITH_UNRESOLVED"
    assert not summary_result["verified"]
    assert summary_result["summary"]["tests"]["failed"] == 1


@pytest.mark.asyncio
async def test_task_execution_budget_is_preserved_across_worker_resume(client, test_db_session, monkeypatch):
    created = await client.post(
        "/api/tasks",
        json={
            "type": "EXPLORE_PAGE",
            "goal": "Preserve execution budget across resume",
            "inputs": {"url": "http://127.0.0.1:1/"},
            "max_duration_seconds": 10,
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        task.context = {**task.context, "_execution_elapsed_seconds": 7.0}
        await session.commit()

    remaining_budgets = []

    async def observe_deadline(_task_id, started):
        remaining_budgets.append(started + 10 - time.monotonic())
        await asyncio.sleep(0.02)
        if len(remaining_budgets) == 1:
            async with test_db_session() as session:
                task = await session.get(TaskORM, task_id)
                assert task is not None
                task.status = TaskStatus.FAILED.value
                await session.commit()

    monkeypatch.setattr(task_scheduler_service, "_execute_dag", observe_deadline)
    await task_scheduler_service._execute_task(task_id)
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        assert task.context["_execution_elapsed_seconds"] >= 7.02
        task.status = TaskStatus.PENDING.value
        await session.commit()
    await task_scheduler_service._execute_task(task_id)

    assert all(2.5 <= remaining <= 3.1 for remaining in remaining_budgets)
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        assert task.context["_execution_elapsed_seconds"] >= 7.04


@pytest.mark.asyncio
async def test_pause_boundary_persists_execution_budget_before_resume(client, test_db_session, monkeypatch):
    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "Persist runtime at pause", "inputs": {"url": "http://127.0.0.1:1/"}},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        task.status = TaskStatus.PAUSING.value
        task.context = {**task.context, "_execution_elapsed_seconds": 4.0}
        await session.commit()
    monkeypatch.setattr("app.services.task_scheduler_service.workspace_source_snapshot", lambda _workspace_id: {})

    assert await task_scheduler_service._pause_at_boundary(task_id, elapsed_seconds=6.0)
    paused = await task_command_service.get(task_id)
    assert paused is not None and paused.status == TaskStatus.PAUSED
    assert paused.context["_execution_elapsed_seconds"] == 6.0

    resumed = await client.post(f"/api/tasks/{task_id}/resume")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == TaskStatus.PENDING.value
    assert resumed.json()["context"]["_execution_elapsed_seconds"] == 6.0


def test_goal_plan_scopes_run_only_and_read_only_failure_goals():
    run_contract = parse_qa_goal("跑完这些测试，有问题告诉我", {"requirement_id": "req-1"})
    run_plan = build_qa_goal_plan(run_contract, {"analysis_ready": True, "case_count": 1, "unbound_case_count": 0})
    assert run_contract["mode"] == "run_requirement"
    assert not run_contract["allow_source_changes"]
    assert not any(
        step.tool in {"tests.generate", "source.apply_repair", "source.write_generated"} for step in run_plan
    )

    inspect_contract = parse_qa_goal("只分析，不要修改", {"failure_id": "failure-1"})
    inspect_plan = build_qa_goal_plan(inspect_contract, {})
    assert inspect_contract["mode"] == "failure"
    assert not inspect_contract["run_tests"]
    assert not any(step.tool in {"source.apply_repair", "tests.run_target"} for step in inspect_plan)
    assert "failure.diagnose" in [step.tool for step in inspect_plan]


def test_goal_plan_adds_approval_and_repair_only_for_eligible_locator_failures():
    contract = parse_qa_goal("把这个失败修好", {"failure_id": "failure-1"})
    plan = build_qa_goal_plan(contract, {})
    repair = next(step for step in plan if step.tool == "failure.prepare_repair")
    assert repair.when == {"output_truthy": {"step": "diagnose", "field": "repairable"}}
    assert any(step.tool == "task.request_approval" for step in plan)
    assert any(step.tool == "source.apply_repair" for step in plan)


def test_goal_plan_reuses_existing_case_automation_instead_of_generating_again():
    contract = parse_qa_goal("生成并验证当前用例自动化", {"test_case_id": "case-1"})
    plan = build_qa_goal_plan(contract, {"nodeids": ["tests/test_shop.py::test_cart"], "case_count": 1})
    tools = [step.tool for step in plan]
    assert "source.inspect" in tools
    assert "tests.run_regression" in tools
    assert "tests.generate" not in tools
    assert "task.request_approval" not in tools


def test_goal_parser_keeps_ambiguous_project_goals_read_only_and_respects_case_run_intent():
    project_analysis = parse_qa_goal("分析这个项目", {})
    assert project_analysis["mode"] == "review_project"
    assert not project_analysis["run_tests"]
    assert [step.tool for step in build_qa_goal_plan(project_analysis, {})] == ["goal.review_project", "goal.summary"]

    run_and_review = parse_qa_goal("运行当前测试用例并检查自动化质量", {"test_case_id": "case-1"})
    assert run_and_review["mode"] == "run_case"
    assert run_and_review["run_tests"]

    explicit_test = parse_qa_goal(
        "运行这个测试并汇报结果，不要使用浏览器", {"nodeids": ["tests/test_smoke.py::test_ok"]}
    )
    assert explicit_test["mode"] == "run_project" and explicit_test["run_tests"]
    assert not explicit_test["allow_browser"]

    regenerate = parse_qa_goal("重新生成这个用例的自动化", {"test_case_id": "case-1"})
    regenerate_plan = build_qa_goal_plan(regenerate, {"nodeids": ["tests/test_shop.py::test_cart"]})
    assert "tests.generate" in [step.tool for step in regenerate_plan]

    analysis_only = parse_qa_goal("只分析，不要修改", {"requirement_id": "req-1"})
    analysis_plan = build_qa_goal_plan(analysis_only, {"analysis_ready": True})
    assert not analysis_only["run_tests"] and not analysis_only["allow_source_changes"]
    assert not any(step.tool.startswith("tests.run") or step.tool.startswith("source.write") for step in analysis_plan)

    no_browser = parse_qa_goal("生成并验证当前用例自动化，不要使用浏览器", {"test_case_id": "case-1"})
    no_browser_plan = build_qa_goal_plan(no_browser, {})
    assert not no_browser["allow_browser"]
    assert not any(
        step.tool.startswith("browser.") or step.tool == "decision.select_candidate" for step in no_browser_plan
    )


@pytest.mark.asyncio
async def test_browser_verify_rejects_unmet_explicit_goal_criteria():
    with pytest.raises(TaskBlocked, match="did not satisfy"):
        await task_execution_service._browser_verify(
            None,
            {
                "inspect": {"url": "https://shop.example", "title": "Shop"},
                "act": {
                    "steps": [{"action": "click", "name": "Submit order"}],
                    "validation_scope": "explicit_observed_text",
                    "goal_validated": False,
                },
            },
        )


@pytest.mark.parametrize(
    "source",
    [
        "def test_generated():\n    assert True\n",
        "import pytest\ndef test_generated():\n    pytest.skip('skip')\n",
        "import pytest\ndef test_generated():\n    pytest.xfail('xfail')\n",
        "import pytest\npytest.importorskip('optional')\ndef test_generated():\n    assert 1 == 1\n",
        "import pytest\n@pytest.mark.skip\ndef test_generated():\n    assert 1 == 1\n",
        "import pytest\n@pytest.mark.skipif(True, reason='skip')\ndef test_generated():\n    assert 1 == 1\n",
        "import pytest\n@pytest.mark.xfail\ndef test_generated():\n    assert 1 == 1\n",
        "def test_generated():\n    try:\n        check()\n    except Exception:\n        pass\n",
    ],
)
def test_goal_generated_test_rejects_assertion_or_skip_bypasses(source):
    with pytest.raises(TaskBlocked):
        TaskCodeGenerationService._validate_goal_generated_test(source, "tests/generated.py")


@pytest.mark.asyncio
async def test_task_api_persists_task_steps_and_replayable_terminal_events(client, test_db_session):
    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "Inspect the local help page", "inputs": {"url": "http://127.0.0.1:1/"}},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"

    listed = await client.get("/api/tasks")
    assert listed.status_code == 200
    assert any(item["id"] == task_id for item in listed.json())

    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        task.status = TaskStatus.COMPLETED.value
        rows = await TaskRepository(session).steps_for_task(task_id)
        assert len(rows) == len(build_plan(TaskType.EXPLORE_PAGE))
        await TaskRepository(session).add_event(task_id, "task.completed", {"verification": "test"})
        await session.commit()

    detail = await client.get(f"/api/tasks/{task_id}")
    assert detail.status_code == 200
    assert [step["key"] for step in detail.json()["steps"]] == [step.key for step in build_plan(TaskType.EXPLORE_PAGE)]
    stream = await client.get(f"/api/tasks/{task_id}/events")
    assert stream.status_code == 200
    assert '"type": "task.created"' in stream.text
    assert '"type": "task.completed"' in stream.text

    resumed = await client.get(f"/api/tasks/{task_id}/events", headers={"Last-Event-ID": "1"})
    assert resumed.status_code == 200
    assert '"type": "task.completed"' in resumed.text
    assert '"type": "task.created"' not in resumed.text
    invalid_cursor = await client.get(f"/api/tasks/{task_id}/events", headers={"Last-Event-ID": "invalid"})
    assert invalid_cursor.status_code == 400


@pytest.mark.asyncio
async def test_goal_preview_uses_selected_context_and_duplicate_start_is_idempotent(client):
    project = await client.post("/api/projects", json={"name": "Goal Context", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    requirement = await client.post(
        "/api/requirements",
        json={
            "project_id": project_id,
            "title": "Cart quantity boundary",
            "description": "Cart quantity must stay within the allowed range.",
            "acceptance_criteria": "Reject a quantity below one and above ten.",
        },
    )
    assert requirement.status_code == 201, requirement.text
    requirement_id = requirement.json()["id"]
    case = await client.post(
        "/api/test-cases",
        json={
            "project_id": project_id,
            "requirement_id": requirement_id,
            "title": "Reject quantity zero",
            "steps": ["Set quantity to zero", "Submit the cart"],
            "expected_result": "The cart rejects the quantity.",
        },
    )
    assert case.status_code == 201, case.text

    payload = {
        "type": "QA_GOAL",
        "goal": "只检查覆盖，不要生成代码",
        "project_id": project_id,
        "workspace_id": workspace["id"],
        "inputs": {"requirement_id": requirement_id},
        "idempotency_key": "same-user-intent",
    }
    preview = await client.post("/api/tasks/preview", json=payload)
    assert preview.status_code == 200, preview.text
    assert "Cart quantity boundary" in preview.json()["context"]
    assert preview.json()["constraints"] == ["不修改源码", "不运行测试"]
    assert preview.json()["approval_required"] is False
    assert preview.json()["steps"]

    full_preview = await client.post(
        "/api/tasks/preview",
        json={
            **payload,
            "goal": "帮我把这个需求测试完整。可以自动完成低风险步骤；需要修改代码时让我确认。",
            "idempotency_key": "complete-requirement-preview",
        },
    )
    assert full_preview.status_code == 200, full_preview.text
    assert full_preview.json()["approval_required"] is True
    assert "创建缺失的 Test Design / Test Case 记录" in full_preview.json()["effects"]
    assert "生成自动化测试草案" in full_preview.json()["effects"]
    assert "运行目标 pytest 用例" in full_preview.json()["effects"]

    raised_budget = await client.post(
        "/api/tasks",
        json={**payload, "plan_token": preview.json()["plan_token"], "max_ai_calls": 50},
    )
    assert raised_budget.status_code == 201, raised_budget.text
    from app.settings import get_config

    assert raised_budget.json()["max_ai_calls"] == get_config().ai.budget.max_task_calls

    updated_requirement = await client.patch(
        f"/api/requirements/{requirement_id}",
        json={"acceptance_criteria": "Reject quantities below one, above ten, and after inventory changes."},
    )
    assert updated_requirement.status_code == 200, updated_requirement.text
    stale = await client.post("/api/tasks", json={**payload, "idempotency_key": "stale-plan-after-context-change"})
    assert stale.status_code == 422
    assert "Preview the goal again" in stale.json()["detail"]
    refreshed_preview = await client.post("/api/tasks/preview", json=payload)
    assert refreshed_preview.status_code == 200, refreshed_preview.text
    payload["plan_token"] = refreshed_preview.json()["plan_token"]

    first = await client.post("/api/tasks", json=payload)
    second = await client.post("/api/tasks", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    listed = await client.get(f"/api/tasks?project_id={project_id}")
    assert len([task for task in listed.json() if task["type"] == "QA_GOAL"]) == 1

    case_preview = await client.post(
        "/api/tasks/preview",
        json={
            **payload,
            "goal": "Review this test automation",
            "idempotency_key": None,
            "inputs": {"test_case_id": case.json()["id"]},
        },
    )
    assert case_preview.status_code == 200, case_preview.text
    assert case_preview.json()["context"] == "Reject quantity zero"


@pytest.mark.asyncio
async def test_parallel_goal_creation_keeps_requirement_contexts_isolated(client):
    project = await client.post("/api/projects", json={"name": "Multi Goal Context", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    requirements = []
    for title in ["Requirement Alpha", "Requirement Beta"]:
        response = await client.post(
            "/api/requirements",
            json={"project_id": project_id, "title": title, "acceptance_criteria": f"Check {title}."},
        )
        assert response.status_code == 201, response.text
        requirements.append(response.json())

    tasks = []
    for requirement in requirements:
        payload = {
            "type": "QA_GOAL",
            "goal": "只检查覆盖，不要生成代码",
            "project_id": project_id,
            "workspace_id": workspace["id"],
            "inputs": {"requirement_id": requirement["id"]},
        }
        preview = await client.post("/api/tasks/preview", json=payload)
        assert preview.status_code == 200, preview.text
        created = await client.post("/api/tasks", json={**payload, "plan_token": preview.json()["plan_token"]})
        assert created.status_code == 201, created.text
        tasks.append(created.json())

    assert tasks[0]["id"] != tasks[1]["id"]
    for task, requirement in zip(tasks, requirements, strict=True):
        detail = await client.get(f"/api/tasks/{task['id']}")
        assert detail.status_code == 200
        assert detail.json()["inputs"]["requirement_id"] == requirement["id"]
        assert detail.json()["inputs"]["_goal_contract"]["requirement_id"] == requirement["id"]


@pytest.mark.asyncio
async def test_paused_goal_rereads_studio_edits_and_refreshes_its_plan(client, test_db_session):
    project = await client.post("/api/projects", json={"name": "Pause Resume", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    requirement = await client.post(
        "/api/requirements",
        json={
            "project_id": project_id,
            "title": "Studio edit refresh",
            "description": "A requirement used to verify human takeover.",
            "acceptance_criteria": "The workspace change is re-read before the agent continues.",
        },
    )
    assert requirement.status_code == 201, requirement.text
    payload = {
        "type": "QA_GOAL",
        "goal": "只检查覆盖，不要生成代码",
        "project_id": project_id,
        "workspace_id": workspace["id"],
        "inputs": {"requirement_id": requirement.json()["id"]},
    }
    preview = await client.post("/api/tasks/preview", json=payload)
    assert preview.status_code == 200, preview.text
    created = await client.post("/api/tasks", json={**payload, "plan_token": preview.json()["plan_token"]})
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with test_db_session() as session:
        repo = TaskRepository(session)
        rows = await repo.steps_for_task(task_id)
        coverage_step = next(row for row in rows if row.key == "coverage")
        await repo.update_step(
            coverage_step.id,
            status=TaskStepStatus.COMPLETED.value,
            outputs={"missing_criteria": ["stale finding"]},
        )
        await session.commit()

    paused = await client.post(f"/api/tasks/{task_id}/pause")
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "PAUSED"

    edited_file = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_studio_takeover.py"
    edited_file.write_text("def test_broken(:\n    assert True\n", encoding="utf-8")
    invalid_resume = await client.post(f"/api/tasks/{task_id}/resume")
    assert invalid_resume.status_code == 409
    assert "test_studio_takeover.py" in invalid_resume.json()["detail"]
    still_paused = await client.get(f"/api/tasks/{task_id}")
    assert still_paused.json()["status"] == "PAUSED"

    edited_file.write_text("def test_studio_takeover():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    config_file = Path(settings.workspace_storage_dir) / project_id / "pytest.ini"
    config_file.write_text("[pytest]\naddopts = -q\n", encoding="utf-8")
    resumes = await asyncio.gather(
        client.post(f"/api/tasks/{task_id}/resume"),
        client.post(f"/api/tasks/{task_id}/resume"),
    )
    assert sorted(response.status_code for response in resumes) == [200, 409]
    resumed = next(response for response in resumes if response.status_code == 200)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "PENDING"
    events = resumed.json()["events"]
    plan_event = next(item for item in events if item["type"] == "task.plan_refreshed")
    assert "tests/test_studio_takeover.py" in plan_event["payload"]["changed_files"]
    assert "pytest.ini" in plan_event["payload"]["changed_files"]
    assert {"coverage", "goal_summary"} <= set(plan_event["payload"]["invalidated_steps"])
    refreshed_coverage = next(step for step in resumed.json()["steps"] if step["key"] == "coverage")
    assert refreshed_coverage["status"] == "PENDING" and refreshed_coverage["outputs"] == {}
    assert any(item["type"] == "task.resumed" for item in events)


@pytest.mark.asyncio
async def test_paused_typed_review_invalidates_stale_source_findings(client, test_db_session):
    project = await client.post("/api/projects", json={"name": "Typed Review Resume", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    payload = {
        "type": "REVIEW_TEST",
        "goal": "Review selected test assertions",
        "project_id": project_id,
        "workspace_id": workspace["id"],
        "inputs": {"file_path": "tests/test_review.py"},
    }
    created = await client.post("/api/tasks", json=payload)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with test_db_session() as session:
        repo = TaskRepository(session)
        rows = await repo.steps_for_task(task_id)
        for row in rows:
            if row.key in {"inspect", "review"}:
                await repo.update_step(
                    row.id,
                    status=TaskStepStatus.COMPLETED.value,
                    outputs={"source_digest": "before-studio-edit"},
                )
        await session.commit()

    paused = await client.post(f"/api/tasks/{task_id}/pause")
    assert paused.status_code == 200 and paused.json()["status"] == "PAUSED"
    edited_file = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_review.py"
    edited_file.write_text("def test_review():\n    assert 2 + 2 == 4\n", encoding="utf-8")

    resumed = await client.post(f"/api/tasks/{task_id}/resume")
    assert resumed.status_code == 200 and resumed.json()["status"] == "PENDING"
    refreshed = {step["key"]: step for step in resumed.json()["steps"]}
    assert refreshed["inspect"]["status"] == refreshed["review"]["status"] == "PENDING"
    assert refreshed["inspect"]["outputs"] == refreshed["review"]["outputs"] == {}
    event = next(item for item in resumed.json()["events"] if item["type"] == "task.context_refreshed")
    assert event["payload"]["changed_files"] == ["tests/test_review.py"]
    assert {"inspect", "review"} <= set(event["payload"]["invalidated_steps"])


@pytest.mark.asyncio
async def test_paused_typed_create_invalidates_generated_output_after_source_change(client, test_db_session):
    project = await client.post("/api/projects", json={"name": "Create Test Resume", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    created = await client.post(
        "/api/tasks",
        json={
            "type": "CREATE_TEST",
            "goal": "Generate a test from current workspace source",
            "project_id": project_id,
            "workspace_id": workspace["id"],
            "inputs": {"url": "http://127.0.0.1:1/", "file_path": "tests/test_target.py"},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    paused = await client.post(f"/api/tasks/{task_id}/pause")
    assert paused.status_code == 200 and paused.json()["status"] == "PAUSED"
    async with test_db_session() as session:
        repo = TaskRepository(session)
        rows = await repo.steps_for_task(task_id)
        generate = next(row for row in rows if row.key == "generate")
        await repo.update_step(
            generate.id,
            status=TaskStepStatus.COMPLETED.value,
            outputs={"target_file": "tests/test_target.py", "code": "old generated code"},
        )
        await session.commit()

    edited_file = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_target.py"
    edited_file.write_text("def test_target():\n    assert 3 == 3\n", encoding="utf-8")
    resumed = await client.post(f"/api/tasks/{task_id}/resume")
    assert resumed.status_code == 200 and resumed.json()["status"] == "PENDING"
    generate_after_resume = next(step for step in resumed.json()["steps"] if step["key"] == "generate")
    assert generate_after_resume["status"] == "PENDING"
    assert generate_after_resume["outputs"] == {}
    event = next(item for item in resumed.json()["events"] if item["type"] == "task.context_refreshed")
    assert "generate" in event["payload"]["invalidated_steps"]


@pytest.mark.asyncio
async def test_cancel_during_resume_cannot_restart_task(client, monkeypatch):
    project = await client.post("/api/projects", json={"name": "Resume Cancel Race", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    requirement = await client.post(
        "/api/requirements",
        json={
            "project_id": project_id,
            "title": "Resume cancellation",
            "acceptance_criteria": "Keep a cancel decision.",
        },
    )
    assert requirement.status_code == 201, requirement.text
    payload = {
        "type": "QA_GOAL",
        "goal": "只检查覆盖，不要生成代码",
        "project_id": project_id,
        "workspace_id": workspace["id"],
        "inputs": {"requirement_id": requirement.json()["id"]},
    }
    preview = await client.post("/api/tasks/preview", json=payload)
    assert preview.status_code == 200, preview.text
    created = await client.post("/api/tasks", json={**payload, "plan_token": preview.json()["plan_token"]})
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    paused = await client.post(f"/api/tasks/{task_id}/pause")
    assert paused.status_code == 200 and paused.json()["status"] == "PAUSED"

    compile_started = asyncio.Event()
    continue_compile = asyncio.Event()
    original_compile = task_command_service._compile_goal

    async def blocked_compile(data):
        compile_started.set()
        await continue_compile.wait()
        return await original_compile(data)

    monkeypatch.setattr(task_command_service, "_compile_goal", blocked_compile)
    resuming = asyncio.create_task(client.post(f"/api/tasks/{task_id}/resume"))
    await asyncio.wait_for(compile_started.wait(), timeout=5)
    cancelled = await client.post(f"/api/tasks/{task_id}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    continue_compile.set()
    resumed = await resuming
    assert resumed.status_code == 200 and resumed.json()["status"] == "CANCELLED"
    final = await client.get(f"/api/tasks/{task_id}")
    assert final.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_requirement_analysis_task_requires_owned_project_context(client):
    first_project = await client.post("/api/projects", json={"name": "Analysis Task Project"})
    second_project = await client.post("/api/projects", json={"name": "Other Analysis Project"})
    assert first_project.status_code == second_project.status_code == 201
    project_id = first_project.json()["id"]
    requirement = await client.post(
        "/api/requirements",
        json={
            "project_id": project_id,
            "title": "Search empty state",
            "description": "Show a clear message when a product search has no results.",
            "acceptance_criteria": "No product cards are displayed when there are no matches.",
        },
    )
    assert requirement.status_code == 201, requirement.text
    requirement_id = requirement.json()["id"]

    created = await client.post(
        "/api/tasks",
        json={
            "type": "ANALYZE_REQUIREMENT",
            "goal": "Analyze the empty search requirement",
            "project_id": project_id,
            "inputs": {"requirement_id": requirement_id},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["type"] == "ANALYZE_REQUIREMENT"
    detail = await client.get(f"/api/tasks/{created.json()['id']}")
    assert detail.status_code == 200, detail.text
    assert [step["key"] for step in detail.json()["steps"]] == ["analyze"]

    mismatched = await client.post(
        "/api/tasks",
        json={
            "type": "ANALYZE_REQUIREMENT",
            "goal": "Analyze a requirement from another project",
            "project_id": second_project.json()["id"],
            "inputs": {"requirement_id": requirement_id},
        },
    )
    assert mismatched.status_code == 422
    assert "does not belong" in mismatched.json()["detail"]

    missing = await client.post(
        "/api/tasks",
        json={"type": "ANALYZE_REQUIREMENT", "goal": "Analyze a missing requirement", "project_id": project_id},
    )
    assert missing.status_code == 422
    assert "requirement_id" in missing.json()["detail"]


@pytest.mark.asyncio
async def test_task_replan_retries_only_failed_read_only_step(client, test_db_session):
    created = await client.post(
        "/api/tasks", json={"type": "EXPLORE_PAGE", "goal": "Inspect a page", "inputs": {"url": "http://127.0.0.1:1/"}}
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        task.status = TaskStatus.BLOCKED.value
        repo = TaskRepository(session)
        rows = await repo.steps_for_task(task_id)
        await repo.update_step(
            rows[0].id,
            status=TaskStepStatus.FAILED.value,
            error="Temporary navigation error",
        )
        await session.commit()

    replanned = await client.post(
        f"/api/tasks/{task_id}/replan", params={"instructions": "Retry after checking the page URL"}
    )
    assert replanned.status_code == 200, replanned.text
    assert replanned.json()["status"] == "REPLANNING"
    browser_agent = next(step for step in replanned.json()["steps"] if step["key"] == "browser_agent")
    assert browser_agent["status"] == "PENDING"
    assert browser_agent["error"] is None


@pytest.mark.asyncio
async def test_restart_recovery_blocks_active_steps_without_replaying_them(client, test_db_session):
    created = await client.post(
        "/api/tasks",
        json={
            "type": "EXPLORE_PAGE",
            "goal": "Recover an interrupted browser task",
            "inputs": {"url": "http://127.0.0.1:1/"},
        },
    )
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        task.status = TaskStatus.RUNNING.value
        repo = TaskRepository(session)
        steps = await repo.steps_for_task(task_id)
        await repo.update_step(steps[0].id, status=TaskStepStatus.RUNNING.value)
        await session.commit()

    recovered = await task_scheduler_service.recover_interrupted()
    assert task_id in recovered
    detail = await task_command_service.get(task_id)
    assert detail is not None and detail.status == TaskStatus.BLOCKED
    assert detail.steps[0].status == TaskStepStatus.FAILED
    assert "API restarted" in (detail.steps[0].error or "")


@pytest.mark.asyncio
async def test_replan_refuses_to_replay_completed_source_writes(client, test_db_session):
    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "Do not replay source writes", "inputs": {"url": "http://127.0.0.1:1/"}},
    )
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        owner_id = task.owner_id
        task.status = TaskStatus.BLOCKED.value
        repo = TaskRepository(session)
        steps = await repo.steps_for_task(task_id)
        await repo.update_step(
            steps[0].id,
            key="write",
            tool="source.write_generated",
            status=TaskStepStatus.COMPLETED.value,
        )
        await session.commit()

    with pytest.raises(ValueError, match="already changed workspace source"):
        await task_command_service.replan(task_id, owner_id, "retry")
    detail = await task_command_service.get(task_id)
    assert detail is not None and detail.status == TaskStatus.BLOCKED


@pytest.mark.asyncio
async def test_replan_retries_failed_step_and_preserves_completed_steps(client, test_db_session):
    from uuid import uuid4

    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "Retry a blocked runtime step", "inputs": {"url": "http://127.0.0.1:1/"}},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        owner_id = task.owner_id
        task.status = TaskStatus.BLOCKED.value
        repo = TaskRepository(session)
        steps = await repo.steps_for_task(task_id)
        failed = TaskStepORM(
            id=uuid4().hex,
            task_id=task_id,
            position=1,
            key="verify",
            name="Verify the browser result",
            tool="task.verify",
            dependencies=[steps[0].key],
        )
        session.add(failed)
        await session.flush()
        steps = await repo.steps_for_task(task_id)
        completed, failed = steps[:2]
        await repo.update_step(completed.id, status=TaskStepStatus.COMPLETED.value)
        await repo.update_step(
            failed.id,
            status=TaskStepStatus.FAILED.value,
            retry_count=2,
            duration_ms=875,
        )
        task.current_step_id = failed.id
        task.failure_reason = "AI did not return executable source code."
        await session.commit()

    detail = await task_command_service.replan(task_id, owner_id, "Retry the failed step with the same evidence.")
    assert detail is not None and detail.status == TaskStatus.REPLANNING
    assert detail.retry_count == 1 and detail.replan_count == 1
    assert detail.steps[0].status == TaskStepStatus.COMPLETED
    assert detail.steps[1].status == TaskStepStatus.PENDING
    assert detail.steps[1].retry_count == 3
    assert detail.steps[1].duration_ms == 0


@pytest.mark.asyncio
async def test_concurrent_replans_only_claim_a_blocked_task_once(client, test_db_session):
    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "Claim a replan once", "inputs": {"url": "http://127.0.0.1:1/"}},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        task.status = TaskStatus.BLOCKED.value
        repo = TaskRepository(session)
        steps = await repo.steps_for_task(task_id)
        await repo.update_step(steps[0].id, status=TaskStepStatus.FAILED.value)
        await session.commit()
        owner_id = task.owner_id

    results = await asyncio.gather(
        task_command_service.replan(task_id, owner_id, "Retry A"),
        task_command_service.replan(task_id, owner_id, "Retry B"),
    )
    assert sum(result is not None for result in results) == 1
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        steps = await TaskRepository(session).steps_for_task(task_id)
        assert task is not None
        assert task.replan_count == 1 and task.retry_count == 1
        assert steps[0].retry_count == 1 and steps[0].status == TaskStepStatus.PENDING.value


@pytest.mark.asyncio
async def test_cancel_during_approval_request_stays_cancelled(client, monkeypatch):
    from app.services.task_errors import ApprovalRequired

    project = await client.post("/api/projects", json={"name": "Cancel Approval Race", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace_id = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]["id"]
    created = await client.post(
        "/api/tasks",
        json={
            "type": "CREATE_TEST",
            "goal": "Cancel before approval wait",
            "project_id": project_id,
            "workspace_id": workspace_id,
            "inputs": {"url": "http://127.0.0.1:1/"},
        },
    )
    assert created.status_code == 201, created.text
    task, steps = await task_execution_service._load(created.json()["id"])
    assert task is not None
    approval = next(step for step in steps if step.key == "approval")

    async def cancel_before_wait(_task_id, _step, *, deadline=None):
        await task_command_service.cancel(task.id, task.owner_id)
        raise ApprovalRequired()

    monkeypatch.setattr(task_execution_service, "_run_step_tool", cancel_before_wait)
    result = await task_execution_service._execute_step(task, approval)
    detail = await task_command_service.get(task.id)
    assert isinstance(result, ApprovalRequired)
    assert detail is not None and detail.status == TaskStatus.CANCELLED
    assert next(step for step in detail.steps if step.id == approval.id).status == TaskStepStatus.CANCELLED


@pytest.mark.asyncio
async def test_task_approval_resumes_only_an_owned_waiting_task(client, test_db_session):
    project = await client.post("/api/projects", json={"name": "Task Approval Project", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspaces = await client.get(f"/api/workspaces?project_id={project_id}")
    assert workspaces.status_code == 200 and workspaces.json()
    workspace_id = workspaces.json()[0]["id"]
    created = await client.post(
        "/api/tasks",
        json={
            "type": "CREATE_TEST",
            "goal": "Create an approved login test",
            "project_id": project_id,
            "workspace_id": workspace_id,
            "inputs": {"url": "http://127.0.0.1:1/"},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        repo = TaskRepository(session)
        rows = await repo.steps_for_task(task_id)
        approval = next(step for step in rows if step.key == "approval")
        task.status = TaskStatus.WAITING.value
        task.current_step_id = approval.id
        await repo.update_step(approval.id, status=TaskStepStatus.WAITING_FOR_APPROVAL.value)
        await session.commit()

    response = await client.post(f"/api/tasks/{task_id}/approval", json={"approved": True, "comment": "Reviewed"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    approval = next(step for step in body["steps"] if step["key"] == "approval")
    assert approval["status"] == "COMPLETED"
    assert approval["outputs"]["approved"] is True


@pytest.mark.asyncio
async def test_task_endpoints_require_authentication(anonymous_client):
    response = await anonymous_client.get("/api/tasks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pending_task_can_be_cancelled(client):
    created = await client.post(
        "/api/tasks",
        json={
            "type": "EXPLORE_PAGE",
            "goal": "Cancel before browser navigation",
            "inputs": {"url": "http://127.0.0.1:1/"},
        },
    )
    assert created.status_code == 201, created.text
    cancelled = await client.post(f"/api/tasks/{created.json()['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancelling_active_task_stops_its_child_pytest(client):
    project = await client.post("/api/projects", json={"name": "Cancel Child Run", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_runtime_cancel.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("import time\n\ndef test_wait_for_cancellation():\n    time.sleep(30)\n", encoding="utf-8")

    await task_scheduler_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "RUN_REGRESSION",
                "goal": "Cancel the active child run",
                "project_id": project_id,
                "workspace_id": project_id,
                "inputs": {"nodeids": ["tests/test_runtime_cancel.py::test_wait_for_cancellation"]},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(100):
            await asyncio.sleep(0.1)
            child_run_id = task_execution_service._child_runs.get(task_id)
            if child_run_id:
                async with open_run_service() as service:
                    child = await service.get_run(child_run_id)
                if child and child.status.value == "RUNNING":
                    break
        assert child_run_id, "task never registered a child run"

        cancelled = await client.post(f"/api/tasks/{task_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
        detail = await client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200, detail.text
        assert any(step["status"] == "CANCELLED" for step in detail.json()["steps"])
        async with open_run_service() as service:
            child = await service.get_run(child_run_id)
        assert child is not None and child.status.value == "CANCELLED"
    finally:
        await task_scheduler_service.stop()


def test_generated_code_policy_rejects_python_internal_access():
    from app.services.task_errors import TaskBlocked

    with pytest.raises(TaskBlocked, match="Python internals"):
        TaskCodeGenerationService._validate_python_test(
            "def test_bad():\n    __builtins__['__import__']('os').system('whoami')\n",
            "tests/test_bad.py",
        )


@pytest.mark.asyncio
async def test_ai_repair_cannot_change_existing_assertions(monkeypatch):
    from types import SimpleNamespace

    from app.services.task_errors import TaskBlocked
    from app.services.task_runtime_service import TaskRuntimeService

    service = TaskRuntimeService(repository_scope=TaskRepositoryScopeFactory())
    task = SimpleNamespace(id="task-1", inputs={}, goal="Repair the missing argument")
    proposal = SimpleNamespace(
        suggested_code="def test_total():\n    result = calculate_total(20, 2)\n    assert result == 99\n"
    )

    async def code_ai(*_args):
        return proposal

    monkeypatch.setattr(service.execution.execution_ports, "call_code_ai", code_ai)
    with pytest.raises(TaskBlocked, match="changed an existing assertion"):
        await service.execution._prepare_repair(
            task,
            {
                "collect": {
                    "test_nodeid": "tests/test_total.py::test_total",
                    "error_message": "TypeError: missing quantity",
                },
                "inspect": {
                    "file_path": "tests/test_total.py",
                    "source": "def test_total():\n    result = calculate_total(20)\n    assert result == 40\n",
                },
                "diagnose": {"classification": "PYTHON_EXCEPTION"},
            },
        )


@pytest.mark.asyncio
async def test_literal_false_assertion_blocks_before_ai_call(monkeypatch):
    from types import SimpleNamespace

    from app.services.task_errors import TaskBlocked
    from app.services.task_runtime_service import TaskRuntimeService

    service = TaskRuntimeService(repository_scope=TaskRepositoryScopeFactory())
    task = SimpleNamespace(inputs={}, goal="Repair the failure")

    async def code_ai(*_args):
        pytest.fail("A contradictory literal assertion requires an explicit intended expectation")

    monkeypatch.setattr(service.execution.execution_ports, "call_code_ai", code_ai)
    with pytest.raises(TaskBlocked, match="deterministically false literal assertion"):
        await service.execution._prepare_repair(
            task,
            {
                "collect": {"test_nodeid": "tests/test_total.py::test_total"},
                "inspect": {"file_path": "tests/test_total.py", "source": "def test_total():\n    assert 1 == 2\n"},
            },
        )


def test_generated_code_policy_allows_url_parsing_but_blocks_network_imports():
    from app.services.task_errors import TaskBlocked

    TaskCodeGenerationService._validate_python_test(
        "from urllib.parse import unquote, urlsplit\n\n"
        "def test_proxy_url():\n    assert urlsplit(unquote('https%3A%2F%2Fexample.test')).scheme == 'https'\n",
        "tests/test_proxy_url.py",
    )

    with pytest.raises(TaskBlocked, match="process/network/system-control"):
        TaskCodeGenerationService._validate_python_test(
            "from urllib.request import urlopen\n\ndef test_bad():\n    urlopen('https://example.test')\n",
            "tests/test_bad.py",
        )

    with pytest.raises(TaskBlocked, match="approved browser environment settings"):
        TaskCodeGenerationService._validate_python_test(
            "import os\n\ndef test_bad():\n    os.getenv('AWS_SECRET_ACCESS_KEY')\n",
            "tests/test_bad.py",
        )


@pytest.mark.asyncio
async def test_regression_task_executes_a_real_local_pytest_run(client):
    project = await client.post("/api/projects", json={"name": "Real Task Runtime", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_runtime_real.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("def test_real_pytest_assertion():\n    assert 6 * 7 == 42\n", encoding="utf-8")

    await task_scheduler_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "RUN_REGRESSION",
                "goal": "Run the real local pytest assertion",
                "project_id": project_id,
                "workspace_id": project_id,
                "inputs": {
                    "nodeids": ["tests/test_runtime_real.py::test_real_pytest_assertion"],
                    "region": "local-test",
                },
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(200):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200, detail.text
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        executed = next(step for step in body["steps"] if step["key"] == "run")
        assert executed["outputs"]["status"] == "PASSED"
        assert executed["outputs"]["passed"] == 1
        assert body["verification"]["verified"] is True
        async with open_run_service() as service:
            child_run = await service.get_run(executed["outputs"]["run_id"])
        assert child_run is not None and child_run.environment["QA_REGION"] == "local-test"
    finally:
        await task_scheduler_service.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("jev_available", "scenario"),
    [(True, "normal"), (False, "normal"), (True, "recovery"), (True, "loop")],
)
async def test_browser_agent_observe_jev_execute_and_reobserve_on_local_page(
    client, monkeypatch, jev_available, scenario
):
    task_scheduler_service = get_task_runtime_service().scheduler
    from project_model.models import DecisionResult
    from qa_core.ai.models import AICompletionResponse
    from qa_core.ai.registry import AIProviderRegistry

    async def serve_page(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            path = request.split(b" ", 2)[1]
            if path == b"/details":
                title = "Account details"
                content = "<h1>Account billing is available</h1>"
            else:
                title = "Task Browser Check"
                content = "<h1>Help</h1><a href='/details'>View details</a><a href='/help'>Help center</a><button type='button' onclick='document.getElementById(&quot;notice&quot;).textContent = document.getElementById(&quot;notice&quot;).textContent === &quot;Ready&quot; ? &quot;Changed&quot; : &quot;Ready&quot;'>View help</button><p id='notice'>Ready</p><button>Delete account</button>"
            body = f"<html><head><title>{title}</title></head><body>{content}</body></html>".encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(serve_page, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    provider_observations = []

    class FixtureAIProvider:
        async def complete(self, request):
            prompt = json.loads(request.prompt)
            current = prompt["current_page"]
            provider_observations.append(
                {
                    "url": current["url"],
                    "elements": [(item["id"], item["role"], item["name"]) for item in current["interactive_elements"]],
                    "history": prompt["previous_actions_and_results"],
                }
            )
            if current["url"].endswith("/details"):
                plan = {
                    "goal_status": "completed",
                    "completion_evidence": ["Account billing is available"],
                }
            elif scenario in {"recovery", "loop"} and (
                scenario == "loop" or not prompt["previous_actions_and_results"]
            ):
                unexpected = next(item for item in current["interactive_elements"] if item["name"] == "View help")
                details = next(item for item in current["interactive_elements"] if item["name"] == "View details")
                plan = {
                    "subgoals": ["Open the details page", "Verify account billing content"],
                    "current_subgoal": "Choose a candidate to advance the details goal",
                    "candidates": [
                        {
                            "candidate_id": "repeat_control" if scenario == "loop" else "unexpected",
                            "action_type": "click",
                            "target_id": unexpected["id"],
                            "reason_summary": "This candidate will produce an unexpected page state.",
                            "expected_effect": "A completion banner appears.",
                        },
                        {
                            "candidate_id": "details",
                            "action_type": "navigate",
                            "target_id": details["id"],
                            "reason_summary": "The visible details link is relevant to the goal.",
                            "expected_effect": "Account billing details are visible.",
                        },
                    ],
                    "preferred_candidate_id": "details",
                }
            else:
                plan = {
                    "subgoals": ["Open the details page", "Verify account billing content"],
                    "current_subgoal": "Open the account details page",
                    "candidates": [
                        {
                            "candidate_id": "details",
                            "action_type": "navigate",
                            "target_id": "el_0",
                            "reason_summary": "The visible details link is relevant to the goal.",
                            "expected_effect": "Account billing details are visible.",
                        },
                        {
                            "candidate_id": "help",
                            "action_type": "navigate",
                            "target_id": "el_1",
                            "reason_summary": "This is another visible navigation option.",
                            "expected_effect": "The help center appears.",
                        },
                    ],
                    "preferred_candidate_id": "details",
                }
            return AICompletionResponse(
                invocation_id="fixture-browser-agent",
                content="{}",
                structured_data=plan,
                provider="test-provider",
                model="fixture-model",
            )

    class FixtureDecisionService:
        def __init__(self):
            self.calls = 0

        async def choose(self, request, **_kwargs):
            self.calls += 1
            if scenario == "loop":
                assert {option.key for option in request.options} == {"repeat_control", "details", "abstain"}
                choice = "repeat_control"
            elif scenario == "recovery" and self.calls == 1:
                assert {option.key for option in request.options} == {"unexpected", "details", "abstain"}
                choice = "unexpected"
            else:
                assert {option.key for option in request.options} == {"details", "help", "abstain"}
                choice = "details"
            assert len(request.state["relevant_elements"]) == 2
            if jev_available:
                return DecisionResult(
                    provider="jev",
                    model="fixture-jev",
                    choice=choice,
                    confidence=0.95,
                    probabilities={
                        key: 0.95 if key == choice else 0.04 if key != "abstain" else 0.01
                        for key in {option.key for option in request.options}
                    },
                )
            return DecisionResult(provider="fallback", fallback_used=True, reason="timeout")

    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda *_args, **_kwargs: FixtureAIProvider())
    decision_service = FixtureDecisionService()
    monkeypatch.setattr("app.services.task_decision_service.DecisionService", lambda **_kwargs: decision_service)
    await task_scheduler_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "EXPLORE_PAGE",
                "goal": "Open the details page and verify account billing without using destructive controls",
                "inputs": {"url": f"http://127.0.0.1:{port}/"},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(150):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200, detail.text
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        if body["status"] == "BLOCKED" and any(
            step.get("outputs", {}).get("failure_type") == "BROWSER_UNAVAILABLE" for step in body["steps"]
        ):
            pytest.skip("The API host cannot launch Chromium/Edge in this environment.")
        if scenario == "loop":
            assert body["status"] == "BLOCKED", {
                "status": body["status"],
                "events": body["events"][-15:],
                "steps": [
                    (step["key"], step["status"], step.get("error"), step.get("outputs")) for step in body["steps"]
                ],
                "provider_observations": provider_observations,
            }
            assert any(event["type"] == "browser.loop_detected" for event in body["events"])
            assert len([event for event in body["events"] if event["type"] == "browser.action_started"]) == 2
            return
        assert body["status"] == "COMPLETED", {
            "failure_reason": body.get("failure_reason"),
            "steps": [(step["key"], step["status"], step.get("error"), step.get("outputs")) for step in body["steps"]],
            "provider_observations": provider_observations,
        }
        agent = next(step for step in body["steps"] if step["key"] == "browser_agent")
        assert agent["outputs"]["kind"] == "ai_jev_browser_agent"
        assert agent["outputs"]["final_url"].endswith("/details")
        assert [item["status"] for item in agent["outputs"]["actions"]] == (
            ["unexpected", "success"] if scenario == "recovery" and jev_available else ["success"]
        ), agent["outputs"]["actions"]
        assert body["decisions"][0]["choice"] == (
            "unexpected" if scenario == "recovery" and jev_available else "details"
        )
        assert body["decisions"][0]["provider"] == ("jev" if jev_available else "ai-ranking")
        sample = agent["outputs"]["decision_samples"][0]
        assert sample["jev_attempted"] is True
        assert sample["fallback_used"] is (not jev_available)
        assert sample["fallback_reason"] == (None if jev_available else "timeout")
        assert sample["ai_provider"] == "test-provider"
        assert sample["ai_latency_ms"] >= 0
        assert body["evidence"]
        assert any(item["kind"] == "DECISION_SAMPLES" for item in body["artifacts"])
        screenshot = next(item for item in body["artifacts"] if item["kind"] == "SCREENSHOT")
        downloaded = await client.get(f"/api/artifacts/{screenshot['artifact_id']}/download")
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        await task_scheduler_service.stop()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_browser_agent_completes_second_ecommerce_journey_on_demo_shop(client, monkeypatch):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    task_scheduler_service = get_task_runtime_service().scheduler
    from project_model.models import DecisionResult
    from qa_core.ai.models import AICompletionResponse
    from qa_core.ai.registry import AIProviderRegistry

    site = Path(__file__).resolve().parents[3] / "examples" / "demo-shop" / "site"

    class QuietStaticHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path in {"/", "/index.html"}:
                body = (site / "index.html").read_bytes().replace(b"Add to cart", "添加到购物车".encode())
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietStaticHandler, directory=str(site)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    provider_observations = []

    def candidate(candidate_id, action_type, element, *, value=None, expected_effect=""):
        return {
            "candidate_id": candidate_id,
            "action_type": action_type,
            "target_id": element["id"],
            "target": element["name"],
            "value": value,
            "reason_summary": "The current visible control advances the requested shop journey.",
            "expected_effect": expected_effect,
            "evidence": [f"Observed {element['id']} as a visible enabled control."],
        }

    class DemoShopAIProvider:
        async def complete(self, request):
            prompt = json.loads(request.prompt)
            page = prompt["current_page"]
            elements = page["interactive_elements"]
            history = prompt["previous_actions_and_results"]
            provider_observations.append(
                {
                    "url": page["url"],
                    "elements": [
                        (item["id"], item["tag"], item["role"], item["name"], item.get("value")) for item in elements
                    ],
                    "history": history,
                }
            )
            inputs = [item for item in elements if item["tag"] == "input"]
            selects = [item for item in elements if item["tag"] == "select"]
            buttons = [item for item in elements if item["role"] == "button"]
            plan = {
                "subgoals": [
                    "Find the Everyday Tee",
                    "Open its product details",
                    "Choose White and size M",
                    "Add the selected item to cart",
                ],
                "current_subgoal": "Use the currently observed shop controls to advance the goal",
                "candidates": [],
            }

            if inputs and not inputs[0].get("value"):
                target = inputs[0]
                alternative = next(item for item in buttons if item["name"] == "Search")
                plan["candidates"] = [
                    candidate(
                        "search_query",
                        "fill",
                        target,
                        value="Everyday Tee",
                        expected_effect="Search text Everyday Tee is entered.",
                    ),
                    candidate(
                        "submit_search", "click", alternative, expected_effect="The product results are filtered."
                    ),
                ]
                plan["preferred_candidate_id"] = "search_query"
            elif inputs and history and history[-1].get("action") == "fill":
                target = next(item for item in buttons if item["name"] == "Search")
                alternative = next(item for item in buttons if item["name"].startswith("Cart"))
                plan["candidates"] = [
                    candidate(
                        "submit_search", "click", target, expected_effect="Everyday Tee appears in the product results."
                    ),
                    candidate("open_cart", "click", alternative, expected_effect="The shopping cart opens."),
                ]
                plan["preferred_candidate_id"] = "submit_search"
            elif "Color" in " ".join(item["name"] for item in selects):
                color = next((item for item in selects if item["name"] == "Color"), None)
                size = next((item for item in selects if item["name"] == "Size"), None)
                add = next((item for item in buttons if item["name"] in {"Add to cart", "添加到购物车"}), None)
                if color and color.get("value") != "White":
                    target, value, candidate_id = color, "White", "choose_white"
                    alternative = size
                elif size and size.get("value") != "M":
                    target, value, candidate_id = size, "M", "choose_size_m"
                    alternative = add
                else:
                    target, value, candidate_id = add, None, "add_to_cart"
                    alternative = color
                action = "select" if target and target["tag"] == "select" else "click"
                expected = f"{value} is selected." if value else "Cart count increases and an add confirmation appears."
                plan["candidates"] = [
                    candidate(candidate_id, action, target, value=value, expected_effect=expected),
                    candidate(
                        "safe_alternative",
                        "select" if alternative and alternative["tag"] == "select" else "click",
                        alternative,
                        value=(alternative.get("options") or [{}])[0].get("value")
                        if alternative and alternative["tag"] == "select"
                        else None,
                        expected_effect="A different visible variant or shop control is selected.",
                    ),
                ]
                plan["preferred_candidate_id"] = candidate_id
            else:
                target = next(item for item in buttons if item["name"] == "View Everyday Tee")
                alternative = next(item for item in buttons if item["name"].startswith("Cart"))
                plan["candidates"] = [
                    candidate(
                        "open_product",
                        "click",
                        target,
                        expected_effect="Everyday Tee product details and options are visible.",
                    ),
                    candidate("open_cart", "click", alternative, expected_effect="The shopping cart opens."),
                ]
                plan["preferred_candidate_id"] = "open_product"

            return AICompletionResponse(
                invocation_id=f"demo-shop-ai-{len(history)}-{len(elements)}",
                content="{}",
                structured_data=plan,
                provider="test-provider",
                model="fixture-planner",
            )

    class DemoShopDecisionService:
        async def choose(self, request, **_kwargs):
            keys = [option.key for option in request.options]
            assert len(keys) >= 3 and keys[-1] == "abstain"
            return DecisionResult(
                provider="jev",
                model="fixture-jev",
                choice=keys[0],
                confidence=0.95,
                probabilities={keys[0]: 0.95, **{key: 0.05 / (len(keys) - 2) for key in keys[1:-1]}},
            )

    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda *_args, **_kwargs: DemoShopAIProvider())
    monkeypatch.setattr(
        "app.services.task_decision_service.DecisionService", lambda **_kwargs: DemoShopDecisionService()
    )
    await task_scheduler_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "EXPLORE_PAGE",
                "goal": "Search for Everyday Tee, choose White and size M, and 把商品添加到购物车",
                "inputs": {"url": url, "max_browser_actions": 8},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(200):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200, detail.text
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", {
            "failure_reason": body.get("failure_reason"),
            "steps": [(step["key"], step["status"], step.get("error"), step.get("outputs")) for step in body["steps"]],
            "provider_observations": provider_observations,
        }
        agent = next(step for step in body["steps"] if step["key"] == "browser_agent")
        result = agent["outputs"]
        assert result["verified"] is True
        assert result["goal_evidence"]["cart_verified"] is True
        assert result["metrics"]["ai_calls"] == 6
        assert result["metrics"]["jev_decisions"] == 4
        assert result["metrics"]["jev_correct"] == 4
        assert sum(sample["jev_attempted"] for sample in result["decision_samples"]) == 4
        assert result["metrics"]["browser_action_success"] == 6
        assert [item["selected_candidate_id"] for item in result["decision_samples"]] == [
            "search_query",
            "submit_search",
            "open_product",
            "choose_white",
            "choose_size_m",
            "add_to_cart",
        ]
        assert [item["status"] for item in result["actions"]] == ["success"] * 6
        assert result["actions"][-1]["action"] == "add_to_cart"
        assert all(item["ai_provider"] == "test-provider" for item in result["decision_samples"])
        assert result["actions"][-1]["cart_verified"] is True
    finally:
        await task_scheduler_service.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_browser_agent_manual_takeover_resumes_same_recorder_session(client, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    task_scheduler_service = get_task_runtime_service().scheduler
    from app.container import recorder_service
    from project_model.models import DecisionResult
    from qa_core.ai.models import AICompletionResponse
    from qa_core.ai.registry import AIProviderRegistry

    pages = {
        "/": ('<a href="/details">View details</a><a href="/help">Help center</a>', "Start"),
        "/details": ('<a href="/continue">Continue verification</a><a href="/help">Help center</a>', "Details"),
        "/continue": ('<p>Agent reached the pause boundary.</p><a href="/help">Help</a>', "Intermediate"),
        "/manual": ("<h1>Access restored</h1>", "Manual result"),
        "/help": ("<h1>Help</h1>", "Help"),
    }

    class PageHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            content, title = pages.get(self.path, pages["/"])
            body = f"<html><head><title>{title}</title></head><body>{content}</body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    task_id = None
    session_id = None
    observed_urls = []
    pause_statuses = []

    class TakeoverAIProvider:
        async def complete(self, request):
            prompt = json.loads(request.prompt)
            page = prompt["current_page"]
            observed_urls.append(page["url"])
            if page["url"].endswith("/manual"):
                plan = {"goal_status": "completed", "completion_evidence": ["Access restored"]}
            else:
                links = [item for item in page["interactive_elements"] if item["tag"] == "a"]
                destination = "/details" if page["url"].endswith("/") else "/continue"
                target = next(item for item in links if item["href"].endswith(destination))
                alternative = next(item for item in links if item["href"].endswith("/help"))
                if destination == "/continue" and not pause_statuses:
                    response = await client.post(f"/api/tasks/{request.task_id}/pause")
                    pause_statuses.append(response.status_code)
                plan = {
                    "subgoals": ["Reach details", "Pause for manual takeover", "Verify the updated page"],
                    "current_subgoal": "Open the next observed page link",
                    "candidates": [
                        {
                            "candidate_id": f"go_{destination[1:]}",
                            "action_type": "navigate",
                            "target_id": target["id"],
                            "expected_effect": f"The {destination[1:]} page opens.",
                            "reason_summary": "The visible destination advances the verification goal.",
                            "evidence": [target["name"]],
                        },
                        {
                            "candidate_id": "help",
                            "action_type": "navigate",
                            "target_id": alternative["id"],
                            "expected_effect": "The help page opens.",
                            "reason_summary": "This is a visible alternative link.",
                            "evidence": [alternative["name"]],
                        },
                    ],
                    "preferred_candidate_id": f"go_{destination[1:]}",
                }
            return AICompletionResponse(
                invocation_id=f"takeover-ai-{len(observed_urls)}",
                content="{}",
                structured_data=plan,
                provider="test-provider",
                model="fixture-planner",
            )

    class TakeoverDecisionService:
        async def choose(self, request, **_kwargs):
            keys = [option.key for option in request.options]
            return DecisionResult(
                provider="jev",
                model="fixture-jev",
                choice=keys[0],
                confidence=0.95,
                probabilities={keys[0]: 0.95, keys[1]: 0.04, keys[2]: 0.01},
            )

    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda *_args, **_kwargs: TakeoverAIProvider())
    monkeypatch.setattr(
        "app.services.task_decision_service.DecisionService", lambda **_kwargs: TakeoverDecisionService()
    )
    await task_scheduler_service.start()
    try:
        project_response = await client.post("/api/projects", json={"name": "Browser Takeover Test"})
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        session_response = await client.post(
            "/api/recorder/sessions", json={"project_id": project_id, "start_url": url}
        )
        assert session_response.status_code == 200, session_response.text
        session_id = session_response.json()["id"]
        created = await client.post(
            "/api/tasks",
            json={
                "type": "EXPLORE_PAGE",
                "project_id": project_id,
                "goal": "Verify Access restored after manual takeover",
                "inputs": {
                    "url": url,
                    "recorder_session_id": session_id,
                    "observable_text_criteria": ["Access restored"],
                },
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(100):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200, detail.text
            if detail.json()["status"] == "PAUSED":
                break
            assert detail.json()["status"] not in {"FAILED", "BLOCKED"}, detail.text
        assert detail.json()["status"] == "PAUSED", detail.text
        assert pause_statuses == [200]
        from app.persistence.database import async_session_factory

        async with async_session_factory() as db_session:
            task = await db_session.get(TaskORM, task_id)
        owner_id = task.owner_id if task else None
        assert owner_id
        live_session = await recorder_service.get(session_id, owner_id)
        assert live_session is not None and live_session.runtime_session.current_url.endswith("/continue")
        page = await recorder_service.browser_runtime.get_page(live_session.browser_session_id)
        await page.goto(f"{url}manual", wait_until="domcontentloaded")
        resumed = await client.post(f"/api/tasks/{task_id}/resume")
        assert resumed.status_code == 200, resumed.text
        for _ in range(100):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200, detail.text
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        result = next(step for step in body["steps"] if step["key"] == "browser_agent")["outputs"]
        assert result["metrics"]["human_takeovers"] == 1
        assert result["goal_evidence"]["visible_text_criteria"] == ["Access restored"]
        assert observed_urls[-1].endswith("/manual")
        assert any(event["type"] == "browser.human_takeover" for event in body["events"])
        assert result["recorder_session_id"] == session_id
    finally:
        await task_scheduler_service.stop()
        if session_id:
            await client.delete(f"/api/recorder/sessions/{session_id}")
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_create_test_runs_browser_decision_approval_and_generated_pytest(client):
    async def serve_page(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            path = request.split(b" ", 2)[1]
            if path == b"/details":
                title, body_html = "Details", "<h1>Details</h1><p>Details: Account billing available</p>"
            else:
                title, body_html = (
                    "Task Browser Check",
                    "<h1>Help</h1><a href='/details'>View details</a><button>Delete account</button>",
                )
            body = f"<html><head><title>{title}</title></head><body>{body_html}</body></html>".encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    project = await client.post("/api/projects", json={"name": "Create Test Runtime", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    server = await asyncio.start_server(serve_page, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
    steps = [
        {"action": "navigate", "url": url, "description": "Open the observed help page"},
        {
            "action": "click",
            "locator": {"kind": "role", "value": "link", "name": "View details", "exact": True},
            "description": "Open the observed details link",
        },
        {
            "action": "assert_text",
            "locator": {"kind": "text", "value": "Details: Account billing available", "exact": True},
            "value": "Details: Account billing available",
            "description": "Verify details content",
        },
    ]
    await task_scheduler_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "CREATE_TEST",
                "goal": "Verify the help page details link",
                "project_id": project_id,
                "workspace_id": workspace["id"],
                "inputs": {
                    "url": url,
                    "file_path": "tests/test_generated_help.py",
                    "test_name": "test_help_details",
                    "recorded_steps": steps,
                },
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(600):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] == "WAITING":
                break
        waiting = detail.json()
        assert waiting["status"] == "WAITING", waiting.get("failure_reason")
        assert any(step["key"] == "decide" and step["status"] == "COMPLETED" for step in waiting["steps"])
        assert waiting["decisions"] and waiting["decisions"][0]["provider"] != "fake"
        assert any(item["kind"] == "GENERATED_TEST" for item in waiting["artifacts"])

        approval = await client.post(
            f"/api/tasks/{task_id}/approval", json={"approved": True, "comment": "Reviewed generated test"}
        )
        assert approval.status_code == 200, approval.text
        for _ in range(600):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        run_step = next(step for step in body["steps"] if step["key"] == "run")
        assert run_step["outputs"]["status"] == "PASSED"
        assert body["verification"]["verified"] is True
        registered = next(step for step in body["steps"] if step["key"] == "register")
        assert registered["status"] == "COMPLETED"
        case_id = registered["outputs"]["test_case_id"]
        case = await client.get(f"/api/test-cases/{case_id}")
        assert case.status_code == 200 and case.json()["automation_status"] == "AUTOMATED"
        binding = await client.get(f"/api/test-cases/{case_id}/binding")
        assert binding.status_code == 200 and binding.json()["nodeid"] == run_step["outputs"]["nodeids"][0]
        assert any(event["type"] == "decision.created" for event in body["events"])
    finally:
        await task_scheduler_service.stop()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_real_failure_record_repair_approval_and_targeted_rerun(client):
    project = await client.post("/api/projects", json={"name": "Failure Repair Runtime", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_repair_e2e.py"
    test_path.write_text(
        "def test_failure_is_repaired():\n    message = 'old'\n    assert message == 'new'\n",
        encoding="utf-8",
    )

    initial_run = await client.post(
        "/api/runs",
        json={
            "project_id": project_id,
            "workspace_id": project_id,
            "nodeids": ["tests/test_repair_e2e.py::test_failure_is_repaired"],
            "requested_by": "agent-task-e2e",
        },
    )
    assert initial_run.status_code == 201, initial_run.text
    run_id = initial_run.json()["id"]
    for _ in range(150):
        await asyncio.sleep(0.2)
        run = await client.get(f"/api/runs/{run_id}")
        if run.json()["status"] in {"PASSED", "FAILED", "ERROR", "CANCELLED"}:
            break
    assert run.json()["status"] == "FAILED", run.json()
    failures = await client.get(f"/api/failures?project_id={project_id}")
    assert failures.status_code == 200, failures.text
    failure = next(item for item in failures.json() if item["run_id"] == run_id)

    await task_scheduler_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "FIX_FAILURE",
                "goal": "Repair the observed assertion and rerun it",
                "project_id": project_id,
                "workspace_id": workspace["id"],
                "inputs": {"failure_id": failure["id"], "old_locator": "'old'", "proposed_locator": "'new'"},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(150):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"WAITING", "COMPLETED", "FAILED", "BLOCKED"}:
                break
        waiting = detail.json()
        assert waiting["status"] == "WAITING", waiting.get("failure_reason")
        classified = next(step for step in waiting["steps"] if step["key"] == "classify")
        assert classified["outputs"]["classification"] == "ASSERTION_FAILURE"
        diagnosed = next(step for step in waiting["steps"] if step["key"] == "diagnose")
        assert diagnosed["outputs"]["provider"] == "FailureClassifier"
        assert diagnosed["outputs"]["fallback_used"] is True
        assert waiting["evidence"]

        approved = await client.post(
            f"/api/tasks/{task_id}/approval",
            json={"approved": True, "comment": "Reviewed the evidence-backed one-line repair"},
        )
        assert approved.status_code == 200, approved.text
        for _ in range(200):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        assert "message = 'new'" in test_path.read_text(encoding="utf-8")
        target_run = next(step for step in body["steps"] if step["key"] == "target_run")
        assert target_run["outputs"]["status"] == "PASSED"
        verification_run = (await client.get(f"/api/runs/{target_run['outputs']['run_id']}")).json()
        assert verification_run["task_id"] == task_id
        assert verification_run["parent_run_id"] == run_id
        assert verification_run["origin_failure_id"] == failure["id"]
        assert body["verification"]["verified"] is True
    finally:
        await task_scheduler_service.stop()


@pytest.mark.asyncio
async def test_review_task_uses_real_source_and_persists_findings(client):
    project = await client.post("/api/projects", json={"name": "Review Task Runtime", "bootstrap_workspace": True})
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_review_e2e.py"
    test_path.write_text("def test_review_has_an_assertion():\n    assert True\n", encoding="utf-8")

    await task_scheduler_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "REVIEW_TEST",
                "goal": "Review the test for meaningful assertions",
                "workspace_id": workspace["id"],
                "inputs": {"file_path": "tests/test_review_e2e.py"},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(80):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        report = next(step for step in body["steps"] if step["key"] == "report")
        assert report["outputs"]["evidence_backed"] is True
        assert report["outputs"]["finding_count"] >= 1
        assert any(item["type"] == "SourceCode" for item in body["evidence"])
    finally:
        await task_scheduler_service.stop()


@pytest.mark.asyncio
async def test_optimize_task_requires_approval_and_runs_the_proposed_refactor(client):
    project = await client.post("/api/projects", json={"name": "Optimize Task Runtime", "bootstrap_workspace": True})
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_optimize_e2e.py"
    test_path.write_text("def test_total():\n    assert (1 + 1) == 2\n", encoding="utf-8")
    proposal = "def test_total():\n    total = sum([1, 1])\n    assert total == 2\n"

    await task_scheduler_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "OPTIMIZE_TEST",
                "goal": "Improve readability without changing the test result",
                "workspace_id": workspace["id"],
                "inputs": {
                    "file_path": "tests/test_optimize_e2e.py",
                    "nodeids": ["tests/test_optimize_e2e.py::test_total"],
                    "proposed_code": proposal,
                },
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(100):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"WAITING", "COMPLETED", "FAILED", "BLOCKED"}:
                break
        waiting = detail.json()
        assert waiting["status"] == "WAITING", waiting.get("failure_reason")
        assert any(item["kind"] == "PATCH_PROPOSAL" for item in waiting["artifacts"])
        approved = await client.post(
            f"/api/tasks/{task_id}/approval", json={"approved": True, "comment": "Reviewed the focused refactor"}
        )
        assert approved.status_code == 200, approved.text
        for _ in range(150):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        assert "total = sum([1, 1])" in test_path.read_text(encoding="utf-8")
        assert body["verification"]["verified"] is True
    finally:
        await task_scheduler_service.stop()


@pytest.mark.asyncio
async def test_repair_approval_uses_repair_proposal_when_generation_output_exists(client, test_db_session):
    from app.services.task_errors import ApprovalRequired

    project = (
        await client.post("/api/projects", json={"name": "Repair Approval Branch", "bootstrap_workspace": True})
    ).json()
    workspace_id = (await client.get(f"/api/workspaces?project_id={project['id']}")).json()[0]["id"]
    created = await client.post(
        "/api/tasks",
        json={
            "type": "CREATE_TEST",
            "goal": "Use the current repair proposal",
            "project_id": project["id"],
            "workspace_id": workspace_id,
            "inputs": {"url": "http://127.0.0.1:1/"},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        repo = TaskRepository(session)
        steps = await repo.steps_for_task(task_id)
        assert task is not None
        approval = next(step for step in steps if step.key == "approval")
        await repo.update_step(approval.id, key="repair_approval")
        task.current_step_id = approval.id
        task.status = TaskStatus.RUNNING.value
        await session.commit()
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)

    outputs = {
        "generate": {"target_file": "tests/generated.py", "suggested_code": "def test_generated(): pass\n"},
        "repair": {"target_file": "tests/repaired.py", "suggested_code": "def test_repaired(): pass\n"},
    }
    with pytest.raises(ApprovalRequired):
        await task_execution_service._request_approval(task, outputs)
    detail = await task_command_service.get(task_id)
    assert detail is not None
    assert detail.context["pending_change_summary"]["file_path"] == "tests/repaired.py"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["repair", "refactor", "generate"])
async def test_approval_preserves_source_modified_while_waiting(client, test_db_session, kind):
    from app.services.task_errors import ApprovalRequired, TaskBlocked
    from app.services.workspace_service import WorkspaceService

    project = (
        await client.post("/api/projects", json={"name": "Approval conflict", "bootstrap_workspace": True})
    ).json()
    workspace_id = project["id"]
    path = "tests/test_approved.py"
    original = None if kind == "generate" else "def test_before():\n    assert True\n"
    source = WorkspaceService()
    if original is not None:
        await source.write_file(workspace_id, path, original)
    created = (
        await client.post(
            "/api/tasks",
            json={
                "type": "EXPLORE_PAGE",
                "goal": "Approval guard",
                "project_id": workspace_id,
                "workspace_id": workspace_id,
                "inputs": {"url": "http://127.0.0.1:1/"},
            },
        )
    ).json()
    async with test_db_session() as session:
        task = await session.get(TaskORM, created["id"])
    change = {"target_file": path, "file_path": path, "suggested_code": "def test_after():\n    assert True\n"}
    if original is not None:
        change["old_code"] = original
    outputs = {kind: change, "approval": {"approved": True}}
    with pytest.raises(ApprovalRequired):
        await task_execution_service._request_approval(task, outputs)
    user_edit = "def test_user_edit():\n    assert True\n"
    await source.write_file(workspace_id, path, user_edit)
    apply = task_execution_service._apply_repair if kind == "repair" else task_execution_service._write_generated
    with pytest.raises(TaskBlocked, match="Existing edits were preserved"):
        await apply(task, outputs)
    assert await source.read_file(workspace_id, path) == user_edit


@pytest.mark.asyncio
async def test_approval_diff_exposes_tail_and_keeps_complete_artifact(client, test_db_session):
    from app.services.task_errors import ApprovalRequired
    from app.services.workspace_service import WorkspaceService

    project = (await client.post("/api/projects", json={"name": "Diff tail", "bootstrap_workspace": True})).json()
    wid = project["id"]
    path = "tests/test_tail.py"
    original = "# " + "unchanged" * 2000 + "\ndef test_tail():\n    assert 1 == 1\n"
    updated = original.replace("1 == 1", "2 == 2")
    await WorkspaceService().write_file(wid, path, original)
    created = (
        await client.post(
            "/api/tasks",
            json={
                "type": "EXPLORE_PAGE",
                "goal": "Review tail",
                "project_id": wid,
                "workspace_id": wid,
                "inputs": {"url": "http://127.0.0.1:1/"},
            },
        )
    ).json()
    async with test_db_session() as session:
        task = await session.get(TaskORM, created["id"])
    outputs = {
        "refactor": {"target_file": path, "suggested_code": updated, "old_code": original},
        "approval": {"approved": True},
    }
    with pytest.raises(ApprovalRequired):
        await task_execution_service._request_approval(task, outputs)
    detail = await task_command_service.get(task.id)
    summary = detail.context["pending_change_summary"]
    assert summary["preview_truncated"] is True
    assert summary["preview"].startswith("--- a/")
    artifact = next(item for item in detail.artifacts if item.artifact_id == summary["artifact_id"])
    response = await client.get(f"/api/artifacts/{artifact.artifact_id}/download")
    assert response.status_code == 200
    assert "-    assert 1 == 1" in response.text and "+    assert 2 == 2" in response.text
    await task_execution_service._write_generated(task, outputs)
    assert await WorkspaceService().read_file(wid, path) == updated


@pytest.mark.asyncio
async def test_create_test_assertion_bypass_flag_is_checked_during_source_validation():
    task = SimpleNamespace(
        type=TaskType.CREATE_TEST.value,
        inputs={"assertion_bypass_check": True},
        workspace_id="project",
    )

    async def evidence(*_args, **_kwargs):
        return "evidence-id"

    service = TaskCodeGenerationService(
        SimpleNamespace(input=lambda item, key, default=None: item.inputs.get(key, default), evidence=evidence)
    )
    outputs = {
        "generate": {
            "target_file": "tests/test_generated.py",
            "suggested_code": "def test_generated():\n    assert True\n",
        }
    }

    with pytest.raises(TaskBlocked, match="constant-true assertion"):
        await service._validate_generated(task, outputs)
