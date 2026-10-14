from __future__ import annotations

import json

from qa_core.ai.context import ContextSelector
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.evidence import FailureEvidenceBundle
from qa_core.failure.redactor import SensitiveRedactor

from app.settings import get_config


class FailureEvidenceService:
    @staticmethod
    def _compact_recorder_evidence(bundle: dict, page_url: str) -> dict:
        if not isinstance(bundle, dict) or bundle.get("version") != "v1.0":
            return {}
        current_url = SensitiveRedactor.redact_url(page_url)
        revisions = bundle.get("revisions")
        versions = (
            [bundle, *reversed([item for item in revisions if isinstance(item, dict)])]
            if isinstance(revisions, list)
            else [bundle]
        )
        compact_steps = []
        compact_revisions = []
        matching_step_count = 0
        total_steps = sum(len(item.get("steps", [])) for item in versions if isinstance(item.get("steps"), list))
        for version_index, version in enumerate(versions):
            selected = []
            for step in version.get("steps", []):
                if not isinstance(step, dict):
                    continue
                url = SensitiveRedactor.redact_url(str(step.get("url") or ""))
                if current_url and url != current_url:
                    continue
                evidence = step.get("evidence") if isinstance(step.get("evidence"), dict) else {}
                element = evidence.get("element") if isinstance(evidence.get("element"), dict) else {}
                candidates = [
                    {
                        key: candidate[key]
                        for key in ("candidate_id", "kind", "value", "name", "exact", "nth", "verification")
                        if key in candidate
                    }
                    for candidate in evidence.get("locator_candidates", [])
                    if isinstance(candidate, dict) and isinstance(candidate.get("value"), str)
                ][:8]
                selected.append(
                    {
                        "step_id": step.get("step_id"),
                        "evidence_id": step.get("evidence_id"),
                        "action": step.get("action"),
                        "url": url,
                        "evidence": {
                            "element": {key: element[key] for key in ("tag", "role", "name", "text") if key in element},
                            "locator_candidates": candidates,
                        },
                    }
                )
                matching_step_count += 1
                if len(compact_steps) + len(selected) >= 32:
                    break
            if selected:
                if version_index == 0:
                    compact_steps.extend(selected)
                else:
                    compact_revisions.append({"revision": version.get("revision", 1), "steps": selected})
            if len(compact_steps) + sum(len(item["steps"]) for item in compact_revisions) >= 32:
                break
        decisions = bundle.get("decision_history")
        compact = {
            "schema": bundle.get("schema", "element-evidence-bundle"),
            "version": bundle["version"],
            "revision": bundle.get("revision", 1),
            "binding_id": bundle.get("binding_id"),
            "test_case_id": bundle.get("test_case_id"),
            "captured_at": bundle.get("captured_at"),
            "step_count": total_steps,
            "matching_step_count": matching_step_count,
            "truncated": total_steps > 32,
            "steps": compact_steps,
            "revisions": compact_revisions,
            "decision_history": [item for item in decisions if isinstance(item, dict)][-30:]
            if isinstance(decisions, list)
            else [],
        }
        if len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > 64_000:
            compact.update(steps=[], revisions=[], decision_history=[], truncated=True)
        return compact

    @staticmethod
    async def collect(record, run, workspace_service, browser=None, page=None, recorder_evidence=None):
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
        evidence_url = (browser or {}).get("current_url") or str(page.get("url") or "")
        element_evidence = SensitiveRedactor.redact_value(
            FailureEvidenceService._compact_recorder_evidence(recorder_evidence or {}, evidence_url)
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
                "recorder_element_evidence": element_evidence,
            }.items()
            if not present
        ]
        if element_evidence:
            if not element_evidence.get("step_count"):
                missing.append("recorder_element_evidence_has_no_elements")
            elif not element_evidence.get("matching_step_count"):
                missing.append("recorder_element_evidence_page_mismatch")
        if element_evidence.get("truncated"):
            missing.append("recorder_element_evidence_truncated")
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
            page_url=SensitiveRedactor.redact_url(evidence_url),
            failing_locator=SensitiveRedactor.redact_text(record.failing_locator or "") or None,
            artifacts=artifacts,
            console=console,
            network=network,
            recent_steps=SensitiveRedactor.redact_value((page.get("recent_steps") or [])[-10:]),
            controls=controls,
            element_evidence=element_evidence,
            source_context=bundle.render()[: failure_policy.source_context_chars] if bundle else "",
            context_paths=bundle.paths if bundle else [],
            missing=missing,
        )
