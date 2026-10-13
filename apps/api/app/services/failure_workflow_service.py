from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from project_model.models import (
    FailureRepairState,
    FailureRepairWorkflow,
    TestRun,
    TestRunCreate,
)
from qa_core.ai.trace import AITraceEvent, make_trace_event
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.models import FailureCategory
from qa_core.failure.redactor import SensitiveRedactor

from app.ports.repository_scope import RepositoryScopeFactory
from app.services.ai_settings_service import AISettingsService
from app.services.failure_service import FailureService, LocatorRepairNotApplicableError
from app.services.locator_decision_service import LocatorDecisionService
from app.services.locator_history_service import LocatorHistoryService
from app.services.locator_repair_context import bind_locator_repair, reset_locator_repair
from app.services.locator_repair_state_machine import LocatorRepairStateMachine
from app.services.test_run_service import TestRunService
from app.services.workspace_service import SecurityException
from app.settings import get_config

RETRYABLE_CLASSIFICATIONS = {"LOCATOR_CHANGED", "AUTOMATION_DEFECT", "ENVIRONMENT", "NETWORK", "TIMING", "TEST_DATA"}
ISSUE_CLASSIFICATIONS = {"PRODUCT_DEFECT", "ENVIRONMENT"}
_TERMINAL_RUN_STATUSES = {"PASSED", "FAILED", "ERROR", "CANCELLED"}


def _repair_verification_nodeids(test_nodeid: str) -> list[str]:
    if get_config().repair.rerun_exact_nodeid:
        return [test_nodeid]
    return [test_nodeid.split("::", 1)[0]]


logger = logging.getLogger(__name__)


class FailureWorkflowService:
    """Own failure analysis and the exact-case repair verification workflow."""

    def __init__(
        self,
        failure_service: FailureService,
        decision_service: LocatorDecisionService | None = None,
        run_service: TestRunService | None = None,
        repository_scope: RepositoryScopeFactory | None = None,
        auto_repair_mode: str | None = None,
    ):
        self.failures = failure_service
        self.decisions = decision_service or LocatorDecisionService(repository_scope=repository_scope)
        self.run_service = run_service
        self.repository_scope = repository_scope or failure_service.repository_scope
        configured_mode = (
            get_config().repair.mode if get_config().repair.enabled and get_config().features.auto_repair else "OFF"
        )
        self.auto_repair_mode = (auto_repair_mode or configured_mode).upper()
        self._verification_monitors: set[asyncio.Task[None]] = set()
        self._monitored_verification_run_ids: set[str] = set()
        self.repair_state_machine = LocatorRepairStateMachine()
        if self.repository_scope is None:
            raise ValueError("FailureWorkflowService requires a repository scope")

    async def _history_list(self, failure_id: str) -> list[dict[str, Any]]:
        async with self.repository_scope() as repositories:
            return await repositories.failure_analyses.list(failure_id)

    async def _history_create(self, failure_id: str) -> str:
        async with self.repository_scope() as repositories:
            analysis_id = await repositories.failure_analyses.create(failure_id)
            await repositories.commit()
            return analysis_id

    async def _history_running(self, failure_id: str) -> str | None:
        async with self.repository_scope() as repositories:
            return await repositories.failure_analyses.get_running(failure_id)

    async def _history_claim(self, failure_id: str) -> tuple[str, bool]:
        async with self.repository_scope() as repositories:
            result = await repositories.failure_analyses.claim(failure_id)
            await repositories.commit()
            return result

    async def start_analysis(self, failure_id: str) -> tuple[str, bool]:
        """Claim the single active analysis slot for this failure."""
        if await self.failures.get_failure_state(failure_id) is None:
            raise ValueError("Failure record not found")
        active_id = await self._history_running(failure_id)
        if active_id:
            await self._ensure_locator_repair(
                failure_id,
                active_id,
                initial_state=FailureRepairState.ANALYZING,
            )
            return active_id, False
        workflow = await self.get_repair_workflow(failure_id)
        if "START_ANALYSIS" not in workflow.allowed_actions:
            active_id = await self._history_running(failure_id)
            if active_id:
                await self._ensure_locator_repair(
                    failure_id,
                    active_id,
                    initial_state=FailureRepairState.ANALYZING,
                )
                return active_id, False
            raise ValueError(f"Repair state {workflow.state} does not allow starting analysis")
        analysis_id, created = await self._history_claim(failure_id)
        await self._ensure_locator_repair(failure_id, analysis_id)
        return analysis_id, created

    @staticmethod
    def _repair_state_from_event(event: AITraceEvent, result: dict[str, Any] | None) -> FailureRepairState | None:
        state = (result or {}).get("repair_state") or event.metadata.get("state")
        if isinstance(state, str) and state in FailureRepairState._value2member_map_:
            return FailureRepairState(state)
        if event.type == "workflow.step":
            if event.stage == "decision" and event.status == "RUNNING":
                return FailureRepairState.DECIDING
            if event.stage == "decision" and event.status == "COMPLETED":
                return FailureRepairState.VERIFYING_CANDIDATE
            if event.stage == "repair" and event.status == "COMPLETED":
                return FailureRepairState.PATCH_READY
            if event.stage == "repair" and event.status == "BLOCKED":
                return FailureRepairState.BLOCKED
            if event.stage == "verification" and event.status == "RUNNING":
                return FailureRepairState.VERIFYING_FIX
        return None

    async def _locator_repair_for_analysis(self, analysis_id: str):
        async with self.repository_scope() as repositories:
            return await repositories.locator_repairs.get_by_analysis(analysis_id)

    async def _ensure_locator_repair(
        self,
        failure_id: str,
        analysis_id: str,
        *,
        initial_state: FailureRepairState = FailureRepairState.CREATED,
    ):
        async with self.repository_scope() as repositories:
            repair = await self.repair_state_machine.create(
                repositories.locator_repairs,
                failure_id=failure_id,
                analysis_id=analysis_id,
                initial_state=initial_state,
            )
            await repositories.commit()
            return repair

    async def _history_append(
        self, analysis_id: str, event: AITraceEvent, *, result: dict[str, Any] | None = None
    ) -> None:
        async with self.repository_scope() as repositories:
            source = await repositories.failure_analyses.get_state_source(analysis_id)
            target_state = self._repair_state_from_event(event, result)
            stale_failure = (source or {}).get("result", {}).get(
                "repair_state"
            ) == "ROLLED_BACK" and target_state != FailureRepairState.ROLLED_BACK
            if source is not None and target_state is not None and not stale_failure:
                repair = await repositories.locator_repairs.get_by_analysis(analysis_id)
                block_reason = (
                    (result or {}).get("block_reason")
                    or event.metadata.get("block_reason")
                    or event.metadata.get("reason")
                )
                repair_proposal = (result or {}).get("repair_proposal") or {}
                selection = (result or {}).get("selection") or {}
                candidate_id = (
                    repair_proposal.get("candidate_id")
                    or selection.get("candidate_id")
                    or (result or {}).get("candidate_id")
                )
                verification_run_id = (result or {}).get("verification_run_id") or event.metadata.get(
                    "verification_run_id"
                )
                if verification_run_id and await repositories.test_runs.get_by_id(verification_run_id) is None:
                    verification_run_id = None
                if repair is None:
                    repair = await self.repair_state_machine.create(
                        repositories.locator_repairs,
                        failure_id=source["failure_id"],
                        analysis_id=analysis_id,
                        initial_state=target_state,
                        block_reason=block_reason,
                        candidate_id=candidate_id,
                        verification_run_id=verification_run_id,
                    )
                else:
                    await self.repair_state_machine.move(
                        repositories.locator_repairs,
                        repair.id,
                        target_state,
                        block_reason=block_reason,
                        candidate_id=candidate_id,
                        verification_run_id=verification_run_id,
                    )
            await repositories.failure_analyses.append(analysis_id, event, result=result)
            await repositories.commit()

    async def _history_attach_verification(self, analysis_id: str, failure_id: str, run_id: str) -> None:
        async with self.repository_scope() as repositories:
            await repositories.failure_analyses.attach_verification(analysis_id, failure_id, run_id)
            await repositories.commit()

    async def _runtime_readiness(self) -> dict[str, Any]:
        """Require real AI and Jev capacity before an automatic repair can start."""
        config = get_config()
        if not config.repair.enabled or not config.features.ai_repair:
            return {"ready": False, "reason": "AI_REPAIR_DISABLED"}
        decision_settings = self.decisions.settings_service
        jev_config = await decision_settings.get_runtime_config()
        if config.repair.require_jev and not jev_config.enabled:
            return {"ready": False, "reason": "JEV_DISABLED", "jev_provider": "jev", "jev_model": jev_config.model}
        if config.repair.require_jev and not jev_config.api_key.strip():
            return {"ready": False, "reason": "JEV_KEY_MISSING", "jev_provider": "jev", "jev_model": jev_config.model}

        ai_settings = AISettingsService(self.repository_scope)
        ai_config = await ai_settings._effective_config()
        if not ai_config.enabled or ai_config.provider == "fake" or not ai_config.api_key.strip():
            return {
                "ready": False,
                "reason": "AI_RUNTIME_NOT_READY",
                "ai_provider": ai_config.provider,
                "ai_model": ai_config.model,
            }

        async with self.repository_scope() as repositories:
            budget = await repositories.ai_budgets.get_by_day(datetime.now(timezone.utc).date().isoformat())
        reserved = budget.reserved_requests if budget else 0
        required_calls = 4
        if ai_config.budget_enabled and ai_config.max_daily_requests - reserved < required_calls:
            return {
                "ready": False,
                "reason": "AI_BUDGET_EXHAUSTED",
                "required_calls": required_calls,
                "remaining_calls": max(0, ai_config.max_daily_requests - reserved),
            }

        ai_runtime = await ai_settings.get_status(refresh=True)
        if not ai_runtime.real_model_available:
            return {
                "ready": False,
                "reason": "AI_RUNTIME_NOT_READY",
                "ai_provider": ai_runtime.provider,
                "ai_model": ai_runtime.model,
                "ai_failure_reason": ai_runtime.failure_reason,
            }

        jev_runtime = None
        if config.repair.require_jev:
            jev_runtime = await self.decisions.decision_service.runtime_check()
            if jev_runtime.runtime != "READY":
                reason = "JEV_TIMEOUT" if "timeout" in jev_runtime.reasons else "JEV_RUNTIME_NOT_READY"
                if "budget_exceeded" in jev_runtime.reasons:
                    reason = "AI_BUDGET_EXHAUSTED"
                return {
                    "ready": False,
                    "reason": reason,
                    "jev_provider": jev_runtime.provider,
                    "jev_model": jev_runtime.model,
                    "jev_reasons": jev_runtime.reasons,
                }
        return {
            "ready": True,
            "ai_provider": ai_runtime.provider,
            "ai_model": ai_runtime.model,
            "jev_provider": jev_runtime.provider if jev_runtime else None,
            "jev_model": jev_runtime.model if jev_runtime else None,
            "jev_minimum_confidence": jev_runtime.minimum_confidence if jev_runtime else None,
        }

    async def start_verification(self, failure_id: str, analysis_id: str, *, monitor: bool = True) -> TestRun:
        """Create and attach the canonical exact-case repair verification run."""
        if self.run_service is None:
            raise RuntimeError("A run service is required to start repair verification")
        failure = await self.failures.get_failure_state(failure_id)
        original = await self.failures.run_repo.get_by_id(failure.run_id) if failure else None
        if failure is None or original is None:
            raise ValueError("Failure record not found")
        rows = await self._history_list(failure_id)
        analysis = next((item for item in rows if item["id"] == analysis_id), None)
        if analysis is None:
            raise ValueError("Analysis record not found for this failure")
        proposal = failure.repair_proposal or {}
        if not proposal.get("applied"):
            raise ValueError("Apply the verified repair before starting verification")
        existing_run_id = analysis["result"].get("verification_run_id")
        existing_run = await self.failures.run_repo.get_by_id(existing_run_id) if existing_run_id else None
        if existing_run and existing_run.status in {"QUEUED", "RUNNING"}:
            repair_record = await self._locator_repair_for_analysis(analysis_id)
            if repair_record and repair_record.state == FailureRepairState.PATCH_APPLIED:
                await self._record_transition(
                    failure,
                    analysis,
                    "VERIFYING_FIX",
                    "verification.started",
                    "Repair verification resumed",
                    verification_run_id=existing_run.id,
                )
            if monitor:
                self._schedule_verification_monitor(failure_id, analysis_id, existing_run.id)
            return existing_run
        state = await self.get_repair_workflow(failure_id, analysis_id)
        if "VERIFY" not in state.allowed_actions:
            raise ValueError(f"Repair state {state.state} does not allow verification")
        analyzed_proposal = analysis["result"].get("repair_proposal") or {}
        if analyzed_proposal.get("proposed_locator") != proposal.get("proposed_locator"):
            raise ValueError("Applied repair does not match the selected repair analysis")

        attempt = int(analysis["result"].get("verification_attempt", 0)) + 1
        run = await self.run_service.create_and_execute_run(
            TestRunCreate(
                idempotency_key=f"repair-verification:{analysis_id}:{attempt}",
                parent_run_id=original.id,
                origin_failure_id=failure.id,
                project_id=original.project_id,
                workspace_id=original.workspace_id,
                nodeids=_repair_verification_nodeids(failure.test_nodeid),
                markers=original.markers or [],
                environment=original.environment or {},
                browser=original.browser,
                parallel_workers=original.parallel_workers,
                runner_type=original.runner_type,
                runner_profile_id=original.runner_profile_id,
                requested_by=f"repair-verification:{failure.id}",
            )
        )
        await self.attach_verification(failure_id, analysis_id, run.id)
        await self._record_transition(
            failure,
            analysis,
            "VERIFYING_FIX",
            "verification.started",
            "Repair verification started",
            verification_run_id=run.id,
            verification_attempt=attempt,
        )
        if monitor:
            self._schedule_verification_monitor(failure_id, analysis_id, run.id)
        return run

    def _schedule_verification_monitor(self, failure_id: str, analysis_id: str, run_id: str) -> None:
        if run_id in self._monitored_verification_run_ids:
            return
        self._monitored_verification_run_ids.add(run_id)
        task = asyncio.create_task(self._monitor_verification(failure_id, analysis_id, run_id))
        self._verification_monitors.add(task)

        def clear_monitor(completed: asyncio.Task[None]) -> None:
            self._verification_monitors.discard(completed)
            self._monitored_verification_run_ids.discard(run_id)

        task.add_done_callback(clear_monitor)

    async def _monitor_verification(self, failure_id: str, analysis_id: str, run_id: str) -> None:
        """Reconcile asynchronous verification completion without using the request session."""
        from app.container import get_failure_service, get_failure_workflow_service
        from app.persistence.database import async_session_factory

        try:
            while True:
                async with async_session_factory() as session:
                    service = get_failure_service(session)
                    run = await service.run_repo.get_by_id(run_id)
                    if run is None:
                        return
                    status = getattr(run.status, "value", str(run.status))
                    if status in _TERMINAL_RUN_STATUSES:
                        workflow = get_failure_workflow_service(service, session)
                        history = await workflow.list_history(failure_id)
                        analysis = next((item for item in history if item["id"] == analysis_id), None)
                        result = (analysis or {}).get("result") or {}
                        verified = status == "PASSED" and result.get("verified") is True
                        proposal = result.get("repair_proposal") or {}
                        failure_state = await service.get_failure_state(failure_id)
                        if analysis is not None and proposal.get("applied") and failure_state is not None:
                            target_state = "VERIFIED" if verified else "FAILED"
                            await workflow._record_transition(
                                failure_state,
                                analysis,
                                target_state,
                                "verification.completed",
                                f"Exact-case verification {status}",
                                block_reason=None if verified else "VERIFICATION_FAILED",
                                verification_run_id=run_id,
                                verification_run_status=status,
                                verified=verified,
                            )
                            result = {
                                **result,
                                "repair_state": target_state,
                                "verification_run_status": status,
                                "verified": verified,
                            }
                            if not verified and get_config().repair.auto_rollback:
                                try:
                                    current = await workflow.get_repair_workflow(failure_id, analysis_id)
                                    if "ROLLBACK" in current.allowed_actions:
                                        await workflow.rollback_repair(failure_id, analysis_id, automatic=True)
                                        result = next(
                                            item["result"]
                                            for item in await workflow.list_history(failure_id)
                                            if item["id"] == analysis_id
                                        )
                                except Exception:
                                    logger.exception(
                                        "Automatic repair rollback failed after verification",
                                        extra={"failure_id": failure_id, "analysis_id": analysis_id, "run_id": run_id},
                                    )
                            if verified:
                                failure = await service.get_failure_state(failure_id)
                                proposal = (failure.repair_proposal or {}) if failure else {}
                                applied_at = proposal.get("applied_at")
                                if failure and proposal.get("proposed_locator") and applied_at:
                                    browser, page = await service._browser_evidence(failure.execution_id)
                                    url = (browser or {}).get("current_url") or (page or {}).get("url")
                                    if url:
                                        verified_run = await service.run_repo.get_by_id(run_id)
                                        if verified_run and verified_run.created_at >= datetime.fromisoformat(
                                            applied_at
                                        ):
                                            await LocatorHistoryService(workflow.repository_scope).record(
                                                url,
                                                proposal["proposed_locator"],
                                                True,
                                                verification=True,
                                                healed=True,
                                                healed_analysis_id=analysis_id,
                                            )
                        return
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Could not reconcile automatic repair verification",
                extra={"failure_id": failure_id, "analysis_id": analysis_id, "run_id": run_id},
            )

    async def start_retry(self, failure_id: str, analysis_id: str) -> TestRun:
        """Create the server-authorized exact-case retry for a diagnosed failure."""
        if self.run_service is None:
            raise RuntimeError("A run service is required to start a failure retry")
        workflow = await self.get_repair_workflow(failure_id, analysis_id)
        if workflow.retry_run_id:
            existing_run = await self.failures.run_repo.get_by_id(workflow.retry_run_id)
            if existing_run is not None:
                return existing_run
        if "RETRY" not in workflow.allowed_actions:
            raise ValueError(f"Repair state {workflow.state} does not allow retry")
        failure = await self.failures.get_failure_state(failure_id)
        original = await self.failures.run_repo.get_by_id(failure.run_id) if failure else None
        if failure is None or original is None:
            raise ValueError("Failure record not found")
        rows = await self._history_list(failure_id)
        analysis = next((item for item in rows if item["id"] == analysis_id), None)
        if analysis is None:
            raise ValueError("Analysis record not found for this failure")
        run = await self.run_service.create_and_execute_run(
            TestRunCreate(
                idempotency_key=f"failure-retry:{analysis_id}",
                parent_run_id=original.id,
                origin_failure_id=failure.id,
                project_id=original.project_id,
                workspace_id=original.workspace_id,
                nodeids=_repair_verification_nodeids(failure.test_nodeid),
                markers=original.markers or [],
                environment=original.environment or {},
                browser=original.browser,
                parallel_workers=original.parallel_workers,
                runner_type=original.runner_type,
                runner_profile_id=original.runner_profile_id,
                requested_by=f"failure-retry:{failure.id}",
            )
        )
        await self._record_transition(
            failure,
            analysis,
            workflow.state,
            "failure.retry_started",
            "Authorized exact-case retry started",
            retry_run_id=run.id,
            retry_run_status=run.status,
        )
        return run

    async def get_repair_workflow(self, failure_id: str, analysis_id: str | None = None) -> FailureRepairWorkflow:
        failure = await self.failures.get_failure_state(failure_id)
        if failure is None:
            raise ValueError("Failure record not found")
        rows = await self._history_list(failure_id)
        analysis = next((item for item in rows if item["id"] == analysis_id), None) if analysis_id else None
        if analysis_id and analysis is None:
            raise ValueError("Analysis record not found for this failure")
        if analysis is None and rows:
            analysis = rows[0]
        if analysis is None:
            state = "CREATED"
            result: dict[str, Any] = {}
        else:
            result = dict(analysis.get("result") or {})
            repair_record = await self._locator_repair_for_analysis(analysis["id"])
            state = (
                repair_record.state.value
                if repair_record is not None
                else str(result.get("repair_state") or ("ANALYZING" if analysis["status"] == "RUNNING" else "BLOCKED"))
            )
            if analysis["status"] in {"FAILED", "CANCELLED", "INTERRUPTED"} and state in {
                "ANALYZING",
                "DECIDING",
                "VERIFYING_CANDIDATE",
            }:
                state = "BLOCKED"
        if state not in FailureRepairState._value2member_map_:
            state = FailureRepairState.BLOCKED.value

        proposal = failure.repair_proposal or {}
        selected_proposal = (result.get("repair_proposal") or {}) if analysis else {}
        same_repair = bool(
            selected_proposal and selected_proposal.get("proposed_locator") == proposal.get("proposed_locator")
        )
        decision_summary = proposal.get("decision_summary") or {}
        trusted_selection = (
            proposal.get("provider") == "jev"
            and decision_summary.get("fallback_used") is False
            and decision_summary.get("verification_source") in {"playwright", "playwright_snapshot"}
            and isinstance(decision_summary.get("confidence"), (int, float))
            and decision_summary["confidence"] >= get_config().jev.minimum_confidence
        )
        verified_patch = bool(
            same_repair
            and proposal.get("verified") is True
            and trusted_selection
            and proposal.get("ai_provider") not in (None, "", "fake")
            and proposal.get("ai_fallback_used") is not True
            and proposal.get("candidate_id")
            and proposal.get("code_diff")
            and proposal.get("source_sha256")
        )
        if state == "PATCH_READY" and not verified_patch:
            state = "BLOCKED"
        elif state == "BLOCKED" and verified_patch and analysis and analysis["status"] == "COMPLETED":
            state = "PATCH_READY"
        if same_repair and proposal.get("rollback_status") == "ROLLED_BACK":
            state = "ROLLED_BACK"
        elif same_repair and proposal.get("applied"):
            state = "PATCH_APPLIED"

        run_id = result.get("verification_run_id")
        run = await self.failures.run_repo.get_by_id(run_id) if run_id else None
        verified = False
        if run is not None and state != "ROLLED_BACK":
            if run.status in {"QUEUED", "RUNNING"}:
                if same_repair and proposal.get("applied"):
                    state = "VERIFYING_FIX"
            elif run.status in {"PASSED", "FAILED", "ERROR", "CANCELLED"}:
                executions = await self.failures.run_repo.list_executions(run.id)
                execution = next((item for item in executions if item.nodeid == failure.test_nodeid), None)
                verified = (
                    same_repair
                    and proposal.get("applied") is True
                    and run.status == "PASSED"
                    and execution is not None
                    and execution.status == "PASSED"
                )
                if same_repair and proposal.get("applied"):
                    state = "VERIFIED" if verified else "FAILED"

        allowed_actions = self.repair_state_machine.allowed_actions(state)
        if state in {"FAILED", "VERIFIED", "PATCH_APPLIED"} and not (same_repair and proposal.get("applied")):
            allowed_actions = tuple(action for action in allowed_actions if action == "START_ANALYSIS")
        if state == "FAILED" and proposal.get("applied"):
            allowed_actions = tuple(action for action in allowed_actions if action != "START_ANALYSIS")
        diagnosis = result.get("diagnosis") or {}
        diagnosis_provider = str(diagnosis.get("provider") or "").lower()
        trusted_diagnosis = bool(
            diagnosis_provider and diagnosis_provider != "fake" and diagnosis.get("fallback_used") is not True
        )
        classification = str(diagnosis.get("classification") or "UNKNOWN").upper()
        if analysis is not None and state == "NOT_APPLICABLE" and trusted_diagnosis:
            if classification in RETRYABLE_CLASSIFICATIONS and not result.get("retry_run_id"):
                allowed_actions = (*allowed_actions, "RETRY")
            if classification in ISSUE_CLASSIFICATIONS:
                allowed_actions = (*allowed_actions, "CREATE_ISSUE_DRAFT")
        retry_run_id = result.get("retry_run_id")
        retry_run = await self.failures.run_repo.get_by_id(retry_run_id) if retry_run_id else None
        failure_snapshot, _ = await self.failures.get_failure_snapshot(failure.execution_id)
        return FailureRepairWorkflow(
            repair_id=repair_record.id if analysis and repair_record else None,
            failure_id=failure_id,
            analysis_id=analysis["id"] if analysis else None,
            state=state,
            allowed_actions=list(allowed_actions),
            verification_run_id=run.id if run else None,
            verification_run_status=run.status if run else None,
            retry_run_id=retry_run.id if retry_run else None,
            retry_run_status=retry_run.status if retry_run else None,
            verified=verified,
            failure_snapshot=failure_snapshot,
            repair_proposal={**selected_proposal, **proposal} if selected_proposal else None,
        )

    async def apply_repair(
        self, failure_id: str, analysis_id: str, payload, *, expected_workspace_id: str | None = None
    ) -> dict[str, Any]:
        state = await self.get_repair_workflow(failure_id, analysis_id)
        if "APPLY" not in state.allowed_actions:
            raise ValueError(f"Repair state {state.state} does not allow applying a patch")
        failure = await self.failures.get_failure_state(failure_id)
        analysis = next((row for row in await self._history_list(failure_id) if row["id"] == analysis_id), None)
        if failure is None or analysis is None:
            raise ValueError("Failure or analysis record not found")
        proposal = analysis["result"].get("repair_proposal") or {}
        if proposal.get("proposed_locator") != payload.new_code:
            raise ValueError("Patch does not match the selected analysis")
        original = await self.failures.run_repo.get_by_id(failure.run_id)
        if original is None or original.workspace_id is None:
            raise ValueError("Failure workspace is unavailable")
        if expected_workspace_id is not None and expected_workspace_id != original.workspace_id:
            raise ValueError("Repair workspace does not match the original failure run")
        await self._record_transition(
            failure,
            analysis,
            "APPLYING",
            "patch.applying",
            "Repair patch application started",
            candidate_id=proposal.get("candidate_id"),
        )
        try:
            result = await self.failures.apply_repair(original.workspace_id, payload, failure_id=failure_id)
        except Exception as error:
            await self._record_transition(
                failure,
                analysis,
                "PATCH_READY",
                "patch.apply_failed",
                "Repair patch application was rejected",
                block_reason="PATCH_APPLY_FAILED",
                error_type=type(error).__name__,
            )
            raise
        await self.failures.transaction.commit()
        updated_failure = await self.failures.get_failure_state(failure_id)
        applied_proposal = (
            updated_failure.repair_proposal
            if updated_failure and updated_failure.repair_proposal
            else {**proposal, "applied": True}
        )
        await self._record_transition(
            failure,
            analysis,
            "PATCH_APPLIED",
            "patch.applied",
            "Repair patch applied to the workspace",
            file_path=result["file_path"],
            changes_applied=True,
            repair_proposal=applied_proposal,
        )
        workflow = await self.get_repair_workflow(failure_id, analysis_id)
        return {**result, "repair": workflow.model_dump(mode="json")}

    async def rollback_repair(
        self,
        failure_id: str,
        analysis_id: str,
        *,
        expected_workspace_id: str | None = None,
        automatic: bool = False,
    ) -> dict[str, Any]:
        if automatic and not get_config().repair.auto_rollback:
            raise ValueError("Automatic rollback is disabled by the effective AppConfig")
        state = await self.get_repair_workflow(failure_id, analysis_id)
        if "ROLLBACK" not in state.allowed_actions:
            raise ValueError(f"Repair state {state.state} does not allow rollback")
        failure = await self.failures.get_failure_state(failure_id)
        analysis = next((row for row in await self._history_list(failure_id) if row["id"] == analysis_id), None)
        if failure is None or analysis is None:
            raise ValueError("Failure or analysis record not found")
        original = await self.failures.run_repo.get_by_id(failure.run_id)
        if original is None or original.workspace_id is None:
            raise ValueError("Failure workspace is unavailable")
        if expected_workspace_id is not None and expected_workspace_id != original.workspace_id:
            raise ValueError("Rollback workspace does not match the original failure run")
        result = await self.failures.rollback_repair(failure_id, original.workspace_id)
        await self.failures.transaction.commit()
        updated_failure = await self.failures.get_failure_state(failure_id)
        rolled_back_proposal = (
            updated_failure.repair_proposal
            if updated_failure and updated_failure.repair_proposal
            else {**(analysis.get("result") or {}).get("repair_proposal", {}), "applied": False}
        )
        transition_metadata = {
            "changes_applied": False,
            "repair_proposal": rolled_back_proposal,
        }
        if automatic:
            transition_metadata.update(automatic=True, auto_rolled_back=True)
        await self._record_transition(
            failure,
            analysis,
            "ROLLED_BACK",
            "repair.rolled_back",
            "Repair patch rolled back",
            file_path=result["file_path"],
            **transition_metadata,
        )
        workflow = await self.get_repair_workflow(failure_id, analysis_id)
        return {**result, "repair": workflow.model_dump(mode="json")}

    async def _record_transition(
        self,
        failure,
        analysis: dict[str, Any],
        state: str,
        event_type: str,
        message: str,
        **metadata: Any,
    ) -> None:
        result = {**(analysis.get("result") or {}), **metadata, "repair_state": state}
        event = make_trace_event(
            failure.run_id,
            event_type,
            stage="repair",
            step_id=f"{analysis['id']}:repair:{state.lower()}",
            title=event_type,
            message=message,
            status="COMPLETED",
            metadata={"analysis_id": analysis["id"], "failure_id": failure.id, "state": state, **metadata},
        )
        await self._history_append(analysis["id"], event, result=result)

    async def attach_verification(self, failure_id: str, analysis_id: str, run_id: str) -> None:
        failure = await self.failures.get_failure_state(failure_id)
        run = await self.failures.run_repo.get_by_id(run_id)
        original = await self.failures.run_repo.get_by_id(failure.run_id) if failure else None
        if not failure or not run or not original or run.id == original.id:
            raise ValueError("Verification requires a new run for this failure")
        if run.workspace_id != original.workspace_id or run.project_id != original.project_id:
            raise ValueError("Verification run belongs to a different workspace or project")
        if run.nodeids != [failure.test_nodeid]:
            raise ValueError("Verification run must execute exactly the failed test case")
        analyses = await self._history_list(failure_id)
        analysis = next((item for item in analyses if item["id"] == analysis_id), None)
        if analysis is None or run.created_at.isoformat() < analysis["created_at"]:
            raise ValueError("Verification run must be created after the selected analysis")
        await self._history_attach_verification(analysis_id, failure_id, run_id)

    async def list_history(self, failure_id: str) -> list[dict[str, Any]]:
        """Read persisted analysis history and project verification status without writes."""
        rows = await self._history_list(failure_id)
        failure = await self.failures.get_failure_state(failure_id)
        if failure is None:
            return rows
        for row in rows:
            result = dict(row.get("result") or {})
            run_id = result.get("verification_run_id")
            if not run_id:
                continue
            run = await self.failures.run_repo.get_by_id(run_id)
            if run is None:
                continue
            completed = run.status in {"PASSED", "FAILED", "ERROR", "CANCELLED"}
            if result.get("verification_run_status") == run.status:
                continue
            execution = None
            if completed:
                executions = await self.failures.run_repo.list_executions(run.id)
                execution = next((item for item in executions if item.nodeid == failure.test_nodeid), None)
            verified = run.status == "PASSED" and execution is not None and execution.status == "PASSED"
            proposal = failure.repair_proposal or {}
            analysis_proposal = result.get("repair_proposal") or {}
            applied_to_analysis = bool(
                proposal.get("applied")
                and proposal.get("proposed_locator") == analysis_proposal.get("proposed_locator")
            )
            if applied_to_analysis:
                result["repair_state"] = "VERIFIED" if verified else "FAILED" if completed else "VERIFYING_FIX"
            result.update(verified=verified, verification_run_status=run.status)
            event_type = "verification.completed" if completed else "verification.started"
            projected_event = make_trace_event(
                failure.run_id,
                event_type,
                stage="verification",
                step_id=f"{row['id']}:verification",
                title="验证修复结果",
                status="COMPLETED" if verified else "FAILED" if completed else "RUNNING",
                message=(f"实际复测 {run.id} · {run.status}" if completed else f"复测 {run.id} 已提交，等待执行结果"),
                metadata={
                    "analysis_id": row["id"],
                    "verification_run_id": run.id,
                    "test_nodeid": failure.test_nodeid,
                    "test_rerun": True,
                    "verified": verified,
                    "evidence_source": "pytest_execution",
                },
                duration_ms=run.duration_ms if completed else None,
            )
            projected_events = list(row.get("events") or [])
            if not any(
                event.get("type") == event_type
                and event.get("step_id") == projected_event.step_id
                and (event.get("metadata") or {}).get("verification_run_id") == run.id
                for event in projected_events
            ):
                projected_events.append(projected_event.model_dump(mode="json"))
            if completed and applied_to_analysis:
                repair_event = make_trace_event(
                    failure.run_id,
                    "repair.verified" if verified else "repair.failed",
                    stage="repair",
                    step_id=f"{row['id']}:repair:{result['repair_state'].lower()}",
                    title="Repair verified" if verified else "Repair verification failed",
                    message=f"Exact-case verification {run.status}",
                    metadata={
                        "analysis_id": row["id"],
                        "verification_run_id": run.id,
                        "state": result["repair_state"],
                    },
                )
                if not any(
                    event.get("type") == repair_event.type
                    and event.get("step_id") == repair_event.step_id
                    and (event.get("metadata") or {}).get("verification_run_id") == run.id
                    for event in projected_events
                ):
                    projected_events.append(repair_event.model_dump(mode="json"))
            row["events"] = projected_events
            row["result"] = result
        return rows

    async def stream(
        self,
        failure_id: str,
        *,
        response_language: str = "en",
        analysis_id: str | None = None,
        start_new_analysis: bool | None = None,
        auto_triggered: bool = False,
    ) -> AsyncGenerator[AITraceEvent, None]:
        failure = await self.failures.get_failure_state(failure_id)
        if failure is None:
            raise ValueError("Failure record not found")
        if analysis_id is None:
            analysis_id, start_new_analysis = await self.start_analysis(failure_id)
        if start_new_analysis is False:
            history = next(
                (row for row in await self._history_list(failure_id) if row["id"] == analysis_id),
                None,
            )
            if history:
                for event in history["events"]:
                    yield AITraceEvent.model_validate(event)
            return
        if start_new_analysis is None:
            raise ValueError("Analysis claim state is required")
        repair = await self._ensure_locator_repair(failure_id, analysis_id)
        if repair.state == FailureRepairState.CREATED:
            async with self.repository_scope() as repositories:
                await self.repair_state_machine.move(
                    repositories.locator_repairs,
                    repair.id,
                    FailureRepairState.ANALYZING,
                )
                await repositories.commit()
        queue: asyncio.Queue[AITraceEvent | None] = asyncio.Queue()
        active_stage = "context"
        stage_started: dict[str, float] = {}

        async def publish(event: AITraceEvent, result: dict[str, Any] | None = None):
            event.metadata = {**event.metadata, "analysis_id": analysis_id}
            event = AITraceEvent.model_validate(SensitiveRedactor.redact_value(event.model_dump(mode="json")))
            await self._history_append(analysis_id, event, result=result)
            await queue.put(event)

        async def step(
            key: str, status: str, message: str, *, _persisted_result: dict[str, Any] | None = None, **metadata
        ):
            nonlocal active_stage
            duration = None
            if status == "RUNNING":
                active_stage = key
                stage_started[key] = time.perf_counter()
            elif key in stage_started:
                duration = round((time.perf_counter() - stage_started[key]) * 1000, 1)
            await publish(
                make_trace_event(
                    failure.run_id,
                    "workflow.step",
                    stage=key,
                    step_id=f"{analysis_id}:{key}",
                    title=key,
                    status=status,
                    message=SensitiveRedactor.redact_text(message),
                    metadata=metadata,
                    duration_ms=duration,
                    case_execution_id=failure.execution_id,
                ),
                result=_persisted_result,
            )

        async def analyze():
            try:
                category, explanation, locator = FailureClassifier.classify(failure.error_message, failure.stack_trace)
                initial_classification = category
                evidence_execution_id = failure.execution_id
                browser, page_evidence = await self.failures._browser_evidence(evidence_execution_id)
                error_text = f"{failure.exception_type}\n{failure.error_message}\n{failure.stack_trace}"
                domain = (
                    "UI"
                    if browser or category == FailureCategory.LOCATOR_CHANGED or "playwright" in error_text.lower()
                    else (
                        "API"
                        if re.search(
                            r"httpx|requests\.|HTTPError|HTTPStatusError|status_code|HTTP/\d|\b[45]\d\d\s+(?:Client|Server|Bad|Not|Internal)",
                            error_text,
                            re.I,
                        )
                        else "PYTHON"
                    )
                )
                steps = ["context", "logs", "inspection", "diagnosis", "decision", "suggestion", "verification"]
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "workflow.plan",
                        stage="workflow",
                        title="失败分析流程",
                        status="RUNNING",
                        metadata={
                            "domain": domain,
                            "steps": steps,
                            "failure_id": failure_id,
                            "classification": category.value,
                        },
                    )
                )
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "repair.started",
                        stage="repair",
                        step_id=f"{analysis_id}:repair-started",
                        title="Repair analysis started",
                        message="Failure repair workflow started",
                        metadata={
                            "analysis_id": analysis_id,
                            "failure_id": failure_id,
                            "state": "ANALYZING",
                            "mode": self.auto_repair_mode,
                            "require_ai": get_config().features.ai_repair,
                            "require_jev": (
                                get_config().repair.require_jev
                                or not get_config().jev.failure_policy.allow_local_fallback
                            ),
                            "auto_rollback": get_config().repair.auto_rollback,
                            "minimum_jev_confidence": get_config().jev.minimum_confidence,
                        },
                    )
                )
                await step("context", "RUNNING", "正在读取测试与运行上下文")
                run = await self.failures.run_repo.get_by_id(failure.run_id)
                environment = SensitiveRedactor.redact_value(run.environment or {}) if run else {}
                if not isinstance(environment, dict):
                    environment = {}
                region = str(environment.get("QA_REGION") or environment.get("REGION") or "未记录区域")
                file_path = failure.test_nodeid.split("::")[0]
                source = ""
                source_error = ""
                if run and run.workspace_id:
                    try:
                        source = await self.failures.workspace_service.read_file(run.workspace_id, file_path)
                    except (ValueError, OSError, SecurityException) as error:
                        source_error = type(error).__name__
                source_hash = hashlib.sha256(source.encode()).hexdigest() if source else None
                await step(
                    "context",
                    "COMPLETED",
                    f"{failure.test_nodeid} · {region}",
                    nodeid=failure.test_nodeid,
                    environment=environment,
                    source_path=file_path,
                    source_sha256=source_hash,
                    source_available=bool(source),
                    source_error=source_error,
                )
                await step("logs", "RUNNING", "正在读取失败日志与异常堆栈")
                await step(
                    "logs",
                    "COMPLETED",
                    f"{failure.exception_type or category.value} · {failure.error_message[:250]}",
                    classification=category.value,
                    rule_explanation=explanation,
                    error_excerpt=failure.error_message[:1500],
                    traceback_excerpt=failure.stack_trace[-3500:],
                )
                await step("inspection", "RUNNING", "正在检查已捕获的失败证据")
                candidates = []
                eligible_candidates = []
                event = {}
                if domain == "UI":
                    raw_candidates = self.failures._observed_locator_candidates(page_evidence)
                    failed_locator = locator or failure.failing_locator or ""
                    event = {
                        "candidates": raw_candidates,
                        "failed_locator": failed_locator,
                        "url": (browser or {}).get("current_url", ""),
                        "action": "click",
                        "context": {"failed_locator": failed_locator, "error_excerpt": failure.error_message[:500]},
                    }
                    candidates = self.decisions.generate_candidates(event)
                    eligible_candidates = self.decisions.prioritize_candidates_for_failure(failed_locator, candidates)
                    await step(
                        "inspection",
                        "COMPLETED" if page_evidence else "BLOCKED",
                        f"失败页面快照中找到 {len(candidates)} 个候选 Locator"
                        if page_evidence
                        else "没有捕获页面元素证据，不能推断候选 Locator",
                        candidate_count=len(candidates),
                        eligible_candidate_count=len(eligible_candidates),
                        candidates=candidates,
                        evidence_source="failure_page_snapshot",
                    )
                else:
                    http_evidence = re.findall(
                        r"(?:status_code\s*[=:]\s*\d{3}|HTTP[/\w.]*\s+\d{3}|HTTPStatusError[^\n]*)", error_text, re.I
                    )
                    excerpt = SensitiveRedactor.redact_text("\n".join(source.splitlines()[:80]))[:5500]
                    await step(
                        "inspection",
                        "COMPLETED" if source or http_evidence else "BLOCKED",
                        (
                            "已检查已捕获的请求/响应日志与测试源码"
                            if domain == "API"
                            else "已检查 Python 异常堆栈与测试源码"
                        )
                        if source or http_evidence
                        else "仅有异常日志，未取得测试源码或请求/响应证据",
                        source_excerpt=excerpt,
                        http_evidence=http_evidence[:10],
                        source_path=file_path,
                        has_traceback=bool(failure.stack_trace),
                        source_available=bool(source),
                    )
                if auto_triggered:
                    if self.auto_repair_mode == "OFF":
                        readiness = {"ready": False, "reason": "AUTO_REPAIR_MODE_OFF"}
                    else:
                        await step("runtime", "RUNNING", "正在检查真实 AI 与 Jev 自动修复运行时")
                        readiness = await self._runtime_readiness()
                    if not readiness.get("ready"):
                        reason = str(readiness.get("reason") or "AUTO_REPAIR_RUNTIME_NOT_READY")
                        await step(
                            "runtime",
                            "BLOCKED",
                            f"自动修复已阻止：{reason}",
                            reason=reason,
                            auto_repair_mode=self.auto_repair_mode,
                            **{key: value for key, value in readiness.items() if key not in {"ready", "reason"}},
                        )
                        blocked_result = {
                            "repair_state": "BLOCKED",
                            "block_reason": reason,
                            "auto_repair_mode": self.auto_repair_mode,
                            "automatic_triggered": True,
                            "verified": False,
                            "changes_applied": False,
                            **{key: value for key, value in readiness.items() if key != "ready"},
                        }
                        await publish(
                            make_trace_event(
                                failure.run_id,
                                "repair.blocked",
                                stage="repair",
                                step_id=f"{analysis_id}:runtime-blocked",
                                title="Auto repair blocked",
                                status="FAILED",
                                message=reason,
                                metadata=blocked_result,
                            ),
                            result=blocked_result,
                        )
                        await publish(
                            make_trace_event(
                                failure.run_id,
                                "run.completed",
                                stage="workflow",
                                title="自动修复未启动",
                                status="COMPLETED",
                                message=reason,
                                metadata={"analysis_id": analysis_id, **blocked_result},
                            ),
                            result=blocked_result,
                        )
                        return
                    await step("runtime", "COMPLETED", "真实 AI 与 Jev 运行时可用", **readiness)
                await step("diagnosis", "RUNNING", "AI 正在基于当前证据分析根因")
                diagnosis = await self.failures.diagnose_failure_ai(
                    failure_id,
                    on_event=publish,
                    response_language=response_language,
                    extra_context=json.dumps(
                        {
                            "domain": domain,
                            "region": region,
                            "source_path": file_path,
                            "source_available": bool(source),
                        },
                        ensure_ascii=False,
                    ),
                )
                await step(
                    "diagnosis",
                    "COMPLETED",
                    diagnosis.root_cause[:600],
                    provider=diagnosis.provider,
                    fallback_used=diagnosis.fallback_used,
                    confidence=None if diagnosis.provider == "fake" else diagnosis.confidence,
                    classification=diagnosis.classification,
                )
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "diagnosis.completed",
                        stage="diagnosis",
                        step_id=f"{analysis_id}:diagnosis",
                        title="Diagnosis completed",
                        message=diagnosis.root_cause[:500],
                        metadata={"provider": diagnosis.provider, "fallback_used": diagnosis.fallback_used},
                    )
                )
                resolved_classification = initial_classification
                classification_source = "RULE"
                if diagnosis.provider != "fake" and not diagnosis.fallback_used:
                    try:
                        diagnosed_category = FailureCategory(diagnosis.classification)
                    except ValueError:
                        diagnosed_category = FailureCategory.UNKNOWN
                    if diagnosed_category != FailureCategory.UNKNOWN:
                        resolved_classification = diagnosed_category
                        if diagnosed_category != initial_classification:
                            classification_source = "AI_DIAGNOSIS"
                selection = None
                repair_proposal = None
                repair_state = (
                    "BLOCKED" if resolved_classification == FailureCategory.LOCATOR_CHANGED else "NOT_APPLICABLE"
                )
                if (
                    domain == "UI"
                    and resolved_classification == FailureCategory.LOCATOR_CHANGED
                    and eligible_candidates
                ):
                    await step("decision", "RUNNING", "正在选择证据支持的候选 Locator")
                    proposal_error = None
                    try:
                        repair_proposal = await self.failures.generate_repair_proposal(
                            failure_id,
                            diagnosis_override=diagnosis,
                            resolved_classification=resolved_classification.value,
                            decision_service=self.decisions,
                            evidence_execution_id=evidence_execution_id,
                        )
                        await self.failures.transaction.commit()
                    except (ValueError, OSError) as error:
                        repair_proposal = None
                        error_summary = SensitiveRedactor.redact_text(str(error))
                        proposal_error = (error_summary.splitlines()[0] if error_summary else type(error).__name__)[
                            :300
                        ]
                        if isinstance(error, LocatorRepairNotApplicableError):
                            selection = error.decision_summary or None
                            for item in error.execution_trace:
                                if item.stage in {"decision", "verification", "repair"}:
                                    await publish(item)
                    if repair_proposal:
                        for item in repair_proposal.execution_trace:
                            if item.stage in {"decision", "verification", "repair"}:
                                await publish(item)
                        selection = repair_proposal.decision_summary or {
                            "engine": repair_proposal.provider,
                            "provider": repair_proposal.provider,
                            "model": repair_proposal.model,
                            "candidate_id": repair_proposal.candidate_id,
                            "selected_locator": repair_proposal.proposed_locator,
                            "confidence": repair_proposal.confidence,
                            "latency_ms": repair_proposal.latency_ms,
                            "verified": repair_proposal.verified,
                            "fallback_reason": repair_proposal.verification_reason,
                        }
                        decision_summary = repair_proposal.decision_summary
                        trusted_selection = (
                            repair_proposal.provider == "jev"
                            and decision_summary.get("fallback_used") is False
                            and decision_summary.get("verification_source") in {"playwright", "playwright_snapshot"}
                            and repair_proposal.confidence is not None
                            and repair_proposal.confidence >= get_config().jev.minimum_confidence
                        )
                        ready = (
                            repair_proposal.verified
                            and trusted_selection
                            and repair_proposal.ai_provider not in (None, "", "fake")
                            and not repair_proposal.ai_fallback_used
                            and bool(repair_proposal.code_diff)
                        )
                        repair_state = "PATCH_READY" if ready else "BLOCKED"
                        await step(
                            "decision",
                            "COMPLETED" if trusted_selection else "BLOCKED",
                            f"{repair_proposal.provider} · {repair_proposal.proposed_locator}",
                            **selection,
                            initial_classification=initial_classification.value,
                            resolved_classification=resolved_classification.value,
                            classification_source=classification_source,
                        )
                        await step(
                            "repair",
                            "COMPLETED" if ready else "BLOCKED",
                            "补丁已生成并通过候选验证，等待 Apply & Verify"
                            if ready
                            else "候选未通过可信选择和浏览器证据验证；补丁不可应用",
                            repair_state=repair_state,
                            candidate_verified=repair_proposal.verified,
                            changes_applied=False,
                            patch_ready=ready,
                            provider=repair_proposal.provider,
                            fallback_reason=repair_proposal.verification_reason,
                            file_path=repair_proposal.file_path,
                            code_diff=repair_proposal.code_diff,
                        )
                    else:
                        await step(
                            "decision",
                            "BLOCKED",
                            "未生成可应用补丁；检查 Jev、页面验证和候选证据",
                            reason=proposal_error,
                            initial_classification=initial_classification.value,
                            resolved_classification=resolved_classification.value,
                            classification_source=classification_source,
                        )
                        await step("repair", "BLOCKED", "没有受 Playwright 验证的 Locator 补丁")
                elif resolved_classification != FailureCategory.LOCATOR_CHANGED:
                    await step(
                        "decision",
                        "SKIPPED",
                        "当前解析后的错误分类不适用 Locator 决策",
                        initial_classification=initial_classification.value,
                        resolved_classification=resolved_classification.value,
                        classification_source=classification_source,
                    )
                else:
                    await step(
                        "decision",
                        "BLOCKED",
                        "没有与失效目标关联的候选证据，未调用 Jev",
                        initial_classification=initial_classification.value,
                        resolved_classification=resolved_classification.value,
                        classification_source=classification_source,
                    )
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "decision.completed",
                        stage="decision",
                        step_id=f"{analysis_id}:decision",
                        title="Repair decision completed",
                        message=str((selection or {}).get("selected_locator") or "No repair candidate selected"),
                        metadata={"analysis_id": analysis_id, "selection": selection, "repair_state": repair_state},
                    )
                )
                if repair_proposal:
                    await publish(
                        make_trace_event(
                            failure.run_id,
                            "candidate.verified",
                            stage="candidate_verification",
                            step_id=f"{analysis_id}:candidate-verification",
                            title="Candidate verification completed",
                            message="Candidate locator verified"
                            if repair_proposal.verified
                            else "Candidate locator not verified",
                            status="COMPLETED" if repair_proposal.verified else "FAILED",
                            metadata={
                                "candidate_id": repair_proposal.candidate_id,
                                "verified": repair_proposal.verified,
                                "provider": repair_proposal.provider,
                            },
                        )
                    )
                if repair_state == "PATCH_READY" and repair_proposal:
                    await publish(
                        make_trace_event(
                            failure.run_id,
                            "patch.generated",
                            stage="repair",
                            step_id=f"{analysis_id}:patch-generated",
                            title="Patch generated",
                            message="Verified patch is ready to apply",
                            metadata={
                                "file_path": repair_proposal.file_path,
                                "candidate_id": repair_proposal.candidate_id,
                            },
                        )
                    )
                elif repair_state == "BLOCKED":
                    await publish(
                        make_trace_event(
                            failure.run_id,
                            "repair.failed",
                            stage="repair",
                            step_id=f"{analysis_id}:repair-failed",
                            title="Repair blocked",
                            status="FAILED",
                            message="Repair did not produce a candidate that passed all required checks",
                            metadata={
                                "repair_state": "BLOCKED",
                                "initial_classification": initial_classification.value,
                                "resolved_classification": resolved_classification.value,
                            },
                        )
                    )
                await step("suggestion", "RUNNING", "正在整理修复建议和验证条件")
                result = {
                    "domain": domain,
                    "diagnosis": diagnosis.model_dump(mode="json", exclude={"execution_trace"}),
                    "selection": selection,
                    "repair_proposal": repair_proposal.model_dump(mode="json") if repair_proposal else None,
                    "repair_state": repair_state,
                    "initial_classification": initial_classification.value,
                    "resolved_classification": resolved_classification.value,
                    "classification_source": classification_source,
                    "verified": False,
                    "changes_applied": False,
                    "auto_repair_mode": self.auto_repair_mode,
                    "automatic_triggered": auto_triggered,
                }

                if repair_state == "PATCH_READY" and repair_proposal:
                    await step(
                        "suggestion",
                        "COMPLETED",
                        "安全补丁已就绪，等待人工审核并 Apply & Verify",
                        candidate_verified=True,
                        changes_applied=False,
                        patch_ready=True,
                        auto_repair_mode=self.auto_repair_mode,
                    )
                else:
                    await step(
                        "suggestion",
                        "COMPLETED" if diagnosis.recommended_actions or repair_proposal else "BLOCKED",
                        "；".join(diagnosis.recommended_actions[:4])
                        or (repair_proposal.proposed_locator if repair_proposal else "证据不足，未生成修复建议"),
                        recommended_actions=diagnosis.recommended_actions,
                        hypotheses=diagnosis.hypotheses,
                        candidate_verified=bool(repair_proposal and repair_proposal.verified),
                        changes_applied=False,
                    )

                await step(
                    "verification",
                    "PENDING" if repair_state in {"PATCH_READY", "NOT_APPLICABLE"} else "BLOCKED",
                    "安全补丁已就绪，等待人工审核、应用与复测"
                    if repair_state == "PATCH_READY"
                    else "当前分类不适用定位器修复，复测仍可单独执行"
                    if repair_state == "NOT_APPLICABLE"
                    else "候选未通过可信选择或失败页面证据验证，不能应用或标记成功",
                    test_rerun=False,
                    candidate_verified=bool(repair_proposal and repair_proposal.verified),
                    changes_applied=False,
                    repair_state=repair_state,
                    verification_source=(
                        repair_proposal.decision_summary.get("verification_source") if repair_proposal else None
                    ),
                )

                result["repair_state"] = repair_state
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "run.completed",
                        stage="workflow",
                        title=(
                            "候选已验证，等待人工审核与应用"
                            if repair_state == "PATCH_READY"
                            else "分析完成，未进入定位器修复"
                            if repair_state == "NOT_APPLICABLE"
                            else "分析完成，修复未通过验证"
                        ),
                        metadata={"analysis_id": analysis_id, **result},
                    ),
                    result=result,
                )
            except asyncio.CancelledError:
                cancelled_result = {
                    "repair_state": "BLOCKED",
                    "block_reason": "ANALYSIS_CANCELLED",
                    "verified": False,
                    "changes_applied": False,
                }
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "run.cancelled",
                        stage=active_stage,
                        title="分析已取消",
                        status="CANCELLED",
                        message="用户中止了分析，未执行修复或复测",
                        metadata=cancelled_result,
                    ),
                    result=cancelled_result,
                )
                raise
            except Exception as error:
                await step(active_stage, "FAILED", str(error)[:500])
                failed_result = dict(result) if isinstance(locals().get("result"), dict) else {}
                current_state = str(failed_result.get("repair_state") or "ANALYZING")
                target_state = "FAILED" if failed_result.get("changes_applied") else "BLOCKED"
                try:
                    self.repair_state_machine.transition(current_state, target_state)
                except (ValueError, KeyError):
                    target_state = current_state
                failed_result["repair_state"] = target_state
                block_reason = None
                if target_state in {"BLOCKED", "FAILED"}:
                    block_reason = failed_result.pop("block_reason", None) or "WORKFLOW_ERROR"
                failed_result.setdefault("verified", False)
                failed_result.setdefault("changes_applied", False)
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "repair.failed",
                        stage="repair",
                        step_id=f"{analysis_id}:repair-failed",
                        title="Repair workflow failed",
                        status="FAILED",
                        message=SensitiveRedactor.redact_text(str(error))[:500],
                        metadata={
                            "repair_state": target_state,
                            "block_reason": block_reason,
                            "error_type": type(error).__name__,
                        },
                    ),
                    result=failed_result,
                )
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "run.failed",
                        stage=active_stage,
                        title="分析失败",
                        status="FAILED",
                        message=SensitiveRedactor.redact_text(str(error))[:500],
                    ),
                    result=failed_result,
                )
            finally:
                await queue.put(None)

        locator_repair_token = bind_locator_repair(repair.id)
        try:
            task = asyncio.create_task(analyze(), name=f"failure-workflow-{analysis_id}")
        finally:
            reset_locator_repair(locator_repair_token)
        try:
            while (event := await queue.get()) is not None:
                yield event
        finally:
            if not task.done():
                _ = task.cancel()
            _ = await asyncio.gather(task, return_exceptions=True)
