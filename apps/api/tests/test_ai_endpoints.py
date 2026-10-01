import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_ai_status_and_usage_endpoints(client: AsyncClient):
    # 1. Check AI Provider Status
    status_res = await client.get("/api/ai/status")
    assert status_res.status_code == 200
    data = status_res.json()
    assert "provider" in data
    assert "status" in data
    assert data["status"] in ["REAL_CONNECTED", "FALLBACK", "SIMULATION", "UNAVAILABLE"]
    assert data["real_model_available"] is (data["status"] == "REAL_CONNECTED")
    assert data["fallback_active"] is (data["status"] == "FALLBACK")
    # Verify no secret leaked
    assert "api_key" not in data
    assert "sk-" not in str(data)

    # 2. Check AI Usage Summary
    usage_res = await client.get("/api/ai/usage")
    assert usage_res.status_code == 200
    usage_data = usage_res.json()
    assert "total_requests" in usage_data
    assert "total_input_tokens" in usage_data
    assert "total_output_tokens" in usage_data
    assert "invocations" in usage_data


@pytest.mark.asyncio
async def test_ai_requirement_and_design_workflow(client: AsyncClient):
    # 1. Create project & requirement
    proj_res = await client.post("/api/projects", json={"name": "AI Workflow Project"})
    proj_id = proj_res.json()["id"]

    req_res = await client.post(
        "/api/requirements",
        json={
            "project_id": proj_id,
            "title": "One-Click Checkout",
            "description": "User clicks checkout and order is placed immediately with saved card",
            "acceptance_criteria": "Card is charged, order confirmation email sent",
        },
    )
    req_id = req_res.json()["id"]

    # 2. Trigger AI Requirement Analysis
    analyze_res = await client.post(f"/api/ai/requirements/{req_id}/analyze")
    assert analyze_res.status_code == 200
    analysis = analyze_res.json()
    assert "summary" in analysis
    assert len(analysis["suggested_test_dimensions"]) > 0

    # 3. Trigger AI Test Design Generation
    designs_res = await client.post(f"/api/ai/requirements/{req_id}/generate-designs")
    assert designs_res.status_code == 200
    designs = designs_res.json()
    assert len(designs) > 0
    assert "title" in designs[0]
    assert "category" in designs[0]

    # Save one test design
    saved_design = await client.post(
        "/api/test-designs",
        json={
            "requirement_id": req_id,
            "title": designs[0]["title"],
            "category": designs[0]["category"],
            "description": designs[0]["description"],
            "risk": designs[0]["risk"],
        },
    )
    design_id = saved_design.json()["id"]

    # 4. Trigger AI Test Case Generation
    cases_res = await client.post(f"/api/ai/test-designs/{design_id}/generate-cases")
    assert cases_res.status_code == 200
    cases = cases_res.json()
    assert len(cases) > 0
    assert "title" in cases[0]
    assert len(cases[0]["steps"]) > 0
