from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from app.api.failures import get_failure_service
from app.persistence.models import BrowserSessionORM, utc_now
from app.repositories.browser_session_repo import BrowserSessionRepository
from app.repositories.failure_repo import FailureRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.failure_service import FailureService
from app.services.failure_workflow_service import FailureWorkflowService
from app.services.locator_decision_service import LocatorDecisionService
from app.services.secret_store import SecretStore
from project_model.models import FailureReplaySummary, FailureSnapshotBundle, RunStatus
from project_model.models import TestRunCreate as RunCreate
from qa_core.ai.models import FailureAnalysisResponse
from qa_core.execution.failure_snapshot import capture_failure_snapshot_event
from qa_core.execution.models import FailureSnapshotCapture
from qa_core.failure.snapshot_crypto import FailureSnapshotCipher
from sqlalchemy import select


def test_plugin_snapshot_transfer_redacts_metadata_and_reencrypts_state():
    ephemeral_key = FailureSnapshotCipher.generate_ephemeral_key()
    master_key = "test-platform-master-key"
    raw_state = json.dumps({"cookies": [{"name": "auth", "value": "fixture-auth-token"}]})
    encrypted_state = FailureSnapshotCipher.encrypt_ephemeral(raw_state, ephemeral_key)
    event = {
        "type": "session.finished",
        "session_id": "browser-session",
        "page_id": "page-id",
        "nodeid": "tests/test_checkout.py::test_checkout",
        "case_name": "test_checkout",
        "worker_id": "main",
        "page_evidence": {
            "failure_snapshot": {
                "status": "CAPTURED",
                "captured_at": utc_now().isoformat(),
                "url": "https://shop.example/checkout?token=hidden",
                "accessibility_tree": "button Pay",
                "redacted_dom": "<input value='[REDACTED]'>",
                "failed_locator": "#old",
                "original_element_baseline": {
                    "status": "MISSING",
                    "fingerprint": None,
                    "reason": "no_prior_successful_matching_locator",
                },
                "storage_state_status": "AVAILABLE",
                "storage_state_ciphertext": encrypted_state,
                "replay": {
                    "status": "NOT_STARTED",
                    "safe_point": "captured_storage_state_and_url",
                    "replayed_steps": [],
                    "not_replayed_steps": ["click:#submit"],
                    "message": "No actions replayed.",
                },
                "evidence_gaps": [],
            }
        },
    }

    capture = capture_failure_snapshot_event(event, ephemeral_key=ephemeral_key, master_key=master_key)

    assert capture is not None
    assert capture.bundle.url == "https://shop.example/checkout"
    assert capture.bundle.original_element_baseline.status == "MISSING"
    assert capture.bundle.replay.not_replayed_steps == ["click:#submit"]
    assert capture.encrypted_storage_state and capture.encrypted_storage_state.startswith("enc_")
    assert "fixture-auth-token" not in capture.model_dump_json()
    assert SecretStore(master_key).decrypt_secret(capture.encrypted_storage_state) == raw_state


def test_oversized_or_invalid_snapshot_event_does_not_fail_the_runner():
    oversized = {
        "type": "session.finished",
        "session_id": "browser-session",
        "page_id": "page-id",
        "nodeid": "tests/test_checkout.py::test_checkout",
        "page_evidence": {
            "failure_snapshot": {
                "status": "CAPTURED",
                "storage_state_status": "AVAILABLE",
                "storage_state_ciphertext": "x" * 3_000_001,
                "evidence_gaps": [],
            }
        },
    }
    capture = capture_failure_snapshot_event(
        oversized,
        ephemeral_key=FailureSnapshotCipher.generate_ephemeral_key(),
        master_key="test-platform-master-key",
    )
    assert capture is not None
    assert capture.encrypted_storage_state is None
    assert capture.bundle.storage_state_status == "UNAVAILABLE"
    assert "storage_state_exceeds_transfer_limit" in capture.bundle.evidence_gaps

    oversized["page_evidence"]["failure_snapshot"] = {"status": "INVALID"}
    assert (
        capture_failure_snapshot_event(
            oversized,
            ephemeral_key=FailureSnapshotCipher.generate_ephemeral_key(),
            master_key="test-platform-master-key",
        )
        is None
    )


@pytest.mark.asyncio
async def test_snapshot_storage_state_is_encrypted_and_deleted_after_ttl(client, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Snapshot TTL", "bootstrap_workspace": False})).json()
    async with test_db_session() as session:
        run = await TestRunRepository(session).create_run(
            RunCreate(project_id=project["id"], workspace_id=project["id"])
        )
        execution = await TestRunRepository(session).add_execution(
            run.id, "tests/test_checkout.py::test_checkout", status=RunStatus.FAILED
        )
        failure = await TestRunRepository(session).create_failure_record(
            run_id=run.id,
            execution_id=execution.id,
            test_nodeid=execution.nodeid,
            test_name="test_checkout",
            classification="LOCATOR_CHANGED",
            exception_type="TimeoutError",
            error_message='Timeout waiting for locator("#old")',
            stack_trace="tests/test_checkout.py:10",
            failing_locator="#old",
        )
        row = BrowserSessionORM(
            id="browser-session",
            run_id=run.id,
            case_execution_id=execution.id,
            browser_session_id="browser-session",
            page_id="page-id",
            nodeid=execution.nodeid,
            current_url="https://shop.example/checkout",
        )
        session.add(row)
        await session.commit()
        failure = await FailureRepository(session).get_by_id(failure.id)
        raw_state = json.dumps({"cookies": [{"name": "auth", "value": "fixture-auth-token"}]})
        capture = FailureSnapshotCapture(
            browser_session_id=row.browser_session_id,
            page_id=row.page_id,
            worker_id=row.worker_id,
            nodeid=failure.test_nodeid,
            case_name="test_checkout",
            bundle=FailureSnapshotBundle(
                status="CAPTURED",
                captured_at=utc_now(),
                url=row.current_url,
                failed_locator="#old",
                storage_state_status="AVAILABLE",
                replay=FailureReplaySummary(
                    status="NOT_STARTED",
                    safe_point="captured_storage_state_and_url",
                    not_replayed_steps=["click:#submit"],
                ),
            ),
            encrypted_storage_state=SecretStore("test-platform-master-key").encrypt_secret(raw_state),
        )
        repository = BrowserSessionRepository(session)
        await repository.save_failure_snapshot(
            run_id=failure.run_id,
            execution_id=failure.execution_id,
            capture=capture,
            storage_state_ttl_seconds=60,
        )
        await session.commit()
        assert row.encrypted_storage_state != raw_state
        assert "fixture-auth-token" not in row.failure_snapshot_json
        row.storage_state_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()
        encrypted_before_read = row.encrypted_storage_state

        failure_repository = FailureRepository(session)
        bundle, encrypted = await failure_repository.latest_failure_snapshot(failure.execution_id)

        assert encrypted is None
        assert bundle.storage_state_status == "EXPIRED"
        assert "storage_state_expired" in bundle.evidence_gaps
        assert row.encrypted_storage_state == encrypted_before_read
        assert await failure_repository.purge_expired_failure_snapshots() == 1
        await session.commit()
        assert row.encrypted_storage_state is None


@pytest.mark.asyncio
async def test_locator_repair_restores_authenticated_fixture_page_from_failure_snapshot(
    client, test_db_session, tmp_path
):
    authenticated_requests = []

    class ProtectedSite(BaseHTTPRequestHandler):
        def do_GET(self):
            authenticated = "qa-auth=fixture-auth-token" in self.headers.get("Cookie", "")
            authenticated_requests.append(authenticated)
            body = (
                b'<main><h1>Protected checkout</h1><button aria-label="Complete purchase">Pay</button></main>'
                if authenticated
                else b"<main><h1>Login required</h1></main>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), ProtectedSite)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    protected_url = f"http://127.0.0.1:{server.server_port}/checkout"
    try:
        project = (
            await client.post("/api/projects", json={"name": "Protected locator repair", "bootstrap_workspace": False})
        ).json()
        fixture_source = f"""import pytest
from playwright.sync_api import sync_playwright

BASE_URL = {protected_url!r}

def launch_browser(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as error:
        for channel in ("chrome", "msedge"):
            try:
                return playwright.chromium.launch(headless=True, channel=channel)
            except Exception:
                pass
        raise error

@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context()
        context.add_cookies([{{"name": "qa-auth", "value": "fixture-auth-token", "url": BASE_URL}}])
        page = context.new_page()
        yield page
        browser.close()
"""
        test_source = """from conftest import BASE_URL
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

def test_checkout(page):
    page.goto(BASE_URL)
    try:
        page.locator("#purchase-now").click(timeout=100)
    except PlaywrightTimeoutError as error:
        raise AssertionError("Checkout locator #purchase-now is missing") from error
"""
        for path, content in (("conftest.py", fixture_source), ("tests/test_checkout.py", test_source)):
            response = await client.put(
                f"/api/workspaces/{project['id']}/file", json={"path": path, "content": content}
            )
            assert response.status_code == 200, response.text

        run_response = await client.post(
            "/api/runs",
            json={
                "project_id": project["id"],
                "workspace_id": project["id"],
                "nodeids": ["tests/test_checkout.py::test_checkout"],
                "runner_type": "LOCAL",
                "requested_by": "failure snapshot acceptance",
            },
        )
        assert run_response.status_code == 201, run_response.text
        run = run_response.json()
        for _ in range(160):
            if run["status"] in {"PASSED", "FAILED", "ERROR", "CANCELLED"}:
                break
            await asyncio.sleep(0.25)
            status_response = await client.get(f"/api/runs/{run['id']}")
            assert status_response.status_code == 200, status_response.text
            run = status_response.json()
        assert run["status"] == "FAILED", run
        failures = await client.get(f"/api/failures?project_id={project['id']}")
        assert failures.status_code == 200, failures.text
        failure = next(item for item in failures.json() if item["run_id"] == run["id"])
        assert run["browser_sessions"], (run.get("log_output") or "")[-5000:]
        serialized_sessions = json.dumps(run["browser_sessions"])
        assert "encrypted_storage_state" not in serialized_sessions
        assert "fixture-auth-token" not in serialized_sessions
        assert all("failure_snapshot" not in item["page_evidence"] for item in run["browser_sessions"])

        async with test_db_session() as session:
            browser = (
                await session.execute(
                    select(BrowserSessionORM).where(BrowserSessionORM.case_execution_id == failure["execution_id"])
                )
            ).scalar_one()
            assert browser.encrypted_storage_state.startswith("enc_")
            assert "fixture-auth-token" not in browser.encrypted_storage_state
            service = get_failure_service(session)
            bundle, encrypted = await service.get_failure_snapshot(failure["execution_id"])
            restored_raw = SecretStore().decrypt_secret(encrypted)
            assert bundle.storage_state_status == "AVAILABLE"
            assert "fixture-auth-token" in restored_raw

            class JevChoice:
                async def choose(self, request, **_kwargs):
                    from project_model.models import DecisionResult

                    return DecisionResult(
                        choice=request.options[0].key,
                        provider="jev",
                        model="snapshot-test-jev",
                        confidence=0.99,
                        fallback_used=False,
                    )

            workflow_service = FailureWorkflowService(service)
            analysis_id = await workflow_service._history_create(failure["id"])

            async def persist_progress(event):
                await workflow_service._history_append(analysis_id, event)

            proposal = await service.generate_repair_proposal(
                failure["id"],
                diagnosis_override=FailureAnalysisResponse(
                    classification="LOCATOR_CHANGED",
                    root_cause="The protected page uses the replacement purchase button.",
                    provider="openai-compatible",
                    fallback_used=False,
                    confidence=0.96,
                ),
                resolved_classification="LOCATOR_CHANGED",
                decision_service=LocatorDecisionService(decision_service=JevChoice()),
                on_event=persist_progress,
            )
            await session.commit()
            workflow = await workflow_service.get_repair_workflow(failure["id"])
            recorded = next(
                row for row in await workflow_service._history_list(failure["id"]) if row["id"] == analysis_id
            )
            event_types = {event["type"] for event in recorded["events"]}
            assert {"repair.progress", "locator_history_started", "decision_started"} <= event_types
            assert proposal.verified is True
            assert proposal.decision_summary["verification_source"] == "playwright"
            assert proposal.verification_replay.status == "RESTORED"
            assert proposal.verification_replay.replayed_steps == []
            assert any(
                "click:" in step and "purchase-now" in step for step in proposal.verification_replay.not_replayed_steps
            )
            assert workflow.failure_snapshot.replay.status == "RESTORED"

            browser.encrypted_storage_state = "enc_invalid"
            await session.commit()
            failed_restore = await service.generate_repair_proposal(
                failure["id"],
                diagnosis_override=FailureAnalysisResponse(
                    classification="LOCATOR_CHANGED",
                    root_cause="The saved browser state can no longer be decrypted.",
                    provider="openai-compatible",
                    fallback_used=False,
                    confidence=0.96,
                ),
                resolved_classification="LOCATOR_CHANGED",
                decision_service=LocatorDecisionService(decision_service=JevChoice()),
            )
            assert failed_restore.verification_replay.status == "RESTORE_FAILED"
            assert failed_restore.verification_reason.startswith("storage_state_restore_failed:")
            failed_workflow = await FailureWorkflowService(service).get_repair_workflow(failure["id"])
            assert failed_workflow.failure_snapshot.replay.status == "RESTORE_FAILED"
        assert authenticated_requests.count(True) >= 2, authenticated_requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_locator_repair_reuses_only_verified_recorder_candidates_for_the_same_page():
    bundle = {
        "version": "v1.0",
        "steps": [
            {
                "action": "click",
                "url": "https://shop.example/checkout",
                "evidence": {
                    "element": {"tag": "button", "role": "button", "name": "Purchase"},
                    "locator_candidates": [
                        {
                            "candidate_id": "candidate_1",
                            "kind": "role",
                            "value": "button",
                            "name": "Purchase",
                            "exact": True,
                            "verification": {"verified": True},
                        },
                        {
                            "candidate_id": "candidate_2",
                            "kind": "css",
                            "value": ".stale",
                            "verification": {"verified": False},
                        },
                    ],
                },
            },
            {
                "url": "https://shop.example/cart",
                "evidence": {
                    "locator_candidates": [
                        {
                            "kind": "test_id",
                            "value": "other-page",
                            "verification": {"verified": True},
                        }
                    ]
                },
            },
        ],
    }

    candidates = FailureService._recorder_evidence_candidates(bundle, "https://shop.example/checkout?run=secret")

    assert len(candidates) == 1
    assert candidates[0]["value"] == "button"
    assert candidates[0]["name"] == "Purchase"
    assert candidates[0]["evidence"]["source"] == "recorder_element_evidence"
    assert candidates[0]["evidence"]["recorded_verification"] is True

    archived = FailureService._recorder_evidence_candidates(
        {"version": "v1.0", "steps": [], "revisions": [{"revision": 1, "steps": bundle["steps"]}]},
        "https://shop.example/checkout",
    )
    assert archived[0]["evidence"]["evidence_revision"] == 1
