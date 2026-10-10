from __future__ import annotations

import ast
import asyncio
import difflib
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from fnmatch import fnmatchcase

from project_model.models import (
    ApplyRepairRequest,
    FailureRecord,
    FailureRecurrenceItem,
)
from qa_core.ai.models import FailureAnalysisResponse, LocatorSemanticReview
from qa_core.ai.trace import AITraceEvent, make_trace_event
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.models import FailureCategory
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.healing.models import LocatorRepairProposal
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.persistence.models import utc_now
from app.ports.browser_runtime import BrowserRuntime
from app.ports.repository_scope import RepositoryScopeFactory
from app.ports.transaction_boundary import TransactionBoundary
from app.repositories.ai_repo import AIRepository
from app.repositories.failure_repo import FailureRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.ai_observability import log_ai_execution
from app.services.ai_runtime import build_ai_orchestrator
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.locator_decision_service import LocatorDecisionService
from app.services.workspace_service import WorkspaceService
from app.settings import get_config

logger = logging.getLogger("app.ai")


def _is_allowed_repair_target(path: str) -> bool:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized or ".." in normalized.split("/") or normalized.startswith("/"):
        return False
    repair = get_config().repair
    if any(fnmatchcase(normalized, pattern.replace("\\", "/")) for pattern in repair.denied_paths):
        return False
    return any(fnmatchcase(normalized, pattern.replace("\\", "/")) for pattern in repair.allowed_paths)


def _validated_trace_events(events: list[AITraceEvent | dict[str, object]]) -> list[AITraceEvent]:
    return [AITraceEvent.model_validate(event) for event in events]


class LocatorRepairNotApplicableError(ValueError):
    """Failure evidence does not support a locator repair."""

    def __init__(
        self,
        message: str,
        *,
        execution_trace: list[AITraceEvent] | None = None,
        decision_summary: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.execution_trace = execution_trace or []
        self.decision_summary = decision_summary or {}


class FailureService:
    _OBSERVED_LOCATOR_PRIORITY = {
        "role": 0,
        "label": 1,
        "test_id": 2,
        "placeholder": 3,
        "id": 4,
        "text": 5,
        "css": 6,
    }

    def __init__(
        self,
        run_repo: TestRunRepository,
        workspace_repo: WorkspaceRepository,
        workspace_service: WorkspaceService,
        orchestrator: ProductionQAOrchestrator | None = None,
        history_repo: RunHistoryRepository | None = None,
        ai_repo: AIRepository | None = None,
        browser_runtime: BrowserRuntime | None = None,
        failure_repo: FailureRepository | None = None,
        transaction: TransactionBoundary | None = None,
        repository_scope: RepositoryScopeFactory | None = None,
    ) -> None:
        self.run_repo = run_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service
        self.orchestrator = orchestrator or build_ai_orchestrator()
        self.history_repo = history_repo or RunHistoryRepository()
        self.ai_repo = ai_repo or AIRepository()
        if browser_runtime is None:
            from app.container import get_browser_runtime

            browser_runtime = get_browser_runtime()
        self.browser_runtime = browser_runtime
        if failure_repo is None or transaction is None:
            raise ValueError("FailureService requires explicit FailureRepository and transaction adapters")
        self.failure_repo = failure_repo
        self.transaction = transaction
        self.repository_scope = repository_scope

    def _to_dto(self, failure: FailureRecord) -> FailureRecord:
        category, _, extracted = FailureClassifier.classify(failure.error_message, failure.stack_trace)
        classification = category.value if category != FailureCategory.UNKNOWN else failure.classification
        failing_locator = (
            (extracted or failure.failing_locator or "").strip()
            if classification == FailureCategory.LOCATOR_CHANGED.value
            else ""
        )
        proposal = failure.repair_proposal
        if (
            not failing_locator
            or not proposal
            or not proposal.get("proposed_locator", "").strip()
            or proposal.get("old_locator", "").strip() != failing_locator
            or proposal.get("proposed_locator", "").strip() == failing_locator
        ):
            proposal = None
        return failure.model_copy(
            update={
                "classification": classification,
                "failure_kind": FailureClassifier.failure_kind(failure.error_message, failure.stack_trace),
                "error_message": SensitiveRedactor.redact_text(failure.error_message),
                "stack_trace": SensitiveRedactor.redact_text(failure.stack_trace),
                "failing_locator": SensitiveRedactor.redact_text(failing_locator) or None,
                "console_logs": SensitiveRedactor.redact_value(failure.console_logs),
                "repair_proposal": SensitiveRedactor.redact_value(proposal) if proposal else None,
            }
        )

    async def list_failures(self, project_id: str | None = None, limit: int = 50) -> list[FailureRecord]:
        records = await self.failure_repo.list(limit=limit, project_id=project_id)
        return [self._to_dto(record) for record in records]

    async def get_failure(self, failure_id: str) -> FailureRecord | None:
        failure = await self.get_failure_state(failure_id)
        return self._to_dto(failure) if failure else None

    async def get_failure_state(self, failure_id: str) -> FailureRecord | None:
        """Return the internal repair state; API callers must use the redacted DTO above."""
        failure = await self.failure_repo.get_by_id(failure_id)
        return failure

    async def diagnose_failure(self, failure_id: str) -> FailureRecord:
        failure = await self.failure_repo.get_by_id(failure_id)
        if not failure:
            raise ValueError(f"Failure record not found: {failure_id}")

        safe_error = SensitiveRedactor.redact_text(failure.error_message)
        safe_stack = SensitiveRedactor.redact_text(failure.stack_trace)
        diag = self.orchestrator.diagnose_failure(
            error_message=safe_error,
            stack_trace=safe_stack,
            test_nodeid=failure.test_nodeid,
        )
        await self.failure_repo.update_diagnosis(
            failure_id,
            error_message=safe_error,
            stack_trace=safe_stack,
            classification=diag.classification.value,
            suggested_action=diag.suggested_action,
            failing_locator=diag.failing_locator,
            clear_repair_proposal=diag.classification != FailureCategory.LOCATOR_CHANGED,
        )
        return self._to_dto(
            failure.model_copy(
                update={
                    "error_message": safe_error,
                    "stack_trace": safe_stack,
                    "classification": diag.classification.value,
                    "suggested_action": diag.suggested_action,
                    "failing_locator": diag.failing_locator,
                    "repair_proposal": (
                        failure.repair_proposal if diag.classification == FailureCategory.LOCATOR_CHANGED else None
                    ),
                }
            )
        )

    async def diagnose_failure_ai(
        self,
        failure_id: str,
        on_event: Callable[[AITraceEvent], Awaitable[None]] | None = None,
        *,
        extra_context: str = "",
        response_language: str = "en",
    ) -> FailureAnalysisResponse:
        failure = await self.failure_repo.get_by_id(failure_id)
        if not failure_id or not failure:
            raise ValueError(f"Failure record not found: {failure_id}")

        trace: list[AITraceEvent] = []

        async def emit(event_type: str, **kwargs) -> None:
            event = make_trace_event(failure.run_id, event_type, case_execution_id=failure.execution_id, **kwargs)
            trace.append(event)
            if on_event is not None:
                await on_event(event)

        last_progress_at = 0.0
        last_progress_chars = 0

        async def report_model_progress(generated_chars: int, elapsed_seconds: float) -> None:
            nonlocal last_progress_at, last_progress_chars
            if on_event is None:
                return
            now = time.monotonic()
            if not last_progress_at and elapsed_seconds < 1.5:
                return
            if last_progress_at and now - last_progress_at < 1.5 and generated_chars - last_progress_chars < 800:
                return
            last_progress_at = now
            last_progress_chars = generated_chars
            await emit(
                "model.progress",
                stage="model",
                title="模型正在生成诊断",
                status="RUNNING",
                message=f"模型已开始返回诊断（等待 {elapsed_seconds:.0f} 秒，收到 {generated_chars} 字符）。",
                metadata={"generated_chars": generated_chars, "elapsed_seconds": round(elapsed_seconds, 1)},
            )

        await emit(
            "analysis_started",
            stage="diagnosis",
            title="开始分析失败原因",
            status="RUNNING",
            message=f"正在分析 {failure.test_nodeid}",
            metadata={"failure_id": failure_id, "failure_type": failure.exception_type},
        )
        browser_session, page_evidence = await self._browser_evidence(failure.execution_id)
        source_run = await self.run_repo.get_by_id(failure.run_id)
        evidence = await FailureEvidenceService.collect(
            failure, source_run, self.workspace_service, browser_session, page_evidence
        )
        await emit(
            "context.loaded",
            stage="context",
            title="读取测试与 fixture 上下文",
            message=failure.test_nodeid,
            metadata={
                "paths": evidence.context_paths,
                "missing_evidence": evidence.missing,
                "evidence_version": evidence.version,
            },
        )
        await emit(
            "rule.classified",
            stage="classification",
            title="规则分类完成",
            message=evidence.failure_kind,
            metadata={"failure_kind": evidence.failure_kind, "source": "deterministic_rules"},
        )

        # Fetch historical context
        history_execs = await self.history_repo.get_test_executions(nodeid=failure.test_nodeid, limit=5)
        history_summary = "No prior executions."
        if history_execs:
            history_summary = "\n".join(
                f"- Run: {e.run_id[:8]} | Status: {e.status} | Category: {e.failure_category or 'N/A'} | Duration: {e.duration_ms}ms"
                for e in history_execs
            )
        if page_evidence:
            controls = page_evidence.get("controls") or []
            visible_names = [str(item.get("name") or "")[:100] for item in controls if item.get("name")][:12]
            page_context = {
                "current_url": (browser_session or {}).get("current_url") or page_evidence.get("url", ""),
                "title": page_evidence.get("title", ""),
                "observed_controls": visible_names,
            }
            history_summary += (
                "\nCurrent page evidence: "
                + json.dumps(SensitiveRedactor.redact_value(page_context), ensure_ascii=False)[:3000]
            )

        if extra_context:
            history_summary += "\nCaptured test context:\n" + SensitiveRedactor.redact_text(extra_context)[:6500]
        start = time.perf_counter()
        started_at = utc_now()

        safe_error = SensitiveRedactor.redact_text(failure.error_message or "")
        safe_stack = SensitiveRedactor.redact_text(failure.stack_trace or "")
        safe_locator = SensitiveRedactor.redact_text(failure.failing_locator or "") or None
        await emit(
            "evidence_collected",
            stage="evidence",
            title="已整理失败证据",
            message=f"读取错误与堆栈、{len(history_execs)} 条历史执行和当前页面记录。错误：{safe_error[:300]}",
            metadata={
                "has_traceback": bool(safe_stack),
                "failed_locator": safe_locator,
                "page_url": (browser_session or {}).get("current_url"),
                "control_count": len((page_evidence or {}).get("controls") or []),
                "history_count": len(history_execs),
            },
        )
        provider = getattr(self.orchestrator, "ai_provider", None)
        provider = getattr(provider, "primary", provider)
        configured_provider = getattr(provider, "provider_name", "")
        configured_model = getattr(provider, "model", "")
        await emit(
            "model.started",
            stage="model",
            title="正在请求 AI 诊断",
            status="RUNNING",
            message="模型正在根据失败证据生成根因、假设和建议。",
            metadata={"provider": configured_provider, "model": configured_model},
        )
        diag_ai = await self.orchestrator.diagnose_failure_ai(
            error_message=safe_error[:3000],
            stack_trace=safe_stack[-8000:],
            test_nodeid=failure.test_nodeid,
            failing_locator=safe_locator,
            historical_context=SensitiveRedactor.redact_text(history_summary)[:3000]
            + "\nFailure evidence bundle:\n"
            + evidence.model_copy(update={"error": "", "traceback": "", "assertion": ""}).render(limit=14000),
            on_progress=report_model_progress if on_event is not None else None,
            response_language=response_language,
        )
        observed, _, _ = FailureClassifier.classify(safe_error, safe_stack)
        try:
            diagnosed = FailureCategory(diag_ai.classification)
        except ValueError:
            diagnosed = FailureCategory.UNKNOWN
        if observed != FailureCategory.UNKNOWN and (
            diag_ai.provider in {"", "fake"} or diag_ai.fallback_used or diagnosed == FailureCategory.UNKNOWN
        ):
            diag_ai.classification = observed.value

        duration_ms = (time.perf_counter() - start) * 1000.0

        invocation = self.orchestrator.last_invocation_metadata()
        await emit(
            "model.completed",
            stage="model",
            title="模型诊断已返回",
            duration_ms=duration_ms,
            metadata={
                "provider": invocation["provider"],
                "model": invocation["model"],
                "fallback_used": invocation["fallback_used"],
            },
        )
        log_ai_execution(
            logger,
            feature="failure_analysis",
            provider=invocation["provider"],
            model=invocation["model"],
            duration_ms=duration_ms,
            status="SUCCESS",
            fallback_used=invocation["fallback_used"],
        )
        if not getattr(getattr(self.orchestrator, "ai_provider", None), "records_usage", False):
            await self.ai_repo.record_invocation(
                task="failure_diagnosis",
                provider=invocation["provider"],
                model=invocation["model"],
                fallback_used=invocation["fallback_used"],
                started_at=started_at,
                duration_ms=duration_ms,
                input_tokens=getattr(getattr(self.orchestrator, "last_completion", None), "input_tokens", None),
                output_tokens=getattr(getattr(self.orchestrator, "last_completion", None), "output_tokens", None),
                prompt_version=invocation.get("prompt_version"),
            )

        diag_ai.duration_ms = round(duration_ms, 1)
        await emit(
            "diagnosis_completed",
            stage="diagnosis",
            title="诊断已完成",
            message=SensitiveRedactor.redact_text(diag_ai.root_cause[:500]),
            status="FALLBACK" if invocation["fallback_used"] else "COMPLETED",
            duration_ms=duration_ms,
            metadata={
                "provider": invocation["provider"],
                "model": invocation["model"],
                "fallback_used": invocation["fallback_used"],
                "classification": diag_ai.classification,
            },
        )
        diag_ai.execution_trace = trace
        payload = evidence.model_dump(mode="json")
        if self.repository_scope is None:
            raise RuntimeError("Failure diagnosis requires a repository scope")
        async with self.repository_scope() as repositories:
            await repositories.failures.update_evidence_bundle(failure_id, payload)
            await repositories.commit()
        return diag_ai

    async def stream_diagnosis(self, failure_id: str) -> AsyncGenerator[AITraceEvent, None]:
        """Forward actual diagnosis milestones while the provider request is in flight."""
        queue: asyncio.Queue[AITraceEvent | None] = asyncio.Queue()
        run_id = failure_id

        async def forward(event: AITraceEvent) -> None:
            nonlocal run_id
            run_id = event.run_id
            await queue.put(event)

        async def diagnose() -> None:
            try:
                diagnosis = await self.diagnose_failure_ai(failure_id, on_event=forward)
                await queue.put(
                    make_trace_event(
                        run_id,
                        "run.completed",
                        stage="run",
                        title="根因分析完成",
                        metadata={"diagnosis": diagnosis.model_dump(mode="json")},
                    )
                )
            except Exception as error:
                logger.warning("Failure diagnosis failed failure_id=%s error_type=%s", failure_id, type(error).__name__)
                await queue.put(
                    make_trace_event(
                        run_id,
                        "run.failed",
                        stage="run",
                        title="根因分析失败",
                        status="FAILED",
                        message=SensitiveRedactor.redact_text(str(error))[:500],
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(diagnose(), name=f"failure-diagnosis-{failure_id}")
        try:
            while (event := await queue.get()) is not None:
                yield event
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def generate_repair_proposal(
        self,
        failure_id: str,
        *,
        diagnosis_override: FailureAnalysisResponse | None = None,
        resolved_classification: str | None = None,
        decision_service: LocatorDecisionService | None = None,
        evidence_execution_id: str | None = None,
        exclude_locators: list[str] | None = None,
    ) -> LocatorRepairProposal:
        failure = await self.failure_repo.get_by_id(failure_id)
        if not failure:
            raise ValueError(f"Failure record not found: {failure_id}")

        stored_analysis = await self._latest_trusted_failure_analysis(failure_id)
        if resolved_classification is None and stored_analysis:
            resolved_classification = str((stored_analysis.get("diagnosis") or {}).get("classification") or "") or None
        evidence_execution_id = evidence_execution_id or failure.execution_id
        browser_session, page_evidence = await self._browser_evidence(evidence_execution_id)
        original_run = await self.run_repo.get_by_id(failure.run_id)
        source_content = ""
        source_sha256 = None
        repair_file = failure.test_nodeid.split("::")[0].replace("\\", "/")
        if not _is_allowed_repair_target(repair_file):
            raise LocatorRepairNotApplicableError("REPAIR_TARGET_BLOCKED: automatic repair is limited to test code.")
        if original_run and original_run.workspace_id:
            try:
                source_content = await self.workspace_service.read_file(
                    original_run.workspace_id, failure.test_nodeid.split("::")[0]
                )
                source_sha256 = hashlib.sha256(source_content.encode("utf-8")).hexdigest()
            except (FileNotFoundError, ValueError):
                pass
        observed_locator = self._observed_failed_locator(page_evidence)
        failing_loc = self._require_locator_failure(
            failure,
            resolved_classification=resolved_classification,
            observed_locator=observed_locator,
        )
        if diagnosis_override is not None:
            diagnosis_root_cause = diagnosis_override.root_cause
            trace = list(diagnosis_override.execution_trace)
            diagnosis_provider = diagnosis_override.provider
            diagnosis_fallback_used = diagnosis_override.fallback_used
        elif stored_analysis:
            diagnosis = stored_analysis["diagnosis"]
            diagnosis_root_cause = str(diagnosis.get("root_cause") or "")
            trace = self._analysis_trace(stored_analysis.get("events") or [])
            diagnosis_provider = str(diagnosis.get("provider") or "")
            diagnosis_fallback_used = diagnosis.get("fallback_used") is True
        else:
            diagnosis_response = await self.diagnose_failure_ai(failure_id)
            diagnosis_root_cause = diagnosis_response.root_cause
            trace = list(diagnosis_response.execution_trace)
            diagnosis_provider = diagnosis_response.provider
            diagnosis_fallback_used = diagnosis_response.fallback_used
        candidate_selection = None
        verification_reason = "page_evidence_unavailable" if not page_evidence else "no_playwright_candidate"
        candidates = self._observed_locator_candidates(page_evidence)
        seen: set[tuple[str, str, str | None]] = {
            (str(candidate.get("kind", "")), str(candidate.get("value", "")), candidate.get("name"))
            for candidate in candidates
        }
        for candidate in self._candidates_from_analysis(stored_analysis):
            key = (str(candidate.get("kind", "")), str(candidate.get("value", "")), candidate.get("name"))
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)
        candidates = LocatorDecisionService.prioritize_candidates_for_failure(failing_loc, candidates)
        target_match = re.search(r"name\s*=\s*(['\"])(.*?)\1", failing_loc)
        failed_name = target_match.group(2)[:180] if target_match else ""
        current_url = str((browser_session or {}).get("current_url") or (page_evidence or {}).get("url") or "")
        event = {
            "tag": "element",
            "role": "",
            "name": failed_name,
            "url": current_url,
            "action": "click",
            "target": {
                "action": "click",
                "failed_locator": failing_loc[:300],
                "test_nodeid": failure.test_nodeid[:300],
                "root_cause": diagnosis_root_cause[:800],
            },
            "failed_locator": failing_loc[:500],
            "failure_type": failure.exception_type[:100],
            "error_excerpt": SensitiveRedactor.redact_text(failure.error_message or "")[:500],
            "context": {
                "failed_locator": failing_loc[:500],
                "classification": resolved_classification or FailureCategory.LOCATOR_CHANGED.value,
                "diagnosis": diagnosis_root_cause[:800],
                "error_excerpt": SensitiveRedactor.redact_text(failure.error_message or "")[:500],
            },
            "candidates": candidates,
        }
        ranked = LocatorDecisionService.generate_candidates(event)
        excluded = {item.strip() for item in (exclude_locators or []) if item.strip()}
        ranked = [candidate for candidate in ranked if candidate["locator"] not in excluded]
        if not ranked and excluded:
            raise LocatorRepairNotApplicableError(
                "REPAIR_CANDIDATES_EXHAUSTED: prior failed locator candidates were excluded."
            )
        verification_session = None
        live_page_available = False
        if ranked and current_url:
            try:
                verification_session = await self.browser_runtime.create_session()
                await self.browser_runtime.navigate(verification_session.id, current_url, timeout_ms=12_000)
                live_page_available = True
            except Exception as error:
                verification_reason = f"live_page_unavailable:{type(error).__name__}"
                if verification_session is not None:
                    await self.browser_runtime.close_session(verification_session.id)
                    verification_session = None
        elif ranked:
            verification_reason = "failed_page_url_unavailable"

        if ranked:
            try:
                pipeline = decision_service or LocatorDecisionService(
                    browser_runtime=self.browser_runtime, repository_scope=self.repository_scope
                )
                candidate_selection = await pipeline.decide(
                    run_id=failure.run_id,
                    event=event,
                    candidates=ranked,
                    browser_session_id=(
                        verification_session.id if live_page_available and verification_session else None
                    ),
                    case_execution_id=evidence_execution_id,
                    step_id=f"repair:{failure_id}",
                    require_jev=(
                        get_config().repair.require_jev or not get_config().jev.failure_policy.allow_local_fallback
                    ),
                )
            except Exception as error:
                verification_reason = f"locator_decision_failed:{type(error).__name__}"
            finally:
                if verification_session is not None:
                    await self.browser_runtime.close_session(verification_session.id)

        if candidate_selection:
            trace.extend(
                AITraceEvent.model_validate(event)
                for event in candidate_selection["trace"]
                if event.get("type") != "repair_suggested"
            )
        selected = (candidate_selection or {}).get("selected_candidate")
        verification = (candidate_selection or {}).get("verification") or {"verified": False}
        summary = (candidate_selection or {}).get("summary") or {}
        verification_source = "playwright" if verification.get("verified") and live_page_available else None
        if summary.get("provider") != "jev" or summary.get("fallback_used") is True:
            reason = str(summary.get("fallback_reason") or "JEV_UNAVAILABLE")
            raise LocatorRepairNotApplicableError(
                f"{reason}: Jev did not make a trusted candidate decision.",
                execution_trace=trace,
                decision_summary=summary,
            )
        if selected is None:
            reason = str(summary.get("fallback_reason") or "JEV_SELECTED_CANDIDATE_FAILED")
            raise LocatorRepairNotApplicableError(
                f"{reason}: Jev-selected candidate was not verified by Playwright.",
                execution_trace=trace,
                decision_summary=summary,
            )
        confidence = summary.get("confidence")
        minimum_confidence = get_config().jev.minimum_confidence
        if not isinstance(confidence, (int, float)) or confidence < minimum_confidence:
            raise LocatorRepairNotApplicableError(
                f"JEV_LOW_CONFIDENCE: decision confidence is below {minimum_confidence:.2f}.",
                execution_trace=trace,
                decision_summary=summary,
            )
        if (
            not verification.get("verified")
            and not live_page_available
            and self._candidate_matches_captured_control(selected, page_evidence, action="click")
        ):
            verification = {
                "unique": True,
                "visible": True,
                "enabled": True,
                "actionable": True,
                "verified": True,
            }
            verification_source = "playwright_snapshot"
            trace.append(
                make_trace_event(
                    failure.run_id,
                    "candidate.snapshot_verified",
                    stage="candidate_verification",
                    title="Captured Playwright control verified",
                    message="The Jev-selected locator uniquely matches a visible, enabled interactive control in the failed-run Playwright evidence.",
                    metadata={
                        "provider": "jev",
                        "candidate_id": selected.get("candidate_id"),
                        "verification_source": verification_source,
                        "unique": True,
                        "visible": True,
                        "enabled": True,
                        "actionable": True,
                        "verified": True,
                    },
                )
            )
        if get_config().repair.require_candidate_verification and (
            not verification.get("verified") or verification_source not in {"playwright", "playwright_snapshot"}
        ):
            raise LocatorRepairNotApplicableError("PLAYWRIGHT_VERIFICATION_REQUIRED: candidate is not verified.")
        proposal_fields = {
            "candidate_id": summary.get("candidate_id"),
            "provider": summary.get("provider", "local-strategy"),
            "model": summary.get("model"),
            "latency_ms": summary.get("latency_ms"),
            "ai_provider": diagnosis_provider,
            "ai_fallback_used": diagnosis_fallback_used,
            "resolved_classification": resolved_classification or FailureCategory.LOCATOR_CHANGED.value,
            "source_sha256": source_sha256,
            "decision_summary": {**summary, "verification_source": verification_source},
            "verified": bool(verification.get("verified")),
            "verification_reason": None
            if verification.get("verified")
            else verification_reason or summary.get("fallback_reason"),
        }
        proposal = LocatorRepairProposal(
            old_locator=failing_loc,
            proposed_locator=selected["locator"],
            confidence=summary.get("confidence"),
            strategy=selected["strategy"],
            reason=f"Playwright verified this candidate against the observed failure page. Decision engine: {summary['engine']}",
            file_path=failure.test_nodeid.split("::")[0],
            explanation=diagnosis_root_cause,
            **proposal_fields,
            execution_trace=trace,
        )
        safe_proposed_locator = SensitiveRedactor.redact_text(proposal.proposed_locator)
        proposal.execution_trace = _validated_trace_events(
            trace
            + [
                make_trace_event(
                    failure.run_id,
                    "repair_suggested",
                    stage="repair",
                    title="Verified repair suggestion created",
                    message=f"Jev selected {safe_proposed_locator}; Playwright verified the candidate.",
                    case_execution_id=failure.execution_id,
                    metadata={
                        "failure_id": failure_id,
                        "verified": True,
                        "verification_source": verification_source,
                        "decision_summary": summary,
                    },
                ),
            ]
        )
        if not proposal.proposed_locator.strip() or proposal.proposed_locator.strip() == failing_loc.strip():
            raise LocatorRepairNotApplicableError("候选定位器与原定位器相同，不生成无变化的修复提案。")
        run = original_run
        if run and run.workspace_id and source_content:
            try:
                preview = self._patched_content(
                    source_content,
                    proposal.file_path,
                    failing_loc,
                    proposal.proposed_locator,
                    test_name=failure.test_nodeid.split("::")[-1].split("[")[0],
                )
                if preview is not None:
                    proposal.code_diff = "".join(
                        difflib.unified_diff(
                            source_content.splitlines(keepends=True),
                            preview.splitlines(keepends=True),
                            fromfile=proposal.file_path,
                            tofile=proposal.file_path,
                        )
                    )[:16000]
            except (FileNotFoundError, ValueError):
                pass  # Missing source is shown as an unavailable diff; never invent one.
        await self.failure_repo.update_repair_proposal(
            failure.id,
            proposal.model_dump(mode="json"),
            failing_locator=observed_locator if not failure.failing_locator else None,
        )
        return proposal

    async def _latest_trusted_failure_analysis(self, failure_id: str) -> dict | None:
        rows = await self.failure_repo.latest_completed_analyses(failure_id, limit=10)
        for row in rows:
            result = row["result"]
            diagnosis = result.get("diagnosis")
            if not isinstance(diagnosis, dict):
                continue
            provider = str(diagnosis.get("provider") or "").strip().lower()
            if provider and provider != "fake" and diagnosis.get("fallback_used") is not True:
                return {"diagnosis": diagnosis, "events": row["events"], "result": result}
        return None

    @staticmethod
    def _analysis_trace(events: list[dict]) -> list[AITraceEvent]:
        trace: list[AITraceEvent] = []
        for event in events:
            try:
                trace.append(AITraceEvent.model_validate(event))
            except Exception:
                continue
        return trace

    @staticmethod
    def _candidates_from_analysis(analysis: dict | None) -> list[dict]:
        if not analysis:
            return []
        candidates: list[dict] = []
        seen: set[tuple[str, str, str | None]] = set()
        for event in analysis.get("events") or []:
            metadata = event.get("metadata") or {}
            for candidate in metadata.get("candidates") or []:
                key = (str(candidate.get("kind", "")), str(candidate.get("value", "")), candidate.get("name"))
                if key not in seen:
                    seen.add(key)
                    candidates.append(candidate)
        return candidates

    @staticmethod
    def _require_locator_failure(
        failure: FailureRecord,
        *,
        resolved_classification: str | None = None,
        observed_locator: str | None = None,
    ) -> str:
        category, _, extracted = FailureClassifier.classify(failure.error_message, failure.stack_trace)
        if resolved_classification:
            try:
                resolved = FailureCategory(resolved_classification)
            except ValueError:
                resolved = FailureCategory.UNKNOWN
            if resolved != FailureCategory.UNKNOWN:
                category = resolved
        if category != FailureCategory.LOCATOR_CHANGED:
            raise LocatorRepairNotApplicableError(
                f"当前错误属于 {category.value}，不适用定位器修复。请先核对失败断言、实际结果与测试意图。"
            )
        locator = SensitiveRedactor.redact_text(extracted or failure.failing_locator or observed_locator or "").strip()
        if not locator:
            raise LocatorRepairNotApplicableError("未记录实际失效的定位器，不生成修复提案。")
        return locator

    @staticmethod
    def _observed_failed_locator(page_evidence: dict | None) -> str | None:
        """Use the failed action captured by the live browser plugin when traceback classification has no selector."""
        if not isinstance(page_evidence, dict):
            return None
        recent_steps = page_evidence.get("recent_steps")
        if not isinstance(recent_steps, list):
            return None
        for step in reversed(recent_steps):
            if not isinstance(step, dict) or str(step.get("status", "")).upper() != "FAILED":
                continue
            locator = step.get("locator")
            if not isinstance(locator, str) or not locator.strip():
                continue
            locator = locator.strip()
            if locator.startswith("css="):
                locator = locator.removeprefix("css=")
            return locator or None
        return None

    @classmethod
    def _observed_locator_candidates(cls, page_evidence: dict | None) -> list[dict]:
        """Keep one strongest observed locator per control; do not ask Jev to choose among aliases."""
        if not isinstance(page_evidence, dict):
            return []
        controls = page_evidence.get("controls")
        if not isinstance(controls, list):
            return []
        candidates: list[dict] = []
        seen: set[tuple[str, str, str | None]] = set()
        for control in controls:
            if not isinstance(control, dict):
                continue
            observed = control.get("candidates")
            if not isinstance(observed, list):
                continue
            usable = [candidate for candidate in observed if isinstance(candidate, dict) and candidate.get("value")]
            if not usable:
                continue
            candidate = min(
                usable,
                key=lambda item: cls._OBSERVED_LOCATOR_PRIORITY.get(str(item.get("kind", "")), 99),
            )
            key = (str(candidate.get("kind", "")), str(candidate.get("value", "")), candidate.get("name"))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    **candidate,
                    "evidence": {
                        **(candidate.get("evidence") or {}),
                        "dom_depth": control.get("dom_depth"),
                    },
                }
            )
        return candidates

    @staticmethod
    def _candidate_matches_observed_alias(candidate: dict, observed: dict) -> bool:
        if candidate.get("kind") != observed.get("kind") or candidate.get("value") != observed.get("value"):
            return False
        if candidate.get("kind") not in {"role", "label", "placeholder", "text"}:
            return True
        query = candidate.get("name") if candidate.get("kind") == "role" else candidate.get("value")
        observed_value = observed.get("name") if candidate.get("kind") == "role" else observed.get("value")
        if not isinstance(query, str) or not isinstance(observed_value, str):
            return False
        if "exact=True" in str(candidate.get("locator") or ""):
            return query == observed_value
        return query in observed_value

    @classmethod
    def _candidate_matches_captured_control(
        cls, candidate: dict | None, page_evidence: dict | None, *, action: str = "click"
    ) -> bool:
        """Verify a locator against unique, visible and actionable failed-run Playwright evidence."""
        # ponytail: snapshots cover captured controls only; the original-case rerun remains the final check.
        if not isinstance(candidate, dict):
            return False
        controls = page_evidence.get("controls") if isinstance(page_evidence, dict) else None
        if not isinstance(controls, list):
            return False
        matches = 0
        for control in controls:
            if not isinstance(control, dict):
                continue
            observed_candidates = control.get("candidates")
            if not isinstance(observed_candidates, list):
                continue
            matching_control = any(
                isinstance(observed, dict) and cls._candidate_matches_observed_alias(candidate, observed)
                for observed in observed_candidates
            )
            if matching_control:
                matches += 1
                if matches > 1 or control.get("visible") is not True or control.get("enabled") is not True:
                    return False
                if (
                    action in {"click", "double_click"}
                    and control.get("tag")
                    not in {
                        "button",
                        "a",
                        "input",
                        "textarea",
                        "select",
                        "summary",
                    }
                    and control.get("role") not in {"button", "link", "menuitem"}
                ):
                    return False
        return matches == 1

    async def _browser_evidence(self, execution_id: str):
        browser_session = await self.failure_repo.latest_browser_session(execution_id)
        if not browser_session or not browser_session.get("page_evidence_json"):
            return browser_session, None
        try:
            return browser_session, json.loads(browser_session["page_evidence_json"] or "")
        except (TypeError, json.JSONDecodeError):
            return browser_session, None

    async def review_semantic_repair(
        self, failure_id: str, candidate_locator: str | None = None
    ) -> LocatorSemanticReview:
        failure = await self.failure_repo.get_by_id(failure_id)
        if not failure:
            raise ValueError(f"Failure record not found: {failure_id}")

        old_loc = self._require_locator_failure(failure)
        new_loc = candidate_locator or (failure.repair_proposal or {}).get("proposed_locator", "")
        if not new_loc.strip() or new_loc.strip() == old_loc.strip():
            raise LocatorRepairNotApplicableError("没有有效且不同于原定位器的候选，无法进行语义审查。")

        start = time.perf_counter()
        started_at = utc_now()

        review = await self.orchestrator.review_locator_candidate(
            old_locator=old_loc,
            proposed_locator=new_loc,
            strategy="semantic-attribute",
            dom_snippet=failure.dom_snapshot_path or "",
            error_message=SensitiveRedactor.redact_text(failure.error_message or ""),
        )

        duration_ms = (time.perf_counter() - start) * 1000.0

        invocation = self.orchestrator.last_invocation_metadata()
        log_ai_execution(
            logger,
            feature="locator_analysis",
            provider=invocation["provider"],
            model=invocation["model"],
            duration_ms=duration_ms,
            status="SUCCESS",
            fallback_used=invocation["fallback_used"],
        )
        if not getattr(getattr(self.orchestrator, "ai_provider", None), "records_usage", False):
            await self.ai_repo.record_invocation(
                task="locator_review",
                provider=invocation["provider"],
                model=invocation["model"],
                fallback_used=invocation["fallback_used"],
                started_at=started_at,
                duration_ms=duration_ms,
                input_tokens=invocation.get("input_tokens"),
                output_tokens=invocation.get("output_tokens"),
                prompt_version=invocation.get("prompt_version"),
            )

        return review

    async def get_recurrence(self, failure_id: str) -> list[FailureRecurrenceItem]:
        failure = await self.failure_repo.get_by_id(failure_id)
        if not failure:
            raise ValueError(f"Failure record not found: {failure_id}")

        return await self.history_repo.get_failure_recurrence(
            nodeid=failure.test_nodeid,
            classification=failure.classification,
            exclude_failure_id=failure_id,
        )

    async def apply_repair(self, workspace_id: str, payload: ApplyRepairRequest, *, failure_id: str) -> dict[str, str]:
        """Apply a Jev-selected, browser-verified locator patch.

        The replacement is validated before it is written: a locator that contains the quote character
        used by the surrounding string (`"[data-testid=\"ok\"]"`) would otherwise produce a file that
        no longer parses. If no safe form of the patch exists, nothing is written and the caller is
        told why — the platform never leaves a workspace in a broken state.
        """
        failure = await self.failure_repo.get_by_id(failure_id)
        if failure is None:
            raise ValueError(f"Failure record not found: {failure_id}")
        proposal = failure.repair_proposal or {}
        decision_summary = proposal.get("decision_summary") or {}
        failing_locator = self._require_locator_failure(
            failure, resolved_classification=proposal.get("resolved_classification")
        )
        trusted_selection = (
            proposal.get("provider") == "jev"
            and decision_summary.get("fallback_used") is False
            and isinstance(decision_summary.get("confidence"), (int, float))
            and decision_summary["confidence"] >= get_config().jev.minimum_confidence
        )
        if (
            not proposal.get("verified")
            or not trusted_selection
            or proposal.get("ai_provider") in (None, "", "fake")
            or proposal.get("ai_fallback_used") is True
            or proposal.get("candidate_id") is None
            or proposal.get("proposed_locator") != payload.new_code
        ):
            raise ValueError("仅允许应用真实 AI 诊断且经 Playwright 或失败页捕获证据验证的候选。")
        if proposal.get("applied"):
            raise ValueError("该修复已应用；请先复核当前补丁或执行回滚。")
        failure_file = failure.test_nodeid.split("::")[0].replace("\\", "/")
        if not _is_allowed_repair_target(failure_file):
            raise ValueError("Automatic repair is limited to test code; production source is blocked.")
        if payload.old_code != failing_locator or payload.file_path.replace("\\", "/") != failure_file:
            raise ValueError("修复目标与失败记录中的定位器或文件不一致，不写入工作区。")
        if (
            not payload.old_code.strip()
            or not payload.new_code.strip()
            or payload.old_code.strip() == payload.new_code.strip()
        ):
            raise ValueError("修复补丁为空或与原代码相同，不写入工作区。")
        original_run = await self.run_repo.get_by_id(failure.run_id)
        if not original_run or original_run.workspace_id != workspace_id:
            raise ValueError("修复工作区与原失败运行不一致，不写入代码。")
        current_content = await self.workspace_service.read_file(workspace_id, payload.file_path)
        current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
        if proposal.get("source_sha256") != current_hash:
            raise ValueError("Source changed after repair candidates were generated; nothing was written.")
        if payload.old_code not in current_content:
            raise ValueError(f"Original target code block not found in {payload.file_path}")

        updated_content = self._patched_content(
            current_content,
            payload.file_path,
            payload.old_code,
            payload.new_code,
            test_name=failure.test_nodeid.split("::")[-1].split("[")[0],
        )
        if updated_content is None:
            raise ValueError(
                f"The proposed patch would make {payload.file_path} invalid; nothing was written. "
                "Review the locator and apply it manually."
            )

        await self.workspace_service.write_file_if_unchanged(
            workspace_id,
            payload.file_path,
            updated_content,
            expected_exists=True,
            expected_sha256=proposal["source_sha256"],
        )
        await self.failure_repo.update_repair_proposal(
            failure.id,
            {
                **proposal,
                "applied": True,
                "applied_at": utc_now().isoformat(),
                "proposed_locator": payload.new_code,
                "rollback_content": current_content,
                "rollback_original_sha256": hashlib.sha256(current_content.encode("utf-8")).hexdigest(),
                "applied_sha256": hashlib.sha256(updated_content.encode("utf-8")).hexdigest(),
                "rollback_status": "AVAILABLE",
            },
        )
        return {"status": "applied", "file_path": payload.file_path}

    async def rollback_repair(self, failure_id: str, workspace_id: str) -> dict[str, str]:
        failure = await self.failure_repo.get_by_id(failure_id)
        if failure is None:
            raise ValueError(f"Failure record not found: {failure_id}")
        original_run = await self.run_repo.get_by_id(failure.run_id)
        proposal = failure.repair_proposal or {}
        if not original_run or original_run.workspace_id != workspace_id:
            raise ValueError("回滚工作区与原失败运行不一致。")
        if not proposal.get("applied") or not isinstance(proposal.get("rollback_content"), str):
            raise ValueError("没有可回滚的修复补丁。")
        file_path = str(proposal.get("file_path") or failure.test_nodeid.split("::")[0])
        current_content = await self.workspace_service.read_file(workspace_id, file_path)
        current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
        if current_hash != proposal.get("applied_sha256"):
            raise ValueError("修复应用后文件已变化；为避免覆盖后续编辑，未执行回滚。")
        original_content = proposal["rollback_content"]
        if hashlib.sha256(original_content.encode("utf-8")).hexdigest() != proposal.get("rollback_original_sha256"):
            raise ValueError("回滚快照校验失败；未修改工作区。")
        await self.workspace_service.write_file(workspace_id, file_path, original_content)
        await self.failure_repo.update_repair_proposal(
            failure.id,
            {
                **proposal,
                "applied": False,
                "rolled_back_at": utc_now().isoformat(),
                "rollback_status": "ROLLED_BACK",
            },
        )
        return {"status": "rolled_back", "file_path": file_path}

    def _patched_content(
        self, content: str, file_path: str, old_code: str, new_code: str, *, test_name: str | None = None
    ) -> str | None:
        """Replace `old_code` once, preferring a form that keeps the file parseable."""
        index = content.find(old_code)
        if index == -1:
            return None
        if not file_path.endswith(".py"):
            return content[:index] + new_code + content[index + len(old_code) :]

        if test_name:
            functions = [
                node
                for node in ast.walk(ast.parse(content))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test_name
            ]
            if len(functions) != 1:
                return None
            segment = ast.get_source_segment(content, functions[0])
            if not segment or segment.count(old_code) != 1:
                return None
            index = content.index(segment) + segment.index(old_code)

        # Proposals contain public Playwright calls, not selector strings. Replace the
        # locator call itself so page.locator("#old") becomes page.get_by_role(...).
        methods = {"locator", "get_by_role", "get_by_text", "get_by_label", "get_by_placeholder", "get_by_test_id"}
        if any(new_code.startswith(method + "(") for method in methods):
            try:
                proposed = ast.parse(new_code, mode="eval").body
                if (
                    not isinstance(proposed, ast.Call)
                    or not isinstance(proposed.func, ast.Name)
                    or proposed.func.id not in methods
                    or not all(isinstance(arg, ast.Constant) for arg in proposed.args)
                    or not all(
                        keyword.arg is not None and isinstance(keyword.value, ast.Constant)
                        for keyword in proposed.keywords
                    )
                ):
                    return None
                tree = ast.parse(content)
                scopes = (
                    [
                        node
                        for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test_name
                    ]
                    if test_name
                    else [tree]
                )
                matches = [
                    node
                    for scope in scopes
                    for node in ast.walk(scope)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in methods
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == old_code
                ]
                if len(matches) != 1:
                    return None
                target = matches[0]
                receiver = ast.get_source_segment(content, target.func.value)
                encoded = content.encode("utf-8")
                lines = encoded.splitlines(keepends=True)
                start = sum(map(len, lines[: target.lineno - 1])) + target.col_offset
                end = sum(map(len, lines[: target.end_lineno - 1])) + target.end_col_offset
                updated = (encoded[:start] + f"{receiver}.{new_code}".encode("utf-8") + encoded[end:]).decode("utf-8")
                ast.parse(updated)
                return updated
            except (SyntaxError, ValueError):
                return None

        opening_quote = content[index - 1] if index > 0 else ""
        candidates = [new_code]
        if opening_quote in ("'", '"') and opening_quote in new_code:
            candidates.append(new_code.replace(opening_quote, f"\\{opening_quote}"))

        for candidate in candidates:
            updated = content[:index] + candidate + content[index + len(old_code) :]
            try:
                ast.parse(updated)
            except SyntaxError:
                continue
            return updated
        return None
