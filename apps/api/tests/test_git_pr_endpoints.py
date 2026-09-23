from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_git_and_pr_api_workflow(client: AsyncClient):
    # 1. Create a project and initialize workspace
    proj_resp = await client.post(
        "/api/projects",
        json={
            "name": "E2E GitHub Integration Test",
            "description": "Testing GitHub & PR engineering workflow",
            "bootstrap_workspace": True,
            "repository_url": "https://github.com/fake-org/fake-qa-repo.git",
        },
    )
    assert proj_resp.status_code in (200, 201)
    project_data = proj_resp.json()
    project_id = project_data["id"]
    workspace_id = project_id

    # 3. Check Git Status & Current Branch
    cur_branch_resp = await client.get(f"/api/workspaces/{workspace_id}/git/current-branch")
    assert cur_branch_resp.status_code == 200
    assert cur_branch_resp.json() == "main"

    branches_resp = await client.get(f"/api/workspaces/{workspace_id}/git/branches")
    assert branches_resp.status_code == 200
    branches = branches_resp.json()
    assert any(b["name"] == "main" for b in branches)

    # 4. Create Feature Branch
    create_branch_resp = await client.post(
        f"/api/workspaces/{workspace_id}/git/branch",
        json={"branch_name": "qa/C101-cart-validation", "checkout": True},
    )
    assert create_branch_resp.status_code == 200
    assert create_branch_resp.json() == "qa/C101-cart-validation"

    # 5. Create new file and commit changes
    file_resp = await client.post(
        f"/api/workspaces/{workspace_id}/files/create",
        json={"path": "tests/test_cart.py", "content": "def test_add_item(): pass\n", "is_directory": False},
    )
    assert file_resp.status_code in (200, 201)

    commit_resp = await client.post(
        f"/api/workspaces/{workspace_id}/git/commit",
        json={"message": "feat(cart): add cart test scenario"},
    )
    assert commit_resp.status_code == 200

    # 6. Push Branch
    push_resp = await client.post(f"/api/workspaces/{workspace_id}/git/push")
    assert push_resp.status_code == 200
    push_data = push_resp.json()
    assert push_data["success"] is True

    # 7. Git Log
    log_resp = await client.get(f"/api/workspaces/{workspace_id}/git/log?limit=5")
    assert log_resp.status_code == 200
    commits = log_resp.json()
    assert len(commits) >= 1
    assert any("feat(cart)" in c["message"] for c in commits)

    # 8. Suggest PR Summary
    suggest_resp = await client.post(
        f"/api/workspaces/{workspace_id}/pr/suggest-summary",
        json={"include_diff": True},
    )
    assert suggest_resp.status_code == 200
    summary_data = suggest_resp.json()
    assert "title" in summary_data
    assert "body" in summary_data
    assert "qa/C101-cart-validation" in summary_data["body"]

    # 9. Create Pull Request
    pr_create_resp = await client.post(
        f"/api/workspaces/{workspace_id}/pr/create",
        json={
            "title": summary_data["title"],
            "body": summary_data["body"],
            "head_branch": "qa/C101-cart-validation",
            "base_branch": "main",
        },
    )
    assert pr_create_resp.status_code == 200
    pr_data = pr_create_resp.json()
    assert pr_data["number"] >= 100
    assert "github.com" in pr_data["html_url"]

    # 10. Check PR Status
    checks_resp = await client.get(f"/api/workspaces/{workspace_id}/pr/{pr_data['number']}/checks")
    assert checks_resp.status_code == 200
    checks_data = checks_resp.json()
    assert checks_data["overall_status"] in ("PASSED", "RUNNING", "FAILED")
    assert len(checks_data["checks"]) > 0

    # 11. Diagnose CI Failure
    diag_resp = await client.post(
        f"/api/workspaces/{workspace_id}/pr/diagnose",
        json={
            "check_run_id": checks_data["checks"][0]["id"],
            "failure_logs": "AssertionError: assert False == True\n  File 'tests/test_cart.py', line 12",
        },
    )
    assert diag_resp.status_code == 200
    diag_data = diag_resp.json()
    assert diag_data["classification"] == "TEST_FAILURE"
    assert len(diag_data["suggested_fix"]) > 0
