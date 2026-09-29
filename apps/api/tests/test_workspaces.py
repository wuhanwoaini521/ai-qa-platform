import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_workspace_file_operations_and_diff(client: AsyncClient):
    # 1. Create project with bootstrap workspace
    proj_res = await client.post(
        "/api/projects",
        json={"name": "Studio Test Project", "bootstrap_workspace": True},
    )
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    # 2. Get file tree
    files_res = await client.get(f"/api/workspaces/{proj_id}/files")
    assert files_res.status_code == 200
    files = files_res.json()
    names = [f["name"] for f in files]
    assert "README.md" in names
    assert "tests" in names
    assert "pages" in names

    # 3. Read README.md
    read_res = await client.get(f"/api/workspaces/{proj_id}/file?path=README.md")
    assert read_res.status_code == 200
    assert "Automation Workspace" in read_res.json()["content"]

    # 4. Modify / write a file
    write_res = await client.put(
        f"/api/workspaces/{proj_id}/file",
        json={
            "path": "tests/test_search.py",
            "content": "# New automated search test\ndef test_search():\n    assert True\n",
        },
    )
    assert write_res.status_code == 200

    # 5. Check Git diff / changed files
    diff_res = await client.get(f"/api/workspaces/{proj_id}/diff")
    assert diff_res.status_code == 200
    diff_data = diff_res.json()
    changed_paths = [f["path"] for f in diff_data["changed_files"]]
    assert "tests/test_search.py" in changed_paths or any("test_search.py" in p for p in changed_paths)

    # Repeating bootstrap must neither replace user files nor commit their pending changes.
    bootstrap_res = await client.post(f"/api/workspaces/{proj_id}/bootstrap")
    assert bootstrap_res.status_code == 200
    read_res = await client.get(f"/api/workspaces/{proj_id}/file?path=tests/test_search.py")
    assert "# New automated search test" in read_res.json()["content"]
    diff_res = await client.get(f"/api/workspaces/{proj_id}/diff")
    assert any("test_search.py" in item["path"] for item in diff_res.json()["changed_files"])
