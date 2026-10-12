"""Opt-in acceptance journey against live AI/Jev providers and a local Playwright site.

Run only after checking the configured providers and budgets:
AI_QA_LIVE_BROWSER_E2E=1 uv run pytest apps/api/tests/test_browser_agent_live_e2e.py -q
"""

from __future__ import annotations

import json
import os
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from app.persistence.models import AIInvocationORM, ArtifactORM, TaskArtifactORM, TaskEventORM, TaskORM
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.ai_settings_service import AISettingsService
from app.services.task_runtime_service import TaskRuntimeService
from app.settings import get_config, settings
from sqlalchemy import select


class LiveSearchSiteHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = (
                "<title>Local Catalog</title><h1>Local Catalog</h1>"
                '<form action="/search"><label for="catalog-search">Search catalog</label>'
                '<input id="catalog-search" name="q" type="search" placeholder="Search catalog">'
                '<button type="submit">Search</button></form>'
            )
        elif path == "/search":
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            body = (
                f"<title>Catalog results for {query}</title><h1>Search results</h1>"
                '<a href="/products/blue-wool-jacket">Blue Wool Jacket — product details</a>'
            )
        elif path == "/products/blue-wool-jacket":
            body = "<title>Blue Wool Jacket</title><h1>Blue Wool Jacket</h1><p>Color: blue; Material: wool.</p>"
        else:
            body = "<title>Not found</title><h1>Not found</h1>"
        payload = f"<!doctype html><html><body>{body}</body></html>".encode()
        self.send_response(200 if path in {"/", "/search", "/products/blue-wool-jacket"} else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_live_ai_jev_browser_agent_searches_local_catalog(test_db_session, tmp_path, monkeypatch):
    if os.environ.get("AI_QA_LIVE_BROWSER_E2E") != "1":
        pytest.skip("Set AI_QA_LIVE_BROWSER_E2E=1 to make real AI/Jev provider calls.")

    config = get_config()
    if (
        not config.ai.enabled
        or config.ai.provider.casefold() == "fake"
        or not config.ai.api_key.get_secret_value()
        or not config.jev.enabled
        or not config.features.jev_decision
        or not config.jev.api_key.get_secret_value()
    ):
        pytest.skip("Effective config does not have both a real AI provider and Jev enabled with credentials.")

    server = ThreadingHTTPServer(("127.0.0.1", 0), LiveSearchSiteHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path)
    task_id = uuid4().hex
    owner_id = uuid4().hex
    start_url = f"http://127.0.0.1:{server.server_port}/"
    task = TaskORM(
        id=task_id,
        type="EXPLORE_PAGE",
        goal=(
            "Search the catalog for a blue wool jacket, open the matching product details, "
            "and confirm the product page identifies a Blue Wool Jacket."
        ),
        owner_id=owner_id,
        inputs={
            "url": start_url,
            "max_browser_actions": 6,
            "max_recovery_attempts": 2,
            "require_jev_decisions": True,
            "observable_text_criteria": ["Blue Wool Jacket", "Material: wool"],
        },
    )
    try:
        async with test_db_session() as session:
            session.add(task)
            await session.commit()

        repository_scope = TaskRepositoryScopeFactory()
        await AISettingsService(repository_scope=repository_scope).load_runtime_config()
        result = await TaskRuntimeService(repository_scope=repository_scope).execution.browser_executor._browser_agent(
            task, {}
        )

        assert result["verified"] is True
        assert result["final_url"].endswith("/products/blue-wool-jacket")
        assert result["goal_evidence"]["visible_text_criteria"] == ["Blue Wool Jacket", "Material: wool"]
        assert result["actions"]
        assert all(action["correlation_id"] for action in result["actions"])
        assert all(sample["provider"] == "jev" for sample in result["decision_samples"])
        assert all(sample["correlation_id"] for sample in result["decision_samples"])

        async with test_db_session() as session:
            invocations = list(
                (await session.scalars(select(AIInvocationORM).where(AIInvocationORM.task_id == task_id))).all()
            )
            events = list((await session.scalars(select(TaskEventORM).where(TaskEventORM.task_id == task_id))).all())
            artifacts = list(
                (
                    await session.scalars(
                        select(ArtifactORM)
                        .join(TaskArtifactORM, ArtifactORM.id == TaskArtifactORM.artifact_id)
                        .where(TaskArtifactORM.task_id == task_id)
                    )
                ).all()
            )

        browser_screenshots = [
            item for item in artifacts if item.filename.startswith("browser-action-") and item.filename.endswith(".png")
        ]
        assert browser_screenshots
        model_calls = [row for row in invocations if row.decision_name is None]
        jev_calls = [row for row in invocations if row.decision_name == "browser_action_selection"]
        assert model_calls and all(row.provider == config.ai.provider for row in model_calls)
        assert all(row.status == "SUCCESS" and not row.fallback_used for row in model_calls)
        assert jev_calls and all(row.provider == "jev" and row.status == "SUCCESS" for row in jev_calls)
        model_run_ids = {row.run_id for row in model_calls}
        jev_run_ids = {row.run_id for row in jev_calls}
        action_run_ids = {action["correlation_id"] for action in result["actions"]}
        assert action_run_ids <= model_run_ids
        assert action_run_ids <= jev_run_ids

        persisted_decisions = [row.payload for row in events if row.type == "decision.created"]
        persisted_actions = [row.payload for row in events if row.type == "browser.action_completed"]
        assert action_run_ids <= {payload.get("correlation_id") for payload in persisted_decisions}
        assert action_run_ids <= {payload.get("correlation_id") for payload in persisted_actions}

        evidence_directory = os.environ.get("AI_QA_LIVE_EVIDENCE_DIR")
        if evidence_directory:
            destination = Path(evidence_directory)
            destination.mkdir(parents=True, exist_ok=True)
            screenshot_names = []
            for artifact in artifacts:
                if artifact.filename.startswith("browser-action-") and artifact.filename.endswith(".png"):
                    source = Path(artifact.storage_path)
                    if source.is_file():
                        screenshot_name = f"live-browser-action-{len(screenshot_names) + 1:02d}.png"
                        shutil.copy2(source, destination / screenshot_name)
                        screenshot_names.append(screenshot_name)
            manifest = {
                "task_id": task_id,
                "strategy": result["strategy"],
                "goal": task.goal,
                "verified": result["verified"],
                "final_url": result["final_url"],
                "ai_provider": config.ai.provider,
                "ai_model": config.ai.model,
                "jev_provider": "jev",
                "jev_model": config.jev.model,
                "action_count": len(result["actions"]),
                "ai_invocation_count": len(model_calls),
                "jev_invocation_count": len(jev_calls),
                "actions": [
                    {
                        "sequence": action["sequence"],
                        "action": action["action"],
                        "status": action["status"],
                        "decision_provider": action["decision_provider"],
                        "correlation_id": action["correlation_id"],
                    }
                    for action in result["actions"]
                ],
                "ai_invocation_run_ids": sorted(str(row.run_id) for row in model_calls if row.run_id),
                "jev_invocation_run_ids": sorted(str(row.run_id) for row in jev_calls if row.run_id),
                "screenshot_files": screenshot_names,
            }
            (destination / "live-browser-acceptance.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
