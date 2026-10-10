from __future__ import annotations

from qa_core.ai.context import ContextSelector
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.evidence import FailureEvidenceBundle
from qa_core.failure.redactor import SensitiveRedactor

from app.settings import get_config


class FailureEvidenceService:
    @staticmethod
    async def collect(record, run, workspace_service, browser=None, page=None):
        config = get_config()
        evidence_policy = config.evidence
        failure_policy = config.failure
        bundle = (
            ContextSelector().select(
                workspace_service.get_workspace_dir(run.workspace_id),
                test_nodeid=record.test_nodeid,
            )
            if run
            else None
        )
        page = page or {}
        controls = SensitiveRedactor.redact_value(page.get("controls", [])[: evidence_policy.max_console_entries])
        artifacts = {
            key: value
            for key, value in {
                "screenshot": record.screenshot_path,
                "trace": record.trace_path,
                "dom": record.dom_snapshot_path,
            }.items()
            if value
        }
        console = (
            SensitiveRedactor.redact_value(
                (record.console_logs or page.get("console_logs") or [])[-evidence_policy.max_console_entries :]
            )
            if failure_policy.capture_console and evidence_policy.max_console_entries
            else []
        )
        network = (
            SensitiveRedactor.redact_value((page.get("network_logs") or [])[-evidence_policy.max_network_entries :])
            if failure_policy.capture_network and evidence_policy.max_network_entries
            else []
        )
        missing = [
            key
            for key, present in {
                "screenshot": record.screenshot_path if failure_policy.capture_screenshot else None,
                "trace": record.trace_path,
                "dom": record.dom_snapshot_path if failure_policy.capture_dom else None,
                "network": network,
                "console": console,
                "browser_page": page,
                "source": bundle and bundle.fragments,
            }.items()
            if not present
        ]
        traceback_limit = max(0, failure_policy.traceback_chars)
        error = SensitiveRedactor.redact_text(record.error_message or "")[:traceback_limit]
        screenshot_count = max(0, evidence_policy.max_screenshots)
        if not screenshot_count:
            artifacts.pop("screenshot", None)
        return FailureEvidenceBundle(
            nodeid=record.test_nodeid,
            failure_kind=FailureClassifier.failure_kind(error, record.stack_trace or ""),
            error=error,
            traceback=(
                SensitiveRedactor.redact_text(record.stack_trace or "")[-traceback_limit:] if traceback_limit else ""
            ),
            assertion=error if "assert" in error.lower() else "",
            stdout=SensitiveRedactor.redact_text(run.log_output or "")[-4000:] if run else "",
            page_url=SensitiveRedactor.redact_url((browser or {}).get("current_url") or str(page.get("url") or "")),
            failing_locator=SensitiveRedactor.redact_text(record.failing_locator or "") or None,
            artifacts=artifacts,
            console=console,
            network=network,
            recent_steps=SensitiveRedactor.redact_value((page.get("recent_steps") or [])[-10:]),
            controls=controls,
            source_context=bundle.render()[: failure_policy.source_context_chars] if bundle else "",
            context_paths=bundle.paths if bundle else [],
            missing=missing,
        )
