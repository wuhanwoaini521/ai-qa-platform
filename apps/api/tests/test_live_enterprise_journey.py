"""Opt-in acceptance against real providers and an isolated local test website."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os

import pytest
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.ai_settings_service import AISettingsService
from test_live_locator_repair_acceptance import local_http_url as local_http_url

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(autouse=True)
def live_acceptance_only():
    if os.getenv("AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE") != "1":
        pytest.skip("set AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1 for real-provider acceptance")
    assert importlib.metadata.version("playwright") == "1.62.0"


async def test_real_requirement_to_execution_and_evidence(client, local_http_url, tmp_path, monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path / "artifacts")
    await AISettingsService(TaskRepositoryScopeFactory()).load_runtime_config()
    target = local_http_url(
        '<main><h1>Verification panel</h1><p id="status">Ready</p>'
        "<button onclick=\"document.querySelector('#status').textContent='Verified'\">Verify</button></main>"
    )
    project = await client.post("/api/projects", json={"name": "Enterprise live requirement acceptance"})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    created = await client.post(
        "/api/requirements",
        json={
            "project_id": project_id,
            "title": "Verification panel status transition",
            "description": "A local verification panel initially shows Ready. Clicking Verify changes the status to Verified. No account or external writes are involved.",
            "acceptance_criteria": "AC-001: On load the status is Ready.\nAC-002: Clicking Verify changes the status to Verified.",
        },
    )
    assert created.status_code == 201, created.text
    requirement_id = created.json()["id"]
    analyzed = await client.post(f"/api/requirements/{requirement_id}/lifecycle/analyze/stream")
    assert analyzed.status_code == 200, analyzed.text
    requirement = (await client.get(f"/api/requirements/{requirement_id}")).json()
    document = requirement["qa_model"]
    history = document["history"][-1]
    assert history["status"] == "SUCCESS", {key: history.get(key) for key in ("status", "error_code", "error")}
    assert history["provider"] not in {"", "fake"}
    assert any(item["provider"] == "jev" and not item["fallback_used"] for item in history["decisions"]), history[
        "decisions"
    ]
    designs = await client.post(f"/api/requirements/{requirement_id}/lifecycle/designs")
    assert designs.status_code == 200 and designs.json(), designs.text
    positive = [item for item in designs.json() if (item.get("scenario_model") or {}).get("path_type") != "negative"]
    assert positive, "The model did not produce an executable positive scenario for the explicit acceptance criteria"
    design_id = positive[0]["id"]
    adopted = await client.post(f"/api/test-designs/{design_id}/lifecycle/case")
    assert adopted.status_code == 200, adopted.text
    test_case = adopted.json()
    assert test_case["requirement_id"] == requirement_id
    source = f"""from playwright.sync_api import sync_playwright

def test_verification_panel():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chrome")
        try:
            page = browser.new_page()
            page.goto({target!r})
            assert page.locator("#status").inner_text() == "Ready"
            page.get_by_role("button", name="Verify", exact=True).click()
            assert page.locator("#status").inner_text() == "Verified"
        finally:
            browser.close()
"""
    file_path = "tests/test_verification_panel.py"
    nodeid = f"{file_path}::test_verification_panel"
    saved = await client.put(f"/api/workspaces/{project_id}/file", json={"path": file_path, "content": source})
    assert saved.status_code == 200, saved.text
    bound = await client.post(
        f"/api/test-cases/{test_case['id']}/binding",
        json={
            "test_case_id": test_case["id"],
            "workspace_id": project_id,
            "nodeid": nodeid,
            "file_path": file_path,
            "status": "ACTIVE",
        },
    )
    assert bound.status_code == 200, bound.text
    response = await client.post(
        "/api/runs", json={"project_id": project_id, "workspace_id": project_id, "nodeids": [nodeid]}
    )
    assert response.status_code == 201, response.text
    run = response.json()
    for _ in range(240):
        if run["status"] not in {"QUEUED", "RUNNING"}:
            break
        await asyncio.sleep(0.25)
        run = (await client.get(f"/api/runs/{run['id']}")).json()
    assert run["status"] == "PASSED", {key: run.get(key) for key in ("status", "log_output")}
    assert len(run["executions"]) == 1 and run["executions"][0]["nodeid"] == nodeid
    assert run["browser_sessions"] and run["external_artifacts"]
    graph = (
        await client.get(f"/api/projects/{project_id}/knowledge", params={"requirement_id": requirement_id})
    ).json()
    assert any(node["kind"] == "run" for node in graph["nodes"])
    assert any(node["kind"] == "case" and node["id"].endswith(test_case["id"]) for node in graph["nodes"])
    reopened = (await client.get(f"/api/requirements/{requirement_id}")).json()
    assert reopened["qa_model"]["history"][-1]["id"] == history["id"]
    print(
        "REAL_REQUIREMENT_JOURNEY="
        + json.dumps(
            {
                "project_id": project_id,
                "requirement_id": requirement_id,
                "case_id": test_case["id"],
                "run_id": run["id"],
                "provider": history["provider"],
                "model": history["model"],
                "decisions": history["decisions"],
                "status": run["status"],
                "evidence_count": len(run["external_artifacts"]),
            },
            ensure_ascii=False,
        )
    )


async def test_real_local_discovery_preserves_target_and_project_scope(
    client, test_db_session, local_http_url, tmp_path, monkeypatch
):
    import app.settings as settings_module
    from app.container import get_browser_runtime, get_quality_discovery_service
    from app.main import app
    from app.services.decision_service import DecisionService
    from app.services.quality_discovery_service import QualityDiscoveryService
    from app.services.workspace_service import WorkspaceService

    monkeypatch.setattr(settings_module.settings, "artifact_storage_dir", tmp_path / "artifacts")
    config = settings_module.get_config()
    monkeypatch.setattr(
        settings_module.config_manager,
        "_config",
        config.model_copy(
            update={
                "discovery": config.discovery.model_copy(
                    update={"max_actions": 2, "max_states": 4, "max_runtime_minutes": 1}
                ),
            }
        ),
    )
    await AISettingsService(TaskRepositoryScopeFactory()).load_runtime_config()
    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=get_browser_runtime(),
        decisions=DecisionService(repository_scope=TaskRepositoryScopeFactory()),
        workspace_service=WorkspaceService(),
    )
    app.dependency_overrides[get_quality_discovery_service] = lambda: service
    target = local_http_url(
        "<main><h1>Product catalog</h1><p>Canvas tote</p>"
        "<button onclick=\"document.querySelector('#details').hidden=false\">Show product details</button>"
        '<section id="details" hidden><h2>Canvas tote details</h2><p>Price 20.00, available in blue.</p></section></main>'
    )
    project = (await client.post("/api/projects", json={"name": "Enterprise real browser discovery"})).json()
    created = await client.post(
        "/api/discovery/runs", json={"project_id": project["id"], "start_url": target, "mode": "EXPLORE"}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    try:
        for _ in range(300):
            if run["status"] not in {"QUEUED", "RUNNING"}:
                break
            await asyncio.sleep(0.5)
            run = (await client.get(f"/api/discovery/runs/{run['id']}")).json()
        assert run["status"] in {"COMPLETED", "BUDGET_EXHAUSTED"}, {
            key: run.get(key) for key in ("status", "error", "progress")
        }
        assert run["project_id"] == project["id"] and run["start_url"] == target
        assert run["result"]["states"] and any(item.get("evidence_id") for item in run["result"]["states"])
        assert run["result"]["ai"]["calls"] > 0 and run["result"]["ai"]["provider"] != "fake"
        assert any(
            item.get("provider") == "jev" and not item.get("fallback_used")
            for item in run["result"].get("decisions", [])
        )
        assert run["result"]["features"]
        assert not any(feature.get("test_case_ids") for feature in run["result"]["features"])
        print(
            "REAL_BROWSER_DISCOVERY="
            + json.dumps(
                {
                    "run_id": run["id"],
                    "project_id": project["id"],
                    "start_url": target,
                    "status": run["status"],
                    "progress": run["progress"],
                    "ai": run["result"]["ai"],
                    "jev": run["result"]["jev"],
                },
                ensure_ascii=False,
            )
        )
    finally:
        if run["status"] in {"QUEUED", "RUNNING", "PAUSED"}:
            await service.stop(run["id"])
        tasks = list(service._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
