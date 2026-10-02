from __future__ import annotations

from qa_core.ai.context import ContextSelector
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.evidence import FailureEvidenceBundle
from qa_core.failure.redactor import SensitiveRedactor

from app.persistence.models import TestRunORM


class FailureEvidenceService:
    @staticmethod
    async def collect(record, session, workspace_service, browser=None, page=None):
        run = await session.get(TestRunORM, record.run_id)
        bundle = (
            ContextSelector().select(
                workspace_service.get_workspace_dir(run.workspace_id),
                test_nodeid=record.test_nodeid,
            )
            if run
            else None
        )
        page = page or {}
        controls = SensitiveRedactor.redact_value(page.get("controls", [])[:30])
        artifacts = {
            key: value
            for key, value in {
                "screenshot": record.screenshot_path,
                "trace": record.trace_path,
                "dom": record.dom_snapshot_path,
            }.items()
            if value
        }
        console = SensitiveRedactor.redact_value((record.console_logs or page.get("console_logs") or [])[-30:])
        network = SensitiveRedactor.redact_value((page.get("network_logs") or [])[-30:])
        missing = [
            key
            for key, present in {
                "screenshot": record.screenshot_path,
                "trace": record.trace_path,
                "dom": record.dom_snapshot_path,
                "network": network,
                "console": console,
                "browser_page": page,
                "source": bundle and bundle.fragments,
            }.items()
            if not present
        ]
        error = SensitiveRedactor.redact_text(record.error_message or "")[:3000]
        return FailureEvidenceBundle(
            nodeid=record.test_nodeid,
            failure_kind=FailureClassifier.failure_kind(error, record.stack_trace or ""),
            error=error,
            traceback=SensitiveRedactor.redact_text(record.stack_trace or "")[-8000:],
            assertion=error if "assert" in error.lower() else "",
            stdout=SensitiveRedactor.redact_text(run.log_output or "")[-4000:] if run else "",
            page_url=SensitiveRedactor.redact_url(browser.current_url if browser else str(page.get("url") or "")),
            failing_locator=SensitiveRedactor.redact_text(record.failing_locator or "") or None,
            artifacts=artifacts,
            console=console,
            network=network,
            recent_steps=SensitiveRedactor.redact_value((page.get("recent_steps") or [])[-10:]),
            controls=controls,
            source_context=bundle.render()[:8000] if bundle else "",
            context_paths=bundle.paths if bundle else [],
            missing=missing,
        )
