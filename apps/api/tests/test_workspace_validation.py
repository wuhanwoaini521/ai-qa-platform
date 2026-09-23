import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_workspace_validation_and_collection(client: AsyncClient):
    # 1. Create project with bootstrap workspace
    proj_res = await client.post(
        "/api/projects",
        json={"name": "Validation Project", "bootstrap_workspace": True},
    )
    proj_id = proj_res.json()["id"]

    # 2. Collect tests (should find test_login_flow from bootstrap)
    collect_res = await client.post(f"/api/workspaces/{proj_id}/collect")
    assert collect_res.status_code == 200
    report = collect_res.json()
    assert report["total"] >= 1
    nodeids = [t["nodeid"] for t in report["tests"]]
    assert any("test_login_flow" in n for n in nodeids)

    # 3. Validate clean workspace
    val_res = await client.post(f"/api/workspaces/{proj_id}/validate")
    assert val_res.status_code == 200
    assert val_res.json()["valid"] is True

    # 4. Inject a file with syntax error
    await client.put(
        f"/api/workspaces/{proj_id}/file",
        json={
            "path": "tests/test_broken.py",
            "content": "def broken_syntax(\n    assert True",
        },
    )

    # 5. Validate workspace again - should catch syntax error
    val_res2 = await client.post(f"/api/workspaces/{proj_id}/validate")
    assert val_res2.status_code == 200
    report2 = val_res2.json()
    assert report2["valid"] is False
    assert len(report2["issues"]) >= 1
    assert any("SyntaxError" in i["message"] for i in report2["issues"])
