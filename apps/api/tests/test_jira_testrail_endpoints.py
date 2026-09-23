from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_jira_integration_workflow(client: AsyncClient):
    # 1. Create a project
    proj_resp = await client.post(
        "/api/projects",
        json={"name": "Jira Test Project", "description": "Testing Jira integration"},
    )
    assert proj_resp.status_code in (200, 201)
    project_id = proj_resp.json()["id"]

    # 2. Search Jira Issues
    search_resp = await client.get("/api/jira/issues?query=Login")
    assert search_resp.status_code == 200
    issues = search_resp.json()
    assert len(issues) >= 1
    assert issues[0]["key"] == "PROJ-101"

    # 3. Get single Jira Issue
    single_resp = await client.get("/api/jira/issues/PROJ-101")
    assert single_resp.status_code == 200
    assert single_resp.json()["key"] == "PROJ-101"

    # 4. Import Jira Issues to Requirements
    import_resp = await client.post(
        "/api/jira/import",
        json={"issue_keys": ["PROJ-101", "PROJ-102"], "project_id": project_id},
    )
    assert import_resp.status_code == 200
    imported = import_resp.json()
    assert len(imported) == 2
    assert imported[0]["external_system"] == "JIRA"
    assert imported[0]["external_id"] in ("PROJ-101", "PROJ-102")

    # 5. Check Requirements were created
    reqs_resp = await client.get(f"/api/requirements?project_id={project_id}")
    assert reqs_resp.status_code == 200
    req_list = reqs_resp.json()
    assert len(req_list) >= 2

    # 6. Check Integration Audit log
    audit_resp = await client.get("/api/audit/integrations?system=JIRA")
    assert audit_resp.status_code == 200
    audits = audit_resp.json()
    assert len(audits) >= 2
    assert any(a["action"] == "IMPORT_REQUIREMENT" for a in audits)


@pytest.mark.asyncio
async def test_jira_bug_draft_and_creation(client: AsyncClient):
    # 1. Run a test to generate a failure
    proj_resp = await client.post(
        "/api/projects",
        json={"name": "Bug Draft Project", "bootstrap_workspace": True},
    )
    project_id = proj_resp.json()["id"]

    # Write failing test
    await client.put(
        f"/api/workspaces/{project_id}/file",
        json={
            "path": "tests/test_defect.py",
            "content": "import pytest\ndef test_broken_checkout(): raise AssertionError('Expected price $10, got $20')",
        },
    )

    # Execute test run
    run_resp = await client.post(
        "/api/runs",
        json={
            "project_id": project_id,
            "workspace_id": project_id,
            "nodeids": ["tests/test_defect.py::test_broken_checkout"],
        },
    )
    assert run_resp.status_code in (200, 201)
    run_data = run_resp.json()
    run_id = run_data["id"]

    # Wait for test run to finish
    for _ in range(20):
        await asyncio.sleep(0.1)
        r = await client.get(f"/api/runs/{run_id}")
        if r.status_code == 200 and r.json()["status"] in ("PASSED", "FAILED", "BROKEN"):
            break

    # Check failures
    fail_resp = await client.get("/api/failures")
    assert fail_resp.status_code == 200
    failures = [f for f in fail_resp.json() if f["run_id"] == run_id]
    assert len(failures) >= 1
    fail_id = failures[0]["id"]

    # Generate Bug Draft
    draft_resp = await client.post(
        "/api/jira/bug-draft",
        json={"failure_id": fail_id, "project_key": "QA", "issue_type": "Bug"},
    )
    assert draft_resp.status_code == 200
    draft = draft_resp.json()
    assert "Automated Test Failure" in draft["summary"]
    assert draft["failure_id"] == fail_id

    # Dry-run bug create
    dry_create_resp = await client.post(
        "/api/jira/create-bug",
        json={"draft": draft, "confirm_publish": False},
    )
    assert dry_create_resp.status_code == 200
    dry_res = dry_create_resp.json()
    assert dry_res["published"] is False
    assert dry_res["status"] == "DRY_RUN_VALIDATED"

    # Live bug create
    live_create_resp = await client.post(
        "/api/jira/create-bug",
        json={"draft": draft, "confirm_publish": True},
    )
    assert live_create_resp.status_code == 200
    live_res = live_create_resp.json()
    assert live_res["published"] is True
    assert live_res["status"] == "CREATED"


@pytest.mark.asyncio
async def test_testrail_workflow(client: AsyncClient):
    # 1. List cases
    cases_resp = await client.get("/api/testrail/cases?suite_id=S101")
    assert cases_resp.status_code == 200
    cases = cases_resp.json()
    assert len(cases) >= 3

    # 2. Get single case
    case_resp = await client.get("/api/testrail/cases/C101")
    assert case_resp.status_code == 200
    assert case_resp.json()["id"] == "C101"

    # 3. Create project & test run
    proj_resp = await client.post("/api/projects", json={"name": "TestRail Sync Project", "bootstrap_workspace": True})
    project_id = proj_resp.json()["id"]

    run_resp = await client.post(
        "/api/runs",
        json={"project_id": project_id, "workspace_id": project_id},
    )
    assert run_resp.status_code in (200, 201)
    run_id = run_resp.json()["id"]

    for _ in range(20):
        await asyncio.sleep(0.1)
        r = await client.get(f"/api/runs/{run_id}")
        if r.status_code == 200 and r.json()["status"] in ("PASSED", "FAILED", "BROKEN"):
            break

    # 4. Preview publish
    preview_resp = await client.get(f"/api/testrail/runs/{run_id}/preview?suite_id=S101")
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert "total_tests" in preview
    assert "items" in preview

    # 5. Publish dry-run
    pub_dry = await client.post(
        "/api/testrail/publish",
        json={"run_id": run_id, "suite_id": "S101", "confirm_publish": False},
    )
    assert pub_dry.status_code == 200
    assert pub_dry.json()["success"] is True
    assert pub_dry.json()["published"] is False

    # 6. Publish confirmed
    pub_live = await client.post(
        "/api/testrail/publish",
        json={"run_id": run_id, "suite_id": "S101", "confirm_publish": True},
    )
    assert pub_live.status_code == 200
    assert pub_live.json()["success"] is True
    assert pub_live.json()["published"] is True
    assert "testrail_run_id" in pub_live.json()
