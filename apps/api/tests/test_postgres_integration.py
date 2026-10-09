"""Full-domain integration suite for PostgreSQL, the production backend.

Skipped unless ``AI_QA_TEST_DATABASE_URL`` points at PostgreSQL (see
``pytest_collection_modifyitems`` in ``conftest``). It drives the real HTTP API
through the ``client`` fixture and the repositories directly, covering Project →
Requirement → TestDesign → TestCase → AutomationBinding → TestRun →
TestExecution → FailureRecord → AIInvocation → RunnerProfile → ExecutionJob →
Worker → Artifact → Release → User/Team/ApiKey → SecurityAudit →
IntegrationAudit, plus the flaky/history analytics and the quality/coverage
aggregation. Assertions check concrete values rather than status codes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from app.repositories.ai_repo import AIRepository
from app.repositories.artifact_repo import ArtifactRepository
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.integration_audit_repo import IntegrationAuditRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.runner_profile_repo import RunnerProfileRepository
from app.repositories.security_audit_repo import SecurityAuditRepository
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.job_queue_service import JobQueueService
from httpx import AsyncClient
from project_model.models import RunStatus, TestRunCreate

pytestmark = [pytest.mark.postgres, pytest.mark.integration]

CHECKOUT_NODEID = "tests/test_checkout.py::test_verify_checkout_total"
TIMING_ISSUE = "TIMING_ISSUE"


async def _create_project(client: AsyncClient, name: str, bootstrap: bool = False) -> dict:
    response = await client.post("/api/projects", json={"name": name, "bootstrap_workspace": bootstrap})
    assert response.status_code == 201
    return response.json()


async def _create_test_case(client: AsyncClient, project_id: str, **overrides) -> dict:
    payload = {"project_id": project_id, "title": "Test case", "priority": "P1", "automation_status": "MANUAL"}
    payload.update(overrides)
    response = await client.post("/api/test-cases", json=payload)
    assert response.status_code == 201
    return response.json()


async def _create_run(test_db_session, project_id: str, nodeids: list[str]) -> str:
    async with test_db_session() as session:
        run = await TestRunRepository(session).create_run(
            TestRunCreate(project_id=project_id, workspace_id=project_id, nodeids=nodeids)
        )
        await session.commit()
        return run.id


async def test_project_to_release_domain_graph(client: AsyncClient, test_db_session) -> None:
    project = await _create_project(client, "Postgres Domain Suite", bootstrap=True)
    project_id = project["id"]
    assert datetime.fromisoformat(project["created_at"]).tzinfo is not None

    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project_id,
                "title": "Checkout requirement",
                "description": "Cart checkout must total correctly",
                "acceptance_criteria": "Totals include coupon discounts",
            },
        )
    ).json()
    requirement_id = requirement["id"]
    assert requirement["status"] == "DRAFT"

    design = (
        await client.post(
            "/api/test-designs",
            json={
                "requirement_id": requirement_id,
                "title": "Coupon design",
                "category": "FUNCTIONAL",
                "description": "Cover coupon boundaries",
                "risk": "High",
            },
        )
    ).json()
    design_id = design["id"]
    assert design["category"] == "FUNCTIONAL"

    automated_case = await _create_test_case(
        client,
        project_id,
        requirement_id=requirement_id,
        test_design_id=design_id,
        title="Verify checkout total",
        preconditions="Cart contains two items",
        steps=["Open cart", "Apply coupon"],
        expected_result="Total is discounted",
        priority="P1",
        tags=["checkout", "coupon"],
    )
    automated_case_id = automated_case["id"]
    assert automated_case["steps"] == ["Open cart", "Apply coupon"]
    assert automated_case["tags"] == ["checkout", "coupon"]

    manual_case = await _create_test_case(
        client, project_id, title="Manual signup check", priority="P0", automation_status="MANUAL"
    )
    assert manual_case["priority"] == "P0"
    assert manual_case["automation_status"] == "MANUAL"

    binding_response = await client.post(
        f"/api/test-cases/{automated_case_id}/binding",
        json={
            "test_case_id": automated_case_id,
            "workspace_id": project_id,
            "nodeid": CHECKOUT_NODEID,
            "file_path": "tests/test_checkout.py",
            "framework": "playwright_python",
            "status": "ACTIVE",
        },
    )
    assert binding_response.status_code == 200
    binding = binding_response.json()
    assert binding["nodeid"] == CHECKOUT_NODEID
    assert binding["file_path"] == "tests/test_checkout.py"
    assert binding["status"] == "ACTIVE"
    assert datetime.fromisoformat(binding["created_at"]).tzinfo is not None

    fetched_case = (await client.get(f"/api/test-cases/{automated_case_id}")).json()
    assert fetched_case["automation_status"] == "AUTOMATED"

    # --- the same rows read back through the repositories ---
    async with test_db_session() as session:
        project_orm = await ProjectRepository(session).get_by_id(project_id)
        assert project_orm.name == "Postgres Domain Suite"
        assert project_orm.created_at.tzinfo is not None

        requirement_orm = await RequirementRepository(session).get_by_id(requirement_id)
        assert requirement_orm.title == "Checkout requirement"
        assert requirement_orm.acceptance_criteria == "Totals include coupon discounts"

        design_orm = await TestDesignRepository(session).get_by_id(design_id)
        assert design_orm.requirement_id == requirement_id
        assert design_orm.risk == "High"

        case_orm = await TestCaseRepository(session).get_by_id(automated_case_id)
        assert case_orm.steps == ["Open cart", "Apply coupon"]
        assert case_orm.tags == ["checkout", "coupon"]
        assert case_orm.automation_status == "AUTOMATED"

        binding_orm = await AutomationBindingRepository(session).get_by_test_case_id(automated_case_id)
        assert binding_orm.nodeid == CHECKOUT_NODEID
        assert binding_orm.status == "ACTIVE"

    # --- quality / coverage aggregation ---
    coverage = (await client.get(f"/api/quality/coverage?project_id={project_id}")).json()
    assert coverage["total_requirements"] == 1
    assert coverage["covered_requirements"] == 1
    assert coverage["requirement_coverage_pct"] == 100.0
    assert coverage["total_test_cases"] == 2
    assert coverage["manual_cases"] == 1
    assert coverage["automated_cases"] == 1
    assert coverage["automation_coverage_pct"] == 50.0
    assert coverage["executed_cases_recent"] == 0
    assert coverage["execution_coverage_pct"] == 0.0
    assert len(coverage["requirement_details"]) == 1
    detail = coverage["requirement_details"][0]
    assert detail["requirement_id"] == requirement_id
    assert detail["title"] == "Checkout requirement"
    assert detail["test_design_count"] == 1
    assert detail["test_case_count"] == 1
    assert detail["automated_case_count"] == 1
    assert detail["coverage_percentage"] == 100.0
    assert detail["has_automation"] is True

    # --- release + gate evaluation ---
    release_response = await client.post(
        "/api/releases",
        json={
            "project_id": project_id,
            "version": "v2.0.0",
            "name": "Postgres Release",
            "description": "Domain graph release",
            "pass_rate_threshold": 90.0,
            "max_allowed_flaky": 0,
        },
    )
    assert release_response.status_code == 201
    release = release_response.json()
    assert release["status"] == "PLANNED"
    assert release["version"] == "v2.0.0"

    gate = (await client.post(f"/api/releases/{release['id']}/gate-evaluate")).json()
    assert gate["can_release"] is False
    assert gate["verdict"] == "BLOCKED"
    assert gate["unautomated_p0_count"] == 1
    assert gate["unautomated_p0_met"] is False
    assert gate["flaky_count"] == 0
    assert gate["flaky_met"] is True
    assert gate["pass_rate"] == 0.0
    assert gate["pass_rate_met"] is False
    # 100 - (1 unautomated P0 * 15)
    assert gate["quality_score"] == 85.0
    assert any("unautomated P0" in blocker for blocker in gate["blockers"])

    persisted_release = (await client.get(f"/api/releases/{release['id']}")).json()
    assert persisted_release["status"] == "BLOCKED"
    assert persisted_release["quality_score"] == 85.0
    assert persisted_release["blockers"] == gate["blockers"]


async def test_run_execution_failure_and_history_analytics(client: AsyncClient, test_db_session) -> None:
    project = await _create_project(client, "Postgres Analytics Suite")
    project_id = project["id"]

    # Anchored to now: the dashboard reports 'today', so seeding a fixed past date would make
    # those assertions either wrong or conditionally skipped.
    base = datetime.now(timezone.utc) - timedelta(minutes=5)
    statuses = [RunStatus.PASSED, RunStatus.FAILED, RunStatus.PASSED, RunStatus.FAILED, RunStatus.PASSED]

    async with test_db_session() as session:
        run_repo = TestRunRepository(session)
        run = await run_repo.create_run(
            TestRunCreate(
                project_id=project_id,
                workspace_id=project_id,
                nodeids=[CHECKOUT_NODEID, f"{CHECKOUT_NODEID}_b", f"{CHECKOUT_NODEID}_c"],
                browser="chromium",
            )
        )
        await run_repo.update_run_status(
            run.id,
            RunStatus.PASSED,
            passed=2,
            failed=1,
            skipped=0,
            duration_ms=1500.0,
            started_at=base,
            finished_at=base + timedelta(seconds=30),
        )
        executions = []
        for offset, status in enumerate(statuses):
            execution = await run_repo.add_execution(
                run.id,
                CHECKOUT_NODEID,
                status,
                duration_ms=100.0,
                retry_count=1 if offset == 4 else 0,
                failure_category=TIMING_ISSUE if status is RunStatus.FAILED else None,
                error_message="Locator timed out" if status is RunStatus.FAILED else None,
            )
            execution.started_at = base + timedelta(minutes=offset)
            execution.finished_at = base + timedelta(minutes=offset, seconds=5)
            executions.append(execution)
        await session.flush()

        first_failure = await run_repo.create_failure_record(
            run_id=run.id,
            execution_id=executions[1].id,
            test_nodeid=CHECKOUT_NODEID,
            test_name="test_verify_checkout_total",
            classification=TIMING_ISSUE,
            exception_type="TimeoutError",
            error_message="Locator timed out after 5000ms",
            stack_trace="Traceback ...",
            console_logs=["waiting for selector"],
            suggested_action="Increase wait",
        )
        second_failure = await run_repo.create_failure_record(
            run_id=run.id,
            execution_id=executions[3].id,
            test_nodeid=CHECKOUT_NODEID,
            test_name="test_verify_checkout_total",
            classification=TIMING_ISSUE,
            exception_type="TimeoutError",
            error_message="Locator timed out again",
            stack_trace="Traceback ...",
        )
        artifact = await run_repo.add_external_artifact(
            run.id, "allure-report", "ALLURE", "https://ci.example/allure/index.html", {"suite": "checkout"}
        )
        assert artifact.name == "allure-report"
        await session.commit()
        run_id, first_failure_id, second_failure_id = run.id, first_failure.id, second_failure.id

    # --- run + executions read back through the repository ---
    async with test_db_session() as session:
        run_repo = TestRunRepository(session)
        stored_run = await run_repo.get_by_id(run_id)
        assert stored_run.status == "PASSED"
        assert stored_run.total == 3
        assert stored_run.passed == 2
        assert stored_run.failed == 1
        assert stored_run.duration_ms == 1500.0
        assert stored_run.started_at.tzinfo is not None
        assert stored_run.finished_at.tzinfo is not None
        assert stored_run.started_at == base
        assert [item.name for item in stored_run.external_artifacts] == ["allure-report"]

        listed = await run_repo.list_executions(run_id)
        assert [execution.id for execution in listed] == [execution.id for execution in executions]
        assert [execution.status for execution in listed] == [status.value for status in statuses]
        assert listed[0].started_at == base
        assert listed[0].started_at.tzinfo is not None

        stored_failure = await run_repo.get_failure_by_id(first_failure_id)
        assert stored_failure.classification == TIMING_ISSUE
        assert stored_failure.error_message == "Locator timed out after 5000ms"
        assert stored_failure.console_logs == ["waiting for selector"]
        assert stored_failure.created_at.tzinfo is not None

    # --- history / flaky analytics ---
    history_repo = RunHistoryRepository(test_db_session)
    newest_first = await history_repo.get_test_executions(CHECKOUT_NODEID, project_id=project_id)
    assert [execution.id for execution in newest_first] == [execution.id for execution in reversed(executions)]

    history = (await client.get(f"/api/flaky/history?nodeid={CHECKOUT_NODEID}&project_id={project_id}")).json()
    assert history["nodeid"] == CHECKOUT_NODEID
    assert history["project_id"] == project_id
    assert [item["id"] for item in history["executions"]] == [execution.id for execution in reversed(executions)]
    assert history["executions"][0]["status"] == "PASSED"
    assert history["trend"] == {
        "sample_count": 5,
        "pass_count": 3,
        "fail_count": 2,
        "skip_count": 0,
        "average_duration_ms": 100.0,
        "p95_duration_ms": 100.0,
        "retry_count": 1,
        "failure_categories": {TIMING_ISSUE: 2},
    }
    flaky_score = history["flaky_score"]
    assert flaky_score["classification"] == "LIKELY_FLAKY"
    assert flaky_score["sample_count"] == 5
    assert flaky_score["failure_rate"] == 0.4
    assert flaky_score["alternation_rate"] == 1.0
    assert flaky_score["rerun_recovery_rate"] == 0.5
    assert flaky_score["recent_instability"] == 0.4
    assert flaky_score["score"] == 0.705
    assert flaky_score["main_failure_category"] == TIMING_ISSUE
    assert datetime.fromisoformat(flaky_score["last_failure_at"]) == base + timedelta(minutes=3)

    flaky_list = (await client.get(f"/api/flaky?project_id={project_id}")).json()
    assert len(flaky_list) == 1
    assert flaky_list[0]["nodeid"] == CHECKOUT_NODEID
    assert flaky_list[0]["test_name"] == "test_verify_checkout_total"
    assert flaky_list[0]["project_id"] == project_id
    assert flaky_list[0]["flaky_score"]["score"] == 0.705

    # --- failures API + recurrence ---
    failures = (await client.get("/api/failures")).json()
    by_id = {failure["id"]: failure for failure in failures}
    assert set(by_id) == {first_failure_id, second_failure_id}
    assert by_id[first_failure_id]["test_nodeid"] == CHECKOUT_NODEID
    assert by_id[first_failure_id]["test_name"] == "test_verify_checkout_total"
    assert by_id[first_failure_id]["classification"] == TIMING_ISSUE
    assert by_id[first_failure_id]["console_logs"] == ["waiting for selector"]
    assert by_id[first_failure_id]["run_id"] == run_id

    recurrence = (await client.get(f"/api/failures/{first_failure_id}/recurrence")).json()
    assert [item["failure_id"] for item in recurrence] == [second_failure_id]
    assert recurrence[0]["classification"] == TIMING_ISSUE
    assert recurrence[0]["error_message"] == "Locator timed out again"

    # --- dashboard intelligence ---
    dashboard = (await client.get("/api/dashboard/stats")).json()
    assert dashboard["total_projects"] == 1
    assert dashboard["total_requirements"] == 0
    assert dashboard["total_test_cases"] == 0
    assert dashboard["total_runs"] == 1
    assert dashboard["total_failures"] == 2
    assert dashboard["flaky_tests_count"] == 1
    assert dashboard["rerun_recovery_count"] == 1
    assert dashboard["average_test_duration_ms"] == 1500.0
    assert dashboard["runs_today"] == 1
    assert dashboard["tests_executed_today"] == 3
    assert dashboard["pass_rate_today"] == 66.7

    # --- execution coverage needs test cases linked to executed nodeids ---
    await _create_test_case(
        client, project_id, title="Automated checkout total", priority="P1", automation_status="AUTOMATED"
    )
    await _create_test_case(client, project_id, title="Manual coupon check", priority="P1", automation_status="MANUAL")
    coverage = (await client.get(f"/api/quality/coverage?project_id={project_id}")).json()
    assert coverage["total_test_cases"] == 2
    assert coverage["automated_cases"] == 1
    assert coverage["executed_cases_recent"] == 1
    assert coverage["execution_coverage_pct"] == 50.0

    # --- AI invocation telemetry ---
    await AIRepository(test_db_session).record_invocation(
        task="requirement_analysis",
        provider="openai",
        model="gpt-4o",
        duration_ms=1234.5,
        input_tokens=1200,
        output_tokens=340,
        prompt_version="v2",
    )
    usage = (await client.get("/api/ai/usage")).json()
    assert usage["total_requests"] == 1
    assert usage["total_input_tokens"] == 1200
    assert usage["total_output_tokens"] == 340
    assert usage["invocations"][0]["task"] == "requirement_analysis"
    assert usage["invocations"][0]["model"] == "gpt-4o"
    assert usage["invocations"][0]["fallback_used"] is False
    assert datetime.fromisoformat(usage["invocations"][0]["started_at"]).tzinfo is not None


async def test_identity_workers_jobs_artifacts_and_audits(client: AsyncClient, test_db_session) -> None:
    # --- identity: user, team, api key, security audit ---
    login = await client.post("/api/auth/login", json={"email": "admin@ai-qa.local", "password": "adminpassword"})
    assert login.status_code == 200
    login_body = login.json()
    assert "security:admin" in login_body["permissions"]
    admin_id = login_body["user"]["id"]
    headers = {"Authorization": f"Bearer {login_body['access_token']}"}

    user = (
        await client.post(
            "/api/users",
            json={"email": "dana@company.com", "full_name": "Dana Scully", "role": "QA_LEAD", "password": "secret"},
            headers=headers,
        )
    ).json()
    assert user["role"] == "QA_LEAD"
    assert user["is_active"] is True

    team = (
        await client.post("/api/teams", json={"name": "Platform QA", "description": "Core platform"}, headers=headers)
    ).json()
    member = (
        await client.post(
            f"/api/teams/{team['id']}/members", json={"user_id": user["id"], "role": "LEAD"}, headers=headers
        )
    ).json()
    assert member["role"] == "LEAD"
    assert member["user_id"] == user["id"]

    team_detail = (await client.get(f"/api/teams/{team['id']}", headers=headers)).json()
    assert team_detail["member_count"] == 1
    assert team_detail["members"][0]["user_id"] == user["id"]
    assert datetime.fromisoformat(team_detail["members"][0]["created_at"]).tzinfo is not None

    api_key = (
        await client.post("/api/auth/api-keys", json={"name": "CI key", "user_id": user["id"]}, headers=headers)
    ).json()
    assert api_key["raw_api_key"].startswith("aqp_live_")
    assert api_key["key_prefix"] == api_key["raw_api_key"][:12]
    assert api_key["user_id"] == admin_id

    key_profile = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {api_key['raw_api_key']}"})
    assert key_profile.status_code == 200
    assert key_profile.json()["user"]["id"] == admin_id

    listed_keys = (await client.get("/api/auth/api-keys", headers=headers)).json()
    assert [item["key_prefix"] for item in listed_keys] == [api_key["key_prefix"]]

    security_logs = (await client.get("/api/audit/security")).json()
    actions = {entry["action"] for entry in security_logs}
    assert {"LOGIN", "USER_CREATE"} <= actions
    async with test_db_session() as session:
        stored_logs = await SecurityAuditRepository().list_logs(action="LOGIN", session=session)
        assert stored_logs[0].actor_email == "admin@ai-qa.local"
        assert stored_logs[0].status == "SUCCESS"
        assert stored_logs[0].created_at.tzinfo is not None

    # --- integration audit ---
    async with test_db_session() as session:
        await IntegrationAuditRepository(session).record(
            system="jira", action="import_requirement", target_id="QA-101", details={"imported": 2}
        )
        await session.commit()

    integration_entries = (await client.get("/api/audit/integrations?system=JIRA")).json()
    assert len(integration_entries) == 1
    assert integration_entries[0]["system"] == "JIRA"
    assert integration_entries[0]["action"] == "IMPORT_REQUIREMENT"
    assert integration_entries[0]["target_id"] == "QA-101"
    assert integration_entries[0]["details"] == {"imported": 2}
    assert datetime.fromisoformat(integration_entries[0]["created_at"]).tzinfo is not None

    # --- runner profile ---
    runner = (
        await client.post("/api/runners", json={"name": "Local runner", "type": "LOCAL", "config": {"workers": 2}})
    ).json()
    assert runner["type"] == "LOCAL"
    assert runner["enabled"] is True
    assert runner["config"] == {"workers": 2}
    assert datetime.fromisoformat(runner["created_at"]).tzinfo is not None

    fetched_runner = (await client.get(f"/api/runners/{runner['id']}")).json()
    assert fetched_runner["name"] == "Local runner"
    health = (await client.get(f"/api/runners/{runner['id']}/health")).json()
    assert health["type"] == "LOCAL"
    # The local backend reports availability from its own probe, so an unknown status is a defect.
    assert health["status"] == "AVAILABLE"

    runner_orm = await RunnerProfileRepository().get_by_id(runner["id"])
    assert runner_orm.type == "LOCAL"
    assert runner_orm.config == {"workers": 2}
    assert runner_orm.created_at.tzinfo is not None

    # --- workers, execution jobs, cluster status ---
    worker = (
        await client.post(
            "/api/workers",
            json={
                "hostname": "pg-node-1",
                "ip_address": "10.1.0.5",
                "status": "ONLINE",
                "browsers": ["chromium"],
                "max_concurrency": 8,
            },
        )
    ).json()
    assert worker["status"] == "ONLINE"
    assert worker["max_concurrency"] == 8

    heartbeat = (
        await client.post(f"/api/workers/{worker['id']}/heartbeat", json={"status": "BUSY", "current_load": 4})
    ).json()
    assert heartbeat["status"] == "BUSY"
    assert heartbeat["current_load"] == 4
    assert datetime.fromisoformat(heartbeat["last_heartbeat_at"]).tzinfo is not None

    project = await _create_project(client, "Postgres Distributed Suite")
    run_id = await _create_run(test_db_session, project["id"], ["tests/a.py::test_one"])

    job_service = JobQueueService(repository_scope=TaskRepositoryScopeFactory())
    claimed_source = await job_service.enqueue_job(
        run_id=run_id,
        project_id=project["id"],
        workspace_id=project["id"],
        nodeids=["tests/a.py::test_one", "tests/a.py::test_two"],
        browser="chromium",
        priority=25,
    )
    queued_job = await job_service.enqueue_job(
        run_id=run_id,
        project_id=project["id"],
        workspace_id=project["id"],
        nodeids=["tests/a.py::test_three"],
        browser="chromium",
        priority=10,
    )
    failing_job = await job_service.enqueue_job(
        run_id=run_id,
        project_id=project["id"],
        workspace_id=project["id"],
        nodeids=["tests/a.py::test_four"],
        browser="chromium",
        priority=5,
    )

    claimed = await job_service.dispatch_next_job(worker_id=worker["id"], browser="chromium")
    assert claimed is not None
    assert claimed.id == claimed_source.id
    assert claimed.status.value == "ASSIGNED"
    assert claimed.assigned_worker_id == worker["id"]

    completed = await job_service.complete_job(claimed.id, duration_ms=1250.0)
    assert completed is not None
    assert completed.status.value == "COMPLETED"
    assert completed.duration_ms == 1250.0

    failed = await job_service.fail_job(failing_job.id, error_message="worker crashed")
    assert failed is not None
    assert failed.status.value == "FAILED"
    assert failed.error_message == "worker crashed"

    jobs = (await client.get(f"/api/jobs?project_id={project['id']}")).json()
    jobs_by_id = {job["id"]: job for job in jobs}
    assert set(jobs_by_id) == {claimed_source.id, queued_job.id, failing_job.id}
    assert jobs_by_id[claimed_source.id]["status"] == "COMPLETED"
    assert jobs_by_id[claimed_source.id]["duration_ms"] == 1250.0
    assert jobs_by_id[claimed_source.id]["assigned_worker_id"] == worker["id"]
    assert datetime.fromisoformat(jobs_by_id[claimed_source.id]["finished_at"]).tzinfo is not None
    assert jobs_by_id[queued_job.id]["status"] == "QUEUED"
    assert jobs_by_id[queued_job.id]["priority"] == 10
    assert jobs_by_id[failing_job.id]["status"] == "FAILED"
    assert jobs_by_id[failing_job.id]["error_message"] == "worker crashed"
    assert jobs_by_id[claimed_source.id]["nodeids"] == ["tests/a.py::test_one", "tests/a.py::test_two"]

    cluster = (await client.get("/api/workers/cluster-status")).json()
    assert cluster["total_workers"] == 1
    assert cluster["busy_workers"] == 1
    assert cluster["online_workers"] == 0
    assert cluster["offline_workers"] == 0
    assert cluster["total_concurrency_capacity"] == 8
    assert cluster["used_concurrency"] == 4
    assert cluster["queued_jobs_count"] == 1
    assert cluster["running_jobs_count"] == 0

    # --- artifact upload / download ---
    content = b"<html><body>checkout report</body></html>"
    upload = await client.post("/api/artifacts/upload", files={"file": ("report.html", content, "text/html")})
    assert upload.status_code == 201
    artifact = upload.json()
    assert artifact["filename"] == "report.html"
    assert artifact["size_bytes"] == len(content)
    assert artifact["content_type"] == "text/html"
    assert artifact["storage_type"] == "LOCAL"
    assert artifact["storage_url"] == f"/api/artifacts/{artifact['artifact_id']}/download"

    info = (await client.get(f"/api/artifacts/{artifact['artifact_id']}/info")).json()
    assert info["filename"] == "report.html"
    assert info["expires_in_seconds"] == 3600

    download = await client.get(f"/api/artifacts/{artifact['artifact_id']}/download")
    assert download.status_code == 200
    assert download.content == content

    async with test_db_session() as session:
        artifact_orm = await ArtifactRepository().get_by_id(artifact["artifact_id"], session=session)
        assert artifact_orm.storage_type == "LOCAL"
        assert artifact_orm.size_bytes == len(content)
        assert artifact_orm.created_at.tzinfo is not None
