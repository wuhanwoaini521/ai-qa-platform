from __future__ import annotations

import pytest
from app.persistence.models import (
    AutomationBindingORM,
    FailureRecordORM,
)
from app.persistence.models import (
    TestCaseORM as CaseORM,
)
from app.persistence.models import (
    TestExecutionORM as ExecutionORM,
)
from app.persistence.models import (
    TestRunORM as RunORM,
)
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("execution_status", "binding_status", "workspace_matches", "nodeid_matches", "expected"),
    [
        ("PASSED", "ACTIVE", True, True, 1),
        ("FAILED", "ACTIVE", True, True, 1),
        ("ERROR", "VALIDATED", True, True, 1),
        ("SKIPPED", "ACTIVE", True, True, 0),
        ("QUEUED", "ACTIVE", True, True, 0),
        ("CANCELLED", "ACTIVE", True, True, 0),
        ("PASSED", "DRAFT", True, True, 0),
        ("PASSED", "ACTIVE", False, True, 0),
        ("PASSED", "ACTIVE", True, False, 0),
    ],
)
async def test_execution_coverage_requires_recorded_binding_target(
    client, test_db_session, execution_status, binding_status, workspace_matches, nodeid_matches, expected
):
    project = (
        await client.post("/api/projects", json={"name": "Coverage evidence", "bootstrap_workspace": False})
    ).json()
    project_id = project["id"]
    nodeid = "tests/test_checkout.py::test_checkout"
    async with test_db_session() as session:
        session.add_all(
            [
                CaseORM(id="case_bound", project_id=project_id, title="checkout", automation_status="AUTOMATED"),
                CaseORM(id="case_unbound", project_id=project_id, title="checkout", automation_status="AUTOMATED"),
                CaseORM(id="case_manual", project_id=project_id, title="checkout", automation_status="MANUAL"),
            ]
        )
        await session.flush()
        session.add(
            AutomationBindingORM(
                id="binding_coverage",
                test_case_id="case_bound",
                workspace_id=project_id,
                nodeid=nodeid,
                file_path="tests/test_checkout.py",
                status=binding_status,
            )
        )
        session.add(
            RunORM(
                id="run_coverage",
                project_id=project_id,
                workspace_id=project_id if workspace_matches else "other_workspace",
                status="FAILED",
            )
        )
        await session.flush()
        session.add(
            ExecutionORM(
                id="execution_coverage",
                run_id="run_coverage",
                nodeid=nodeid if nodeid_matches else "tests/test_other.py::test_checkout",
                status=execution_status,
            )
        )
        await session.commit()

    response = await client.get(f"/api/quality/coverage?project_id={project_id}")
    assert response.status_code == 200, response.text
    coverage = response.json()
    assert coverage["total_test_cases"] == 3
    assert coverage["executed_cases_recent"] == expected
    assert coverage["execution_coverage_pct"] == (33.3 if expected else 0.0)


@pytest.mark.asyncio
async def test_quality_risk_and_coverage_exclude_other_projects(client, test_db_session):
    projects = [
        (await client.post("/api/projects", json={"name": name, "bootstrap_workspace": False})).json()["id"]
        for name in ("Healthy project", "Failing project")
    ]
    nodeid = "tests/test_shared.py::test_shared"
    async with test_db_session() as session:
        for index, project_id in enumerate(projects):
            session.add(
                CaseORM(id=f"case_{index}", project_id=project_id, title="shared", automation_status="AUTOMATED")
            )
        await session.flush()
        for index, project_id in enumerate(projects):
            session.add(
                AutomationBindingORM(
                    id=f"binding_{index}",
                    test_case_id=f"case_{index}",
                    workspace_id=project_id,
                    nodeid=nodeid,
                    file_path="tests/test_shared.py",
                    status="ACTIVE",
                )
            )
        session.add(RunORM(id="foreign_run", project_id=projects[1], workspace_id=projects[1], status="FAILED"))
        await session.flush()
        session.add(ExecutionORM(id="foreign_execution", run_id="foreign_run", nodeid=nodeid, status="FAILED"))
        await session.flush()
        session.add(
            FailureRecordORM(
                id="foreign_failure",
                run_id="foreign_run",
                execution_id="foreign_execution",
                test_nodeid=nodeid,
                test_name="shared",
                classification="APPLICATION_BUG",
                error_message="Other project's private failure evidence",
            )
        )
        await session.commit()

    healthy = (await client.get(f"/api/quality/risk-matrix?project_id={projects[0]}")).json()
    assert healthy["overall_quality_score"] == 100.0
    assert healthy["risks"] == []
    failing = (await client.get(f"/api/quality/risk-matrix?project_id={projects[1]}")).json()
    assert failing["overall_quality_score"] == 95.0
    assert any(item["id"] == "risk_fail_foreign_failure" for item in failing["risks"])
    for project_id, expected in zip(projects, (0, 1)):
        coverage = (await client.get(f"/api/quality/coverage?project_id={project_id}")).json()
        assert coverage["executed_cases_recent"] == expected


@pytest.mark.asyncio
async def test_quality_coverage_and_risk_matrix(client: AsyncClient):
    # 1. Create project
    proj_resp = await client.post(
        "/api/projects",
        json={"name": "Quality Intelligence Test Project"},
    )
    assert proj_resp.status_code in (200, 201)
    project_id = proj_resp.json()["id"]

    # 2. Add requirement
    req_resp = await client.post(
        "/api/requirements",
        json={
            "project_id": project_id,
            "title": "User Checkout Flow",
            "description": "Checkout cart items",
            "acceptance_criteria": "1. Price calculation is accurate",
        },
    )
    assert req_resp.status_code in (200, 201)
    req_id = req_resp.json()["id"]

    # 3. Add test design
    td_resp = await client.post(
        "/api/test-designs",
        json={
            "requirement_id": req_id,
            "title": "Verify Price Calculation with Coupon",
            "category": "FUNCTIONAL",
            "description": "Applies valid coupons",
        },
    )
    assert td_resp.status_code in (200, 201)

    # 4. Add test case (P0, Manual)
    tc_resp = await client.post(
        "/api/test-cases",
        json={
            "project_id": project_id,
            "requirement_id": req_id,
            "title": "Verify Checkout Total",
            "priority": "P0",
            "automation_status": "MANUAL",
            "tags": ["checkout", "cart"],
        },
    )
    assert tc_resp.status_code in (200, 201)

    # 5. Fetch Quality Coverage Summary
    cov_resp = await client.get(f"/api/quality/coverage?project_id={project_id}")
    assert cov_resp.status_code == 200
    coverage = cov_resp.json()
    assert coverage["total_requirements"] == 1
    assert coverage["total_test_cases"] == 1
    assert coverage["manual_cases"] == 1
    assert coverage["automated_cases"] == 0
    assert len(coverage["requirement_details"]) == 1

    # 6. Fetch Risk Matrix
    risk_resp = await client.get(f"/api/quality/risk-matrix?project_id={project_id}")
    assert risk_resp.status_code == 200
    risk_data = risk_resp.json()
    assert risk_data["unautomated_p0_count"] == 1
    assert any("risk_p0_" in r["id"] for r in risk_data["risks"])
    assert risk_data["overall_risk_level"] in ("HIGH", "CRITICAL")


@pytest.mark.asyncio
async def test_impact_analysis_and_regression_selector(client: AsyncClient):
    # 1. Create project
    proj_resp = await client.post(
        "/api/projects",
        json={"name": "Impact Analysis Project"},
    )
    project_id = proj_resp.json()["id"]

    # 2. Add test cases
    await client.post(
        "/api/test-cases",
        json={
            "project_id": project_id,
            "title": "Login with Google OAuth",
            "priority": "P1",
            "automation_status": "AUTOMATED",
            "tags": ["auth", "oauth"],
        },
    )
    await client.post(
        "/api/test-cases",
        json={
            "project_id": project_id,
            "title": "Checkout Payment Calculation",
            "priority": "P0",
            "automation_status": "MANUAL",
            "tags": ["checkout", "payment"],
        },
    )

    # 3. Analyze impact of auth changes
    impact_resp = await client.post(
        "/api/quality/impact-analysis",
        json={
            "project_id": project_id,
            "changed_files": ["src/auth/service.py", "src/auth/tokens.py"],
        },
    )
    assert impact_resp.status_code == 200
    impact = impact_resp.json()
    assert len(impact["changed_files"]) == 2
    assert any("auth" in test.lower() for test in impact["recommended_regression_tests"])
    assert len(impact["rationale"]) >= 1


@pytest.mark.asyncio
async def test_impact_analysis_maps_automation_binding_to_nodeid(client: AsyncClient):
    """A bound automated test case contributes its stored nodeid/file_path to the impact result."""
    proj_resp = await client.post(
        "/api/projects",
        json={"name": "Impact Binding Project"},
    )
    project_id = proj_resp.json()["id"]

    tc_resp = await client.post(
        "/api/test-cases",
        json={
            "project_id": project_id,
            "title": "Verify Coupon Display",
            "priority": "P2",
            "automation_status": "MANUAL",
            "tags": ["coupon"],
        },
    )
    tc_id = tc_resp.json()["id"]

    nodeid = "tests/test_auth_session.py::test_login_persists_session"
    bind_resp = await client.post(
        f"/api/test-cases/{tc_id}/binding",
        json={
            "test_case_id": tc_id,
            "workspace_id": project_id,
            "nodeid": nodeid,
            "file_path": "tests/test_auth_session.py",
            "framework": "playwright_python",
            "status": "ACTIVE",
        },
    )
    assert bind_resp.status_code == 200

    impact_resp = await client.post(
        "/api/quality/impact-analysis",
        json={
            "project_id": project_id,
            "changed_files": ["src/auth/session.py"],
        },
    )
    assert impact_resp.status_code == 200
    impact = impact_resp.json()
    assert impact["impacted_test_cases"] == [tc_id]
    assert impact["recommended_regression_tests"] == [nodeid]


@pytest.mark.asyncio
async def test_release_management_and_gate_evaluation(client: AsyncClient):
    # 1. Create project
    proj_resp = await client.post(
        "/api/projects",
        json={"name": "Release Gate Project", "bootstrap_workspace": True},
    )
    project_id = proj_resp.json()["id"]

    # 2. Add unautomated P0 test case (intentional blocker)
    await client.post(
        "/api/test-cases",
        json={
            "project_id": project_id,
            "title": "Critical User Signup Flow",
            "priority": "P0",
            "automation_status": "MANUAL",
        },
    )

    # 3. Create Release
    rel_resp = await client.post(
        "/api/releases",
        json={
            "project_id": project_id,
            "version": "v1.2.0",
            "name": "Sprint 12 Release",
            "description": "Core checkout & auth release",
            "pass_rate_threshold": 90.0,
            "max_allowed_flaky": 0,
        },
    )
    assert rel_resp.status_code == 201
    release_id = rel_resp.json()["id"]

    # 4. List releases
    list_resp = await client.get(f"/api/releases?project_id={project_id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 5. Evaluate Release Gate (Expect BLOCKED due to unautomated P0)
    gate_resp = await client.post(f"/api/releases/{release_id}/gate-evaluate")
    assert gate_resp.status_code == 200
    gate_report = gate_resp.json()
    assert gate_report["can_release"] is False
    assert gate_report["verdict"] == "BLOCKED"
    assert len(gate_report["blockers"]) >= 1
    assert any("unautomated P0" in b for b in gate_report["blockers"])

    # 6. Update release details
    patch_resp = await client.patch(
        f"/api/releases/{release_id}",
        json={"name": "Sprint 12 Production Release", "target_date": "2026-10-01"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Sprint 12 Production Release"

    # 7. Delete release
    del_resp = await client.delete(f"/api/releases/{release_id}")
    assert del_resp.status_code == 204
