import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_file_create_rename_delete(client: AsyncClient):
    # 1. Create project
    proj_res = await client.post(
        "/api/projects",
        json={"name": "File Ops Project", "bootstrap_workspace": True},
    )
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    # 2. Create a new test file
    create_res = await client.post(
        f"/api/workspaces/{proj_id}/files/create",
        json={
            "path": "tests/test_custom_flow.py",
            "is_directory": False,
            "content": "def test_custom():\n    assert True\n",
        },
    )
    assert create_res.status_code == 201

    # 3. Read created file
    read_res = await client.get(f"/api/workspaces/{proj_id}/file?path=tests/test_custom_flow.py")
    assert read_res.status_code == 200
    assert "test_custom" in read_res.json()["content"]

    # 4. Rename file
    rename_res = await client.patch(
        f"/api/workspaces/{proj_id}/files/rename",
        json={
            "old_path": "tests/test_custom_flow.py",
            "new_path": "tests/test_renamed_flow.py",
        },
    )
    assert rename_res.status_code == 200

    # 5. Delete file
    del_res = await client.delete(f"/api/workspaces/{proj_id}/files/delete?path=tests/test_renamed_flow.py")
    assert del_res.status_code == 200

    # 6. Verify deleted
    not_found_res = await client.get(f"/api/workspaces/{proj_id}/file?path=tests/test_renamed_flow.py")
    assert not_found_res.status_code == 404
