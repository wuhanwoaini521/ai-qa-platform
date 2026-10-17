import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_test_case_crud(client: AsyncClient):
    # 1. Create project
    proj_res = await client.post(
        "/api/projects",
        json={"name": "Auth Service", "bootstrap_workspace": False},
    )
    proj_id = proj_res.json()["id"]

    # 2. Create test case
    tc_res = await client.post(
        "/api/test-cases",
        json={
            "project_id": proj_id,
            "title": "Verify Login with Valid MFA Token",
            "preconditions": "User has MFA enabled on account.",
            "steps": [
                "Navigate to /login",
                "Enter valid username and password",
                "Prompted for 6-digit TOTP",
                "Enter valid OTP code",
            ],
            "expected_result": "Successfully redirected to dashboard with valid auth session.",
            "priority": "P0",
            "automation_status": "MANUAL",
            "tags": ["auth", "mfa", "smoke"],
        },
    )
    assert tc_res.status_code == 201
    tc_data = tc_res.json()
    assert tc_data["priority"] == "P0"
    assert len(tc_data["steps"]) == 4
    case_id = tc_data["id"]

    # 3. Update automation status
    patch_res = await client.patch(
        f"/api/test-cases/{case_id}",
        json={"automation_status": "AUTOMATED"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["automation_status"] == "AUTOMATED"

    # 4. List by project
    list_res = await client.get(f"/api/test-cases?project_id={proj_id}")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1


@pytest.mark.asyncio
async def test_binding_rejects_workspace_from_another_project(client: AsyncClient):
    projects = []
    for name in ("Binding owner", "Foreign workspace"):
        response = await client.post("/api/projects", json={"name": name, "bootstrap_workspace": False})
        assert response.status_code == 201, response.text
        projects.append(response.json()["id"])

    case = await client.post(
        "/api/test-cases",
        json={"project_id": projects[0], "title": "Project-owned case", "expected_result": "Pass"},
    )
    assert case.status_code == 201, case.text
    binding = await client.post(
        f"/api/test-cases/{case.json()['id']}/binding",
        json={
            "test_case_id": case.json()["id"],
            "workspace_id": projects[1],
            "nodeid": "tests/test_project.py::test_isolation",
            "file_path": "tests/test_project.py",
            "status": "ACTIVE",
        },
    )
    assert binding.status_code == 422
    assert binding.json()["detail"] == "Workspace does not belong to the test case project"
