"""Security negative tests for the guards added in Round 5.

These cover two real gaps found by the read-only audit: an artifact row pointing outside the storage
root turned the download route into an arbitrary-file read, and applying an AI repair patch — a write
to the customer's repository — left no audit trail.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.api.failures import get_failure_service
from app.persistence.models import ArtifactORM
from app.services.locator_decision_service import LocatorDecisionService
from qa_core.ai.models import FailureAnalysisResponse
from test_failure_workflow import RecordingDecision, seed

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_artifact_download_refuses_a_path_outside_the_storage_root(client, test_db_session, tmp_path: Path):
    secret = tmp_path / "outside-storage.txt"
    secret.write_text("not an artifact", encoding="utf-8")
    async with test_db_session() as session:
        session.add(
            ArtifactORM(
                id="artifact_tampered",
                filename="outside-storage.txt",
                size_bytes=secret.stat().st_size,
                content_type="text/plain",
                storage_type="LOCAL",
                storage_path=str(secret),
            )
        )
        await session.commit()

    download = await client.get("/api/artifacts/artifact_tampered/download")
    assert download.status_code == 404, download.text
    info = await client.get("/api/artifacts/artifact_tampered/info")
    assert info.status_code == 200  # metadata is fine; only the bytes are refused


@pytest.mark.asyncio
async def test_applying_a_repair_is_recorded_in_the_security_audit(
    client, test_db_session, local_html_url, monkeypatch
):
    url = local_html_url('<button type="submit">Continue</button>')
    _project_id, failure_id, _ = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#old-submit")',
        kind="UI",
        candidates=[{"kind": "role", "value": "button", "name": "Continue", "exact": True}],
        url=url,
        source='def test_workflow(page):\n    page.locator("#old-submit").click()\n',
    )

    from app.persistence.models import FailureAnalysisORM

    async with test_db_session() as session:
        service = get_failure_service(session)
        proposal = await service.generate_repair_proposal(
            failure_id,
            diagnosis_override=FailureAnalysisResponse(
                classification="LOCATOR_CHANGED",
                root_cause="The submit button moved.",
                provider="openai-compatible",
                fallback_used=False,
                confidence=0.95,
            ),
            resolved_classification="LOCATOR_CHANGED",
            decision_service=LocatorDecisionService(decision_service=RecordingDecision()),
        )
        analysis_id = "audit-repair-apply"
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={"repair_state": "PATCH_READY", "repair_proposal": proposal.model_dump(mode="json")},
            )
        )
        await session.commit()

    applied = await client.post(
        f"/api/failures/{failure_id}/analyses/{analysis_id}/apply",
        json={
            "file_path": proposal.file_path,
            "old_code": proposal.source_locator,
            "new_code": proposal.proposed_locator,
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["repair"]["state"] == "PATCH_APPLIED"

    audit = await client.get("/api/audit/security", params={"action": "REPAIR_APPLY"})
    assert audit.status_code == 200, audit.text
    entries = audit.json()
    entry = next(item for item in entries if failure_id in item["target_resource"])
    assert entry["actor_email"] == "admin@ai-qa.local"
    assert entry["actor_id"] != "system"
    assert entry["status"] == "SUCCESS"

    rolled_back = await client.post(f"/api/failures/{failure_id}/analyses/{analysis_id}/rollback")
    assert rolled_back.status_code == 200, rolled_back.text
    rollback_audit = (await client.get("/api/audit/security", params={"action": "REPAIR_ROLLBACK"})).json()
    assert any(failure_id in item["target_resource"] for item in rollback_audit)
