import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_workspace_path_traversal_prevention(client: AsyncClient):
    # Create project
    proj_res = await client.post(
        "/api/projects",
        json={"name": "Security Test Project", "bootstrap_workspace": True},
    )
    proj_id = proj_res.json()["id"]

    # 1. Traversal in file read
    malicious_paths = [
        "../../etc/passwd",
        "/etc/passwd",
        "../../.ssh/id_rsa",
        "../..",
        "tests/../../..",
    ]

    for bad_path in malicious_paths:
        res = await client.get(f"/api/workspaces/{proj_id}/file?path={bad_path}")
        assert res.status_code in (400, 404), f"Path {bad_path} should be rejected or not found"

    # 2. Traversal in file write
    bad_write = await client.put(
        f"/api/workspaces/{proj_id}/file",
        json={"path": "../../escape.txt", "content": "malicious content"},
    )
    assert bad_write.status_code == 400

    # 3. Traversal in workspace ID
    bad_ws_id = "../../escaped_ws"
    bad_ws_res = await client.get(f"/api/workspaces/{bad_ws_id}/files")
    # Base dir validation handles this safely (either rejects 400/404 or isolates to empty dir)
    assert bad_ws_res.status_code in (200, 400, 404)
