import pytest
from httpx import AsyncClient


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
