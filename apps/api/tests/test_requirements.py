import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_requirement_lifecycle(client: AsyncClient):
    # 1. Create project
    proj_res = await client.post(
        "/api/projects",
        json={"name": "Checkout Service", "bootstrap_workspace": False},
    )
    proj_id = proj_res.json()["id"]

    # 2. Create requirement
    req_res = await client.post(
        "/api/requirements",
        json={
            "project_id": proj_id,
            "title": "Guest Checkout with Coupon Code",
            "description": "Users should be able to apply coupons at checkout as guest.",
            "acceptance_criteria": "Discount is reflected in final total.",
            "status": "DRAFT",
        },
    )
    assert req_res.status_code == 201
    req_data = req_res.json()
    assert req_data["title"] == "Guest Checkout with Coupon Code"
    req_id = req_data["id"]

    # 3. Create test design for requirement
    des_res = await client.post(
        "/api/test-designs",
        json={
            "requirement_id": req_id,
            "title": "Boundary Test: Expired Coupon Code",
            "category": "BOUNDARY",
            "description": "Ensure expired coupon returns clear error message.",
            "risk": "High",
            "status": "DRAFT",
        },
    )
    assert des_res.status_code == 201
    assert des_res.json()["category"] == "BOUNDARY"

    # 4. List test designs
    list_des = await client.get(f"/api/test-designs?requirement_id={req_id}")
    assert list_des.status_code == 200
    assert len(list_des.json()) == 1

    # 5. Update requirement status
    patch_res = await client.patch(
        f"/api/requirements/{req_id}",
        json={"status": "READY"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "READY"
