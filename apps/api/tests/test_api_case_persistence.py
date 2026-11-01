from __future__ import annotations

import pytest


async def _seed(client, session):
    from app.persistence.models import RequirementORM

    project = (
        await client.post("/api/projects", json={"name": "API case persistence", "bootstrap_workspace": True})
    ).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Health endpoint",
                "description": "The info endpoint reports the fixture state.",
                "acceptance_criteria": "Service name is fixture",
            },
        )
    ).json()
    async with session() as db:
        row = await db.get(RequirementORM, requirement["id"])
        row.qa_model = {
            "display_id": "REQ-API-1",
            "criteria": [
                {"id": "AC-001", "description": "Service name is fixture", "negative_required": False},
                {"id": "AC-002", "description": "Status is 200", "negative_required": False},
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
    return project, requirement


def _payload(project_id: str, requirement_id: str | None, criteria: list[str]) -> dict:
    return {
        "project_id": project_id,
        "requirement_id": requirement_id,
        "criterion_ids": criteria,
        "request": {
            "test_name": "api_info",
            "method": "GET",
            "url": "/api/info",
            "base_url": "http://127.0.0.1:8099",
            "assertions": [{"kind": "status", "expected": 200}],
        },
    }


@pytest.mark.asyncio
async def test_save_api_case_writes_file_case_and_assertions(client, test_db_session):
    project, requirement = await _seed(client, test_db_session)
    saved = await client.post(
        "/api/api-cases/save", json=_payload(project["id"], requirement["id"], ["AC-001", "AC-002"])
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    case_id = body["test_case"]["id"]
    assert case_id.startswith("tc_api_")
    assert body["file_path"] == "tests/test_api_info.py"
    assert body["nodeid"] == "tests/test_api_info.py::test_api_info"
    assert [item["criterion_id"] for item in body["assertions"]] == ["AC-001", "AC-002"]

    file = await client.get(f"/api/workspaces/{project['id']}/file?path=tests/test_api_info.py")
    assert file.status_code == 200 and "httpx.request" in file.json()["content"]

    assertions = (await client.get(f"/api/test-cases/{case_id}/assertions")).json()["assertions"]
    assert {item["criterion_id"] for item in assertions} == {"AC-001", "AC-002"}
    assert all(item["nodeid"] == body["nodeid"] for item in assertions)
    assert all(item["state"] in {"NEVER_RUN", "UNBOUND"} for item in assertions)

    retry = await client.post("/api/api-cases/save", json=_payload(project["id"], requirement["id"], ["AC-001"]))
    assert retry.status_code == 200
    assert retry.json()["reused"] is True
    assert retry.json()["test_case"]["id"] == case_id
    assert [item["criterion_id"] for item in retry.json()["assertions"]] == ["AC-001"]


@pytest.mark.asyncio
async def test_save_api_case_rejects_unknown_criterion(client, test_db_session):
    project, requirement = await _seed(client, test_db_session)
    response = await client.post("/api/api-cases/save", json=_payload(project["id"], requirement["id"], ["AC-999"]))
    assert response.status_code == 422
    assert "Unknown criteria" in response.json()["detail"]


@pytest.mark.asyncio
async def test_save_api_case_without_requirement_has_no_assertions(client, test_db_session):
    project, _ = await _seed(client, test_db_session)
    response = await client.post("/api/api-cases/save", json=_payload(project["id"], None, []))
    assert response.status_code == 200, response.text
    assert response.json()["assertions"] == []
