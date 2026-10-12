from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from project_model.models import FailureSnapshotBundle
from pydantic import ValidationError

from qa_core.execution.models import FailureSnapshotCapture
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.failure.snapshot_crypto import FailureSnapshotCipher


def _add_evidence_gap(bundle: dict[str, Any], gap: str) -> None:
    gaps = bundle.get("evidence_gaps")
    if not isinstance(gaps, list):
        gaps = []
    bundle["evidence_gaps"] = [*gaps, gap][:100]


def capture_failure_snapshot_event(
    event: dict[str, Any], *, ephemeral_key: str, master_key: str
) -> FailureSnapshotCapture | None:
    """Convert a plugin failure event to a safe runner transfer with storage state re-encrypted at rest."""
    if event.get("type") != "session.finished":
        return None
    page_evidence = event.get("page_evidence")
    raw_bundle = page_evidence.get("failure_snapshot") if isinstance(page_evidence, dict) else None
    if not isinstance(raw_bundle, dict):
        return None

    bundle_payload = {key: value for key, value in raw_bundle.items() if key != "storage_state_ciphertext"}
    bundle_payload = SensitiveRedactor.redact_value(bundle_payload)
    encrypted_state = None
    ephemeral_ciphertext = raw_bundle.get("storage_state_ciphertext")
    if isinstance(ephemeral_ciphertext, str) and ephemeral_ciphertext and master_key:
        if len(ephemeral_ciphertext) > 3_000_000:
            bundle_payload["storage_state_status"] = "UNAVAILABLE"
            _add_evidence_gap(bundle_payload, "storage_state_exceeds_transfer_limit")
        else:
            raw_state = FailureSnapshotCipher.decrypt_ephemeral(ephemeral_ciphertext, ephemeral_key)
            if raw_state:
                encrypted_state = FailureSnapshotCipher.encrypt_at_rest(raw_state, master_key)
            else:
                bundle_payload["storage_state_status"] = "UNAVAILABLE"
                _add_evidence_gap(bundle_payload, "storage_state_decryption_failed")
    elif bundle_payload.get("storage_state_status") == "AVAILABLE":
        bundle_payload["storage_state_status"] = "UNAVAILABLE"
        _add_evidence_gap(bundle_payload, "storage_state_encryption_unavailable")

    try:
        bundle = FailureSnapshotBundle.model_validate(bundle_payload)
    except ValidationError:
        return None
    if encrypted_state is None and bundle.storage_state_status == "AVAILABLE":
        bundle.storage_state_status = "UNAVAILABLE"
    captured_at = bundle.captured_at
    if isinstance(captured_at, datetime) and captured_at.tzinfo is None:
        bundle.captured_at = captured_at.replace(tzinfo=timezone.utc)

    session_id = str(event.get("session_id") or "")
    page_id = str(event.get("page_id") or session_id)
    nodeid = str(event.get("nodeid") or "")
    if not session_id or not page_id or not nodeid:
        return None
    return FailureSnapshotCapture(
        browser_session_id=session_id[:36],
        page_id=page_id[:36],
        worker_id=str(event.get("worker_id") or "main")[:100],
        nodeid=nodeid[:500],
        case_name=str(event.get("case_name") or nodeid.split("::")[-1])[:250],
        bundle=bundle,
        encrypted_storage_state=encrypted_state,
    )
