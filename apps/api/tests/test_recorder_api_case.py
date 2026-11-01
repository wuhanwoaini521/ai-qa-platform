import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _call_id(method: str, url: str, status: int) -> str:
    return hashlib.sha256(f"{method}\0{url}\0{status}".encode("utf-8")).hexdigest()[:12]


@pytest.mark.asyncio
async def test_save_api_case_writes_file_creates_case_and_reuses(client: AsyncClient, monkeypatch):
    from app.api.recorder import recorder_service

    project = await client.post("/api/projects", json={"name": "Recorder API case", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    url = "http://127.0.0.1:8099/api/info"
    network = [
        {
            "url": url,
            "method": "GET",
            "failed": False,
            "status": 200,
            "resource_type": "xhr",
            "request_headers": {"accept": "application/json"},
            "request_body": None,
            "response_headers": {"content-type": "application/json"},
        }
    ]
    session = SimpleNamespace(
        id="recorder-api-session",
        project_id=project_id,
        runtime_session=SimpleNamespace(network=network),
    )
    monkeypatch.setattr(recorder_service, "get", AsyncMock(return_value=session))
    payload = {"call_id": _call_id("GET", url, 200)}

    saved = await client.post("/api/recorder/sessions/test-session/save-api-case", json=payload)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["file_path"].startswith("tests/test_get_")
    assert body["nodeid"] == f"{body['file_path']}::{body['test_case']['test_model']['display_id']}"
    assert body["test_case"]["id"].startswith("tc_api_")
    assert "httpx.request" in body["code"]
    assert body["reused"] is False

    written = await client.get(f"/api/workspaces/{project_id}/file?path={body['file_path']}")
    assert written.status_code == 200, written.text
    assert "httpx.request" in written.json()["content"]

    binding = await client.get(f"/api/test-cases/{body['test_case']['id']}/binding")
    assert binding.status_code == 200, binding.text
    assert binding.json()["nodeid"] == body["nodeid"]

    retry = await client.post("/api/recorder/sessions/test-session/save-api-case", json=payload)
    assert retry.status_code == 200, retry.text
    assert retry.json()["reused"] is True
    assert retry.json()["test_case"]["id"] == body["test_case"]["id"]


@pytest.mark.asyncio
async def test_save_api_case_keeps_auth_as_environment_reference(client: AsyncClient, monkeypatch):
    from app.api.recorder import recorder_service

    project = await client.post("/api/projects", json={"name": "Recorder API auth", "bootstrap_workspace": True})
    project_id = project.json()["id"]
    url = "http://127.0.0.1:8099/api/info"
    session = SimpleNamespace(
        id="recorder-api-auth",
        project_id=project_id,
        runtime_session=SimpleNamespace(
            network=[
                {
                    "url": url,
                    "method": "GET",
                    "failed": False,
                    "status": 200,
                    "resource_type": "fetch",
                    "request_headers": {
                        "accept": "application/json",
                        "authorization": "[REDACTED]",
                    },
                    "request_body": None,
                    "response_headers": {"content-type": "application/json"},
                }
            ]
        ),
    )
    monkeypatch.setattr(recorder_service, "get", AsyncMock(return_value=session))
    saved = await client.post(
        "/api/recorder/sessions/test-session/save-api-case",
        json={"call_id": _call_id("GET", url, 200)},
    )
    assert saved.status_code == 200, saved.text
    code = saved.json()["code"]
    assert "QA_API_SECRET_AUTHORIZATION" in code
    assert "Bearer" not in code
    assert "[REDACTED]" not in code


@pytest.mark.asyncio
async def test_save_api_case_rejects_unknown_call(client: AsyncClient, monkeypatch):
    from app.api.recorder import recorder_service

    project = await client.post("/api/projects", json={"name": "Recorder API case 2", "bootstrap_workspace": True})
    project_id = project.json()["id"]
    session = SimpleNamespace(
        id="recorder-api-session-2",
        project_id=project_id,
        runtime_session=SimpleNamespace(network=[]),
    )
    monkeypatch.setattr(recorder_service, "get", AsyncMock(return_value=session))
    response = await client.post(
        "/api/recorder/sessions/test-session/save-api-case",
        json={"call_id": "does-not-exist"},
    )
    assert response.status_code == 422
