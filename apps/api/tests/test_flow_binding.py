"""Flow canvas → case assertion binding."""

from __future__ import annotations

import pytest


async def _seed_requirement(client, session) -> tuple[dict, dict, list[str]]:
    from app.persistence.models import RequirementORM

    project = (
        await client.post("/api/projects", json={"name": "Flow binding probe", "bootstrap_workspace": True})
    ).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Checkout discount",
                "description": "A valid code reduces the total.",
                "acceptance_criteria": "Valid code reduces the total\nExpired code keeps the total",
            },
        )
    ).json()
    async with session() as db:
        row = await db.get(RequirementORM, requirement["id"])
        row.qa_model = {
            "display_id": "REQ-001",
            "criteria": [
                {"id": "AC-001", "description": "Valid code reduces the total", "negative_required": False},
                {"id": "AC-002", "description": "Expired code keeps the total", "negative_required": False},
            ],
            "rules": [],
            "constraints": [],
            "dependencies": [],
            "analysis": None,
            "history": [],
            "assertions": [],
            "scripts": [],
        }
        await db.commit()
    criteria = ["AC-001", "AC-002"]
    return project, requirement, criteria


def _payload(project_id: str, requirement_id: str, criterion_id: str) -> dict:
    return {
        "project_id": project_id,
        "requirement_id": requirement_id,
        "scenario_id": "SCN-001",
        "file_path": "tests/test_flow_checkout.py",
        "test_name": "test_flow_checkout",
        "title": "Apply a valid discount code",
        "steps": ["open checkout", "apply code"],
        "assertions": [
            {
                "criterion_id": criterion_id,
                "statement": "Total reflects the applied discount",
                "check": "assert_text:css=#total contains 90.00",
            }
        ],
    }


@pytest.mark.asyncio
async def test_bind_flow_creates_case_assertions_with_nodeid(client, test_db_session):
    project, requirement, criteria = await _seed_requirement(client, test_db_session)
    response = await client.post("/api/flows/bind-case", json=_payload(project["id"], requirement["id"], criteria[0]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case_id"].startswith("tc_flow_")
    assert body["nodeid"] == "tests/test_flow_checkout.py::test_flow_checkout"
    assert body["created"] is True

    response_body = (await client.get(f"/api/test-cases/{body['case_id']}/assertions")).json()
    assertions = response_body["assertions"]
    assert len(assertions) == 1
    entry = assertions[0]
    assert entry["criterion_id"] == criteria[0]
    assert entry["nodeid"] == body["nodeid"]
    assert entry["state"] in {"NEVER_RUN", "UNBOUND"}

    # Re-binding the same identity refreshes the case instead of duplicating it.
    again = await client.post("/api/flows/bind-case", json=_payload(project["id"], requirement["id"], criteria[0]))
    assert again.status_code == 200
    assert again.json()["case_id"] == body["case_id"]
    assert again.json()["created"] is False


@pytest.mark.asyncio
async def test_bind_flow_rejects_unknown_criterion(client, test_db_session):
    project, requirement, _ = await _seed_requirement(client, test_db_session)
    response = await client.post("/api/flows/bind-case", json=_payload(project["id"], requirement["id"], "AC-999"))
    assert response.status_code == 422
    assert "Unknown criteria" in response.json()["detail"]


@pytest.mark.asyncio
async def test_bind_flow_rejects_requirement_from_another_project(client, test_db_session):
    project, requirement, criteria = await _seed_requirement(client, test_db_session)
    other = (await client.post("/api/projects", json={"name": "Other project", "bootstrap_workspace": True})).json()
    response = await client.post("/api/flows/bind-case", json=_payload(other["id"], requirement["id"], criteria[0]))
    assert response.status_code == 422
    assert "another project" in response.json()["detail"]
