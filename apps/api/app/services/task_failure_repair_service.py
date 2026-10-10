from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from project_model.task_models import EvidenceType
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.redactor import SensitiveRedactor

from app.domain.task_records import TaskRecord as TaskExecutionRecord
from app.services.ai_runtime import build_ai_orchestrator
from app.services.task_ai_service import TaskAIService
from app.services.task_approval import approval_granted
from app.services.task_errors import TaskBlocked
from app.services.task_execution_ports import TaskExecutionPorts
from app.services.workspace_service import WorkspaceService


class TaskFailureRepairService:
    """Own task failure diagnosis, repair preparation and approved repair application."""

    def __init__(self, context: TaskExecutionPorts, *, ai_service: TaskAIService) -> None:
        self.context = context
        self.ai_service = ai_service

    async def _inspect_failure_source(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        failure = outputs.get("collect", {})
        path = failure.get("test_nodeid", "").split("::", 1)[0] or str(self.context.input(task, "file_path", ""))
        return await self.context.inspect_source(task, outputs, path)

    async def _collect_failure(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        failure_id = str(self.context.input(task, "failure_id", ""))
        if not failure_id:
            raise TaskBlocked("FixFailureTask requires failure_id.")
        async with self.context.repository_scope() as repositories:
            run_repository = repositories.test_runs
            failure = await run_repository.get_failure_by_id(failure_id)
            source_run = await run_repository.get_by_id(failure.run_id) if failure else None
            if failure is None or source_run is None or (task.project_id and source_run.project_id != task.project_id):
                raise TaskBlocked("Failure record was not found.")
            from app.services.failure_evidence_service import FailureEvidenceService

            browser = await repositories.failures.latest_browser_session(failure.execution_id)
            page = browser.get("page_evidence_json") if browser else None
            if isinstance(page, str):
                try:
                    page = json.loads(page)
                except ValueError:
                    page = {}
            evidence_bundle = await FailureEvidenceService.collect(
                failure, source_run, WorkspaceService(), browser=browser, page=page
            )
            result = {
                "id": failure.id,
                "run_id": failure.run_id,
                "test_nodeid": failure.test_nodeid,
                "classification": failure.classification,
                "exception_type": failure.exception_type,
                "error_message": SensitiveRedactor.redact_text(failure.error_message or ""),
                "stack_trace": SensitiveRedactor.redact_text(failure.stack_trace or "")[-12000:],
                "failing_locator": SensitiveRedactor.redact_text(failure.failing_locator or "") or None,
                "screenshot_path": failure.screenshot_path,
                "trace_path": failure.trace_path,
                "dom_snapshot_path": failure.dom_snapshot_path,
                "repair_proposal": SensitiveRedactor.redact_value(failure.repair_proposal)
                if failure.repair_proposal
                else None,
                "evidence_bundle": evidence_bundle.model_dump(mode="json"),
                "rendered_evidence": evidence_bundle.render(),
            }
        evidence = [
            await self.context.evidence(
                task,
                "collect",
                EvidenceType.PYTEST_TRACEBACK,
                "failure_records + test_executions",
                f"Collected {result['exception_type']} for {result['test_nodeid']}.",
                result["stack_trace"],
                {"failure_id": failure_id, "stored_classification": result["classification"]},
            )
        ]
        if result["screenshot_path"]:
            evidence.append(
                await self.context.evidence(
                    task,
                    "collect",
                    EvidenceType.SCREENSHOT,
                    "failure_records",
                    "Screenshot path captured by the run.",
                    None,
                    {"path": result["screenshot_path"]},
                )
            )
        if result["trace_path"]:
            evidence.append(
                await self.context.evidence(
                    task,
                    "collect",
                    EvidenceType.PLAYWRIGHT_TRACE,
                    "failure_records",
                    "Playwright trace path captured by the run.",
                    None,
                    {"path": result["trace_path"]},
                )
            )
        result["_evidence"] = evidence
        return result

    async def _classify_failure(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        failure = outputs.get("collect", {})
        category, explanation, locator = FailureClassifier.classify(
            failure.get("error_message", ""), failure.get("stack_trace", "")
        )
        return {
            "classification": category.value,
            "root_cause": explanation,
            "failing_locator": locator or failure.get("failing_locator"),
            "evidence": [failure.get("error_message", ""), *failure.get("stack_trace", "").splitlines()[-8:]],
            "_evidence": [
                await self.context.evidence(
                    task,
                    "classify",
                    EvidenceType.ANALYSIS,
                    "FailureClassifier",
                    f"Rule-based classification: {category.value}.",
                    json.dumps(
                        {"error_message": failure.get("error_message"), "classification": category.value},
                        ensure_ascii=False,
                    ),
                    {"confidence": "heuristic", "locator_observed": bool(locator)},
                )
            ],
        }

    async def _diagnose_failure(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        failure = outputs.get("collect", {})
        rules = outputs.get("classify", {})
        if not await self.ai_service.reserve_ai_call(task.id):
            repairable = rules.get("classification") == "LOCATOR_CHANGED" and bool(
                (failure.get("evidence_bundle") or {}).get("page_url")
                and (failure.get("evidence_bundle") or {}).get("controls")
                or self.context.input(task, "proposed_locator")
                or failure.get("repair_proposal")
            )
            result = {
                "classification": rules.get("classification", "UNKNOWN"),
                "root_cause": rules.get(
                    "root_cause", "Task AI-call budget exhausted; no model diagnosis was performed."
                ),
                "evidence": rules.get("evidence", []),
                "hypotheses": [],
                "recommended_actions": [
                    "Review the captured traceback and inspected source before proposing a change."
                ],
                "confidence": 0.0,
                "provider": "FailureClassifier",
                "fallback_used": True,
                "repairable": repairable,
            }
            return {
                **result,
                "_evidence": [
                    await self.context.evidence(
                        task,
                        "diagnose",
                        EvidenceType.ANALYSIS,
                        "FailureClassifier",
                        "AI-call budget exhausted; returned the observed rule-based diagnosis.",
                        json.dumps(result, ensure_ascii=False),
                        {"ai_call_skipped": True},
                    )
                ],
            }
        orchestrator = build_ai_orchestrator()
        analysis = await orchestrator.diagnose_failure_ai(
            error_message=failure.get("error_message", ""),
            stack_trace=failure.get("stack_trace", ""),
            test_nodeid=failure.get("test_nodeid", ""),
            failing_locator=failure.get("failing_locator"),
            historical_context="Current bounded evidence (not historical proof):\n"
            + failure.get("rendered_evidence", "No additional evidence captured."),
        )
        completion = orchestrator.last_completion
        ai_fallback = (not completion) or completion.fallback_used or completion.provider.lower() == "fake"
        # Treat direct traceback classification as the evidence boundary. AI can enrich the
        # explanation, but cannot overwrite a clearly observed assertion/timeout category. If
        # the provider fell back to a local/fake completion, report the rule explanation instead
        # of presenting fallback prose as an AI root-cause finding.
        classification = rules.get("classification", "UNKNOWN")
        evidence_bundle = failure.get("evidence_bundle") or {}
        repairable = classification == "LOCATOR_CHANGED" and bool(
            evidence_bundle.get("page_url")
            and evidence_bundle.get("controls")
            or self.context.input(task, "proposed_locator")
            or failure.get("repair_proposal")
        )
        result = {
            "classification": classification,
            "root_cause": rules.get("root_cause") if ai_fallback else analysis.root_cause,
            "evidence": analysis.evidence,
            "hypotheses": analysis.hypotheses,
            "recommended_actions": analysis.recommended_actions,
            "confidence": analysis.confidence,
            "provider": "FailureClassifier" if ai_fallback else completion.provider,
            "fallback_used": ai_fallback,
            "repairable": repairable,
        }
        return {
            **result,
            "_evidence": [
                await self.context.evidence(
                    task,
                    "diagnose",
                    EvidenceType.ANALYSIS,
                    result["provider"],
                    f"Root cause analysis for evidence-backed category {classification}.",
                    json.dumps(result, ensure_ascii=False),
                    {"fallback_used": result["fallback_used"]},
                )
            ],
        }

    async def _prepare_repair(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        diagnosis = outputs.get("diagnose", {})
        failure = outputs.get("collect", {})
        source_info = outputs.get("inspect", {})
        path, source = source_info.get("file_path"), source_info.get("source", "")
        proposed = str(
            self.context.input(task, "proposed_text", "") or self.context.input(task, "proposed_locator", "")
        ).strip()
        old_locator = str(
            failure.get("failing_locator")
            or outputs.get("classify", {}).get("failing_locator")
            or self.context.input(task, "old_text", "")
            or self.context.input(task, "old_locator", "")
        ).strip()
        stored_proposal = failure.get("repair_proposal") or {}
        proposed = proposed or str(stored_proposal.get("proposed_locator", "")).strip()
        old_locator = old_locator or str(stored_proposal.get("old_locator", "")).strip()
        failure_evidence = failure.get("evidence_bundle") or {}
        observed_controls = failure_evidence.get("controls") or []
        has_failure_page_observation = bool(failure_evidence.get("page_url") and observed_controls)

        if not proposed:
            test_name = str(failure.get("test_nodeid") or "").split("::")[-1]
            tree = ast.parse(source)
            functions = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test_name
            ]
            for function in functions:
                for assertion in (node for node in ast.walk(function) if isinstance(node, ast.Assert)):
                    expression = assertion.test
                    if (
                        isinstance(expression, ast.Compare)
                        and len(expression.ops) == 1
                        and isinstance(expression.ops[0], ast.Eq)
                    ):
                        try:
                            left, right = ast.literal_eval(expression.left), ast.literal_eval(expression.comparators[0])
                        except (ValueError, TypeError):
                            continue
                        if left != right:
                            raise TaskBlocked(
                                "The failed test contains a deterministically false literal assertion. Confirm the intended expectation before proposing a code change; the assertion is retained."
                            )

        if proposed and old_locator and old_locator in source:
            updated = source.replace(old_locator, proposed, 1)
        else:
            if (
                diagnosis.get("classification") == "LOCATOR_CHANGED"
                and not failure.get("dom_snapshot_path")
                and not has_failure_page_observation
                and not self.context.input(task, "url")
                and not proposed
            ):
                raise TaskBlocked(
                    "Locator repair needs a DOM snapshot, a failure-time browser observation with a page URL and observed controls, or a user-supplied proposed_locator; no source was changed."
                )
            result = await self.context.call_code_ai(
                task,
                "Repair the failing test based on the exact failure evidence and inspected source. "
                "Keep the change minimal. Preserve business expectations and assertions; never change an expected value merely to make a test pass. Return the complete replacement test module in suggested_code; "
                "do not claim a repair if the evidence is insufficient.\n"
                f"Goal: {task.goal}\nClassification: {diagnosis.get('classification')}\n"
                f"User-proposed locator candidate: {proposed or 'none'}\n"
                f"Failure: {failure.get('error_message')}\nTraceback:\n{failure.get('stack_trace')}\n"
                f"Source path: {path}\nSource:\n{source}\n"
                f"Bounded source, fixtures and execution evidence:\n{failure.get('rendered_evidence', '')}\n"
                "Use any page URL and observed controls from the failure evidence bundle above to ground locator changes. "
                "If that evidence does not support a safe replacement, return the source unchanged.",
            )
            updated = result.suggested_code or ""
            original_assertions = [
                ast.dump(node, include_attributes=False)
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Assert)
            ]
            proposed_assertions = [
                ast.dump(node, include_attributes=False)
                for node in ast.walk(ast.parse(updated))
                if isinstance(node, ast.Assert)
            ]
            if original_assertions != proposed_assertions:
                raise TaskBlocked(
                    "AI repair changed an existing assertion. The proposal was not applied; review intended expectations explicitly."
                )
        self.context.validate_python_test(updated, path)
        if updated == source:
            raise TaskBlocked("The proposed repair does not change the inspected source.")
        artifact = await self.context.artifact(
            task, "repair", Path(path).name, "PATCH_PROPOSAL", updated.encode(), "text/x-python"
        )
        return {
            "file_path": path,
            "target_file": path,
            "suggested_code": updated,
            "old_code": source,
            "classification": diagnosis.get("classification"),
            "artifact_id": artifact["artifact_id"],
            "_artifacts": [artifact],
            "_evidence": [
                await self.context.evidence(
                    task,
                    "repair",
                    EvidenceType.GIT_DIFF,
                    "task.repair.proposal",
                    f"Proposed a reviewed replacement for {path}; it has not been applied.",
                    updated,
                    {"base_source_length": len(source), "classification": diagnosis.get("classification")},
                    artifact["artifact_id"],
                )
            ],
        }

    async def _apply_repair(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        proposal = outputs.get("repair", {})
        if not proposal.get("suggested_code") or not proposal.get("file_path"):
            raise TaskBlocked("No repair proposal is available to apply.")
        if not self._approval_granted(outputs):
            raise TaskBlocked("Repair cannot be applied without an explicit approval step.")
        await self.context.write_approved_source(task, outputs, proposal["file_path"], proposal["suggested_code"])
        return {
            "written": True,
            "file_path": proposal["file_path"],
            "characters": len(proposal["suggested_code"]),
            "_evidence": [
                await self.context.evidence(
                    task,
                    "apply",
                    EvidenceType.SOURCE_CODE,
                    "workspace.write_file",
                    f"User-approved repair applied to {proposal['file_path']}.",
                    proposal["suggested_code"],
                    {"approved": True, "file_path": proposal["file_path"]},
                )
            ],
        }

    @staticmethod
    def _approval_granted(outputs: dict[str, Any]) -> bool:
        return approval_granted(outputs)

    async def _validate_workspace(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        report = await WorkspaceService().validate_workspace(task.workspace_id or "")
        summary = {"valid": report.valid, "issues": [issue.model_dump(mode="json") for issue in report.issues[:100]]}
        if not report.valid:
            raise TaskBlocked(
                f"Workspace validation failed with {len(report.issues)} issue(s); inspect evidence before another edit."
            )
        return {
            **summary,
            "_evidence": [
                await self.context.evidence(
                    task,
                    "validate",
                    EvidenceType.ANALYSIS,
                    "workspace.validate",
                    "Workspace syntax and collection validation passed.",
                    json.dumps(summary, ensure_ascii=False),
                    {"valid": report.valid},
                )
            ],
        }
