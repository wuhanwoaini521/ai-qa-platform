import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_project(client: AsyncClient):
    payload = {
        "name": "E-Commerce QA Suite",
        "description": "Full end-to-end regression test suite",
        "repository_url": "https://github.com/org/ecom-tests",
        "default_branch": "main",
        "framework_type": "playwright_python",
        "bootstrap_workspace": True,
    }

    create_res = await client.post("/api/projects", json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["name"] == "E-Commerce QA Suite"
    assert data["id"].startswith("proj_")
    proj_id = data["id"]

    # Get by ID
    get_res = await client.get(f"/api/projects/{proj_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "E-Commerce QA Suite"

    # List
    list_res = await client.get("/api/projects")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # Update
    patch_res = await client.patch(
        f"/api/projects/{proj_id}",
        json={"description": "Updated description"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["description"] == "Updated description"
