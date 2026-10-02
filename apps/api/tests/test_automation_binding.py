import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_automation_binding_and_generation(client: AsyncClient, monkeypatch):
    from qa_core.ai.models import AICompletionResponse
    from qa_core.ai.registry import AIProviderRegistry

    class ContractProvider:
        async def complete(self, request):
            assert "Total is discounted" in request.prompt
            assert "conftest.py" in request.prompt
            return AICompletionResponse(
                content="",
                provider="contract-test",
                model="test-model",
                structured_data={
                    "reply": "Draft coupon calculation case",
                    "suggested_code": "def test_verify_checkout_flow():\n    total = 100 * (1 - 0.2)\n    assert total == 80\n",
                    "target_file": "tests/test_coupon.py",
                    "action_type": "generate_test",
                    "suggestions": [],
                },
            )

    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda: ContractProvider())
    # 1. Create project
    proj_res = await client.post(
        "/api/projects",
        json={"name": "Binding Test Suite", "bootstrap_workspace": True},
    )
    proj_id = proj_res.json()["id"]

    # 2. Create test case
    tc_res = await client.post(
        "/api/test-cases",
        json={
            "project_id": proj_id,
            "title": "Verify Checkout Flow for Discount Coupons",
            "preconditions": "Cart has items",
            "steps": ["Apply coupon", "Verify discount"],
            "expected_result": "Total is discounted",
            "priority": "P0",
            "automation_status": "MANUAL",
        },
    )
    tc_id = tc_res.json()["id"]
    from app.services.workspace_service import WorkspaceService

    await WorkspaceService().write_file(
        proj_id, "conftest.py", "import pytest\n@pytest.fixture\ndef cart_total():\n    return 100\n"
    )

    # 3. Generate automation draft
    gen_res = await client.post(f"/api/test-cases/{tc_id}/generate-automation")
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["status"] == "generated"
    assert "::test_verify_checkout_flow" in gen_data["binding"]["nodeid"]

    # 4. Check binding
    bind_res = await client.get(f"/api/test-cases/{tc_id}/binding")
    assert bind_res.status_code == 200
    binding = bind_res.json()
    assert binding is not None
    assert binding["status"] == "DRAFT"

    # 5. Mark Automated / Active
    update_bind_res = await client.post(
        f"/api/test-cases/{tc_id}/binding",
        json={
            "test_case_id": tc_id,
            "workspace_id": proj_id,
            "nodeid": binding["nodeid"],
            "file_path": binding["file_path"],
            "framework": "playwright_python",
            "status": "ACTIVE",
        },
    )
    assert update_bind_res.status_code == 200
    assert update_bind_res.json()["status"] == "ACTIVE"

    # 6. Verify TestCase automation_status updated to AUTOMATED
    tc_updated = await client.get(f"/api/test-cases/{tc_id}")
    assert tc_updated.status_code == 200
    assert tc_updated.json()["automation_status"] == "AUTOMATED"
