from __future__ import annotations

import pytest
from httpx import AsyncClient


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
