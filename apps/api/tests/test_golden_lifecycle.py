import pytest
from app.persistence.models import TestRunORM as RunORM
from app.services.golden_demo_service import DEMO_ID, DEMO_REQUIREMENT
from sqlalchemy import select

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_demo_is_idempotent_and_coverage_uses_real_denominators(client):
    first = await client.post("/api/projects/golden-demo/seed")
    assert first.status_code == 200, first.text
    assert first.json()["created"]
    again = await client.post("/api/projects/golden-demo/seed")
    assert not again.json()["created"]
    doc = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()["qa_model"]
    assert doc["history"][0]["status"] == "REFERENCE"
    graph = (await client.get(f"/api/projects/{DEMO_ID}/knowledge")).json()
    assert graph["counts"]["case"] == 7
    assert graph["counts"]["automated"] == 6
    assert graph["counts"]["executed"] == 0
    metrics = {item["key"]: item for item in graph["coverage"]}
    assert (metrics["criteria"]["covered"], metrics["criteria"]["total"]) == (6, 6)
    assert metrics["automation"]["percentage"] == 85.7
    assert metrics["execution"]["percentage"] == 0
    assert metrics["passed"]["percentage"] is None
    assert not any(node["kind"] == "run" for node in graph["nodes"])
    assert any(gap["label"] == "AC-006" and gap["reason"] == "no_automation" for gap in graph["gaps"])


@pytest.mark.asyncio
async def test_cross_project_references_and_orphaned_oracles_are_rejected(client):
    await client.post("/api/projects/golden-demo/seed")
    other = (await client.post("/api/projects", json={"name": "Other", "bootstrap_workspace": False})).json()
    result = await client.post(
        "/api/test-cases", json={"project_id": other["id"], "requirement_id": DEMO_REQUIREMENT, "title": "Invalid"}
    )
    assert result.status_code == 422
    graph = await client.get(f"/api/projects/{other['id']}/knowledge?focus=case_golden_004")
    assert graph.status_code == 422
    req = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()
    req["qa_model"]["criteria"] = req["qa_model"]["criteria"][:-1]
    response = await client.patch(f"/api/requirements/{DEMO_REQUIREMENT}", json={"qa_model": req["qa_model"]})
    assert response.status_code == 422
    response = await client.patch(f"/api/requirements/{DEMO_REQUIREMENT}", json={"qa_model": None})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_demo_reset_preserves_other_projects_and_refuses_active_runs(client, test_db_session):
    await client.post("/api/projects/golden-demo/seed")
    other = (await client.post("/api/projects", json={"name": "User project", "bootstrap_workspace": False})).json()
    denied = await client.post(f"/api/projects/{other['id']}/demo/reset")
    assert denied.status_code == 409
    async with test_db_session() as session:
        session.add(RunORM(id="run_golden_busy", project_id=DEMO_ID, workspace_id=DEMO_ID, status="RUNNING"))
        await session.commit()
    result = await client.post(f"/api/projects/{DEMO_ID}/demo/reset")
    assert result.status_code == 409
    async with test_db_session() as session:
        row = await session.scalar(select(RunORM).where(RunORM.id == "run_golden_busy"))
        row.status = "CANCELLED"
        await session.commit()
    result = await client.post(f"/api/projects/{DEMO_ID}/demo/reset")
    assert result.status_code == 200, result.text
    assert (await client.get(f"/api/projects/{other['id']}")).status_code == 200
    graph = (await client.get(f"/api/projects/{DEMO_ID}/knowledge")).json()
    assert graph["counts"]["case"] == 7


@pytest.mark.asyncio
async def test_adoption_reuses_existing_entities_and_models(client):
    await client.post("/api/projects/golden-demo/seed")
    designs = await client.post(f"/api/requirements/{DEMO_REQUIREMENT}/lifecycle/designs")
    assert designs.status_code == 200, designs.text
    assert len(designs.json()) == 7
    adopted = await client.post("/api/test-designs/des_golden_004/lifecycle/case")
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["id"] == "case_golden_004"
    assert adopted.json()["test_model"]["coverage"]["criterion_ids"] == ["AC-003", "AC-004"]


@pytest.mark.asyncio
async def test_demo_static_shop_is_public_but_seed_is_protected(anonymous_client):
    assert (await anonymous_client.get("/api/demo-shop/index.html")).status_code == 200
    assert (await anonymous_client.post("/api/projects/golden-demo/seed")).status_code == 401
