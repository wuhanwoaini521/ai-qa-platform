from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncGenerator, Awaitable, Callable

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
from qa_core.healing.healer import NoLocatorCandidateError
from qa_core.healing.models import LocatorRepairProposal
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator
from sqlalchemy import select

from app.persistence.models import BrowserSessionORM, FailureRecordORM, utc_now
from app.repositories.ai_repo import AIRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.ai_observability import log_ai_execution
from app.services.locator_decision_service import LocatorDecisionService
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger("app.ai")


def _validated_trace_events(events: list[AITraceEvent | dict[str, object]]) -> list[AITraceEvent]:
    return [AITraceEvent.model_validate(event) for event in events]


class LocatorRepairNotApplicableError(ValueError):
    """Failure evidence does not support a locator repair."""


class FailureService:
    def __init__(
        self,
        run_repo: TestRunRepository,
        workspace_repo: WorkspaceRepository,
        workspace_service: WorkspaceService,
        orchestrator: ProductionQAOrchestrator | None = None,
        history_repo: RunHistoryRepository | None = None,
        ai_repo: AIRepository | None = None,
    ) -> None:
        self.run_repo = run_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service
        self.orchestrator = orchestrator or ProductionQAOrchestrator()
        self.history_repo = history_repo or RunHistoryRepository()
        self.ai_repo = ai_repo or AIRepository()

    def _to_dto(self, orm: FailureRecordORM) -> FailureRecord:
        category, _, extracted = FailureClassifier.classify(orm.error_message or "", orm.stack_trace or "")
        classification = category.value if category != FailureCategory.UNKNOWN else orm.classification
        failing_locator = (
            (extracted or orm.failing_locator or "").strip()
            if classification == FailureCategory.LOCATOR_CHANGED.value
            else ""
        )
        proposal = orm.repair_proposal
        if (
            not failing_locator
            or not proposal
            or not proposal.get("proposed_locator", "").strip()
            or proposal.get("old_locator", "").strip() != failing_locator
            or proposal.get("proposed_locator", "").strip() == failing_locator
        ):
            proposal = None
        return FailureRecord(
            id=orm.id,
            run_id=orm.run_id,
            execution_id=orm.execution_id,
            test_nodeid=orm.test_nodeid,
            test_name=orm.test_name,
            classification=classification,
            exception_type=orm.exception_type,
            error_message=SensitiveRedactor.redact_text(orm.error_message or ""),
            stack_trace=SensitiveRedactor.redact_text(orm.stack_trace or ""),
            failing_locator=SensitiveRedactor.redact_text(failing_locator) or None,
            screenshot_path=orm.screenshot_path,
            trace_path=orm.trace_path,
            dom_snapshot_path=orm.dom_snapshot_path,
            console_logs=SensitiveRedactor.redact_value(orm.console_logs or []),
            suggested_action=orm.suggested_action,
            repair_proposal=SensitiveRedactor.redact_value(proposal) if proposal else None,
            created_at=orm.created_at,
        )

    async def list_failures(self, project_id: str | None = None, limit: int = 50) -> list[FailureRecord]:
        orms = await self.run_repo.list_failures(limit=limit, project_id=project_id)
        return [self._to_dto(orm) for orm in orms]

    async def get_failure(self, failure_id: str) -> FailureRecord | None:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def diagnose_failure(self, failure_id: str) -> FailureRecord:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        safe_error = SensitiveRedactor.redact_text(orm.error_message or "")
        safe_stack = SensitiveRedactor.redact_text(orm.stack_trace or "")
        orm.error_message = safe_error
        orm.stack_trace = safe_stack
        diag = self.orchestrator.diagnose_failure(
            error_message=safe_error,
            stack_trace=safe_stack,
            test_nodeid=orm.test_nodeid,
        )
        orm.classification = diag.classification.value
        orm.suggested_action = diag.suggested_action
        orm.failing_locator = diag.failing_locator
        if diag.classification != FailureCategory.LOCATOR_CHANGED:
            orm.repair_proposal = None

        await self.run_repo.session.flush()
        return self._to_dto(orm)

    async def diagnose_failure_ai(
        self,
        failure_id: str,
        on_event: Callable[[AITraceEvent], Awaitable[None]] | None = None,
        *,
        extra_context: str = "",
    ) -> FailureAnalysisResponse:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not failure_id or not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        trace: list[AITraceEvent] = []

        async def emit(event_type: str, **kwargs) -> None:
            event = make_trace_event(orm.run_id, event_type, case_execution_id=orm.execution_id, **kwargs)
            trace.append(event)
            if on_event is not None:
                await on_event(event)

        await emit(
            "analysis_started",
            stage="diagnosis",
            title="开始分析失败原因",
            status="RUNNING",
            message=f"正在分析 {orm.test_nodeid}",
            metadata={"failure_id": failure_id, "failure_type": orm.exception_type},
        )
        browser_session, page_evidence = await self._browser_evidence(orm.execution_id)

        # Fetch historical context
        history_execs = await self.history_repo.get_test_executions(nodeid=orm.test_nodeid, limit=5)
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
                "current_url": browser_session.current_url if browser_session else page_evidence.get("url", ""),
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

        safe_error = SensitiveRedactor.redact_text(orm.error_message or "")
        safe_stack = SensitiveRedactor.redact_text(orm.stack_trace or "")
        safe_locator = SensitiveRedactor.redact_text(orm.failing_locator or "") or None
        await emit(
            "evidence_collected",
            stage="evidence",
            title="已整理失败证据",
            message=f"读取错误与堆栈、{len(history_execs)} 条历史执行和当前页面记录。错误：{safe_error[:300]}",
            metadata={
                "has_traceback": bool(safe_stack),
                "failed_locator": safe_locator,
                "page_url": browser_session.current_url if browser_session else None,
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
            error_message=safe_error,
            stack_trace=safe_stack,
            test_nodeid=orm.test_nodeid,
            failing_locator=safe_locator,
            historical_context=SensitiveRedactor.redact_text(history_summary),
        )
        observed, _, _ = FailureClassifier.classify(safe_error, safe_stack)
        if observed != FailureCategory.UNKNOWN:
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
        await self.ai_repo.record_invocation(
            task="failure_diagnosis",
            provider=invocation["provider"],
            model=invocation["model"],
            fallback_used=invocation["fallback_used"],
            started_at=started_at,
            duration_ms=duration_ms,
            input_tokens=getattr(getattr(self.orchestrator, "last_completion", None), "input_tokens", None),
            output_tokens=getattr(getattr(self.orchestrator, "last_completion", None), "output_tokens", None),
            prompt_version="v1.0",
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

    async def generate_repair_proposal(self, failure_id: str) -> LocatorRepairProposal:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        failing_loc = self._require_locator_failure(orm)
        diagnosis = await self.diagnose_failure_ai(failure_id)
        trace = list(diagnosis.execution_trace)
        browser_session, page_evidence = await self._browser_evidence(orm.execution_id)
        candidate_selection = None
        verification_reason = "page_evidence_unavailable"
        if browser_session and page_evidence and browser_session.current_url:
            controls = page_evidence.get("controls") or []
            candidates = []
            seen: set[tuple[str, str, str | None]] = set()
            for control in controls:
                for candidate in control.get("candidates") or []:
                    key = (str(candidate.get("kind", "")), str(candidate.get("value", "")), candidate.get("name"))
                    if key not in seen:
                        seen.add(key)
                        candidates.append(
                            {**candidate, "evidence": {"uniqueness": True, "dom_depth": control.get("dom_depth")}}
                        )
            target_match = re.search(r"name\s*=\s*(['\"])(.*?)\1", failing_loc)
            failed_name = target_match.group(2)[:180] if target_match else ""
            event = {
                "tag": "element",
                "role": "",
                "name": failed_name,
                "url": browser_session.current_url,
                "action": "click",
                "failed_locator": failing_loc[:500],
                "failure_type": orm.exception_type[:100],
                "error_excerpt": SensitiveRedactor.redact_text(orm.error_message or "")[:500],
                "candidates": candidates,
            }
            ranked = LocatorDecisionService.generate_candidates(event)
            try:
                from playwright.async_api import async_playwright

                from app.services.browser_proxy import browser_proxy_options

                async with async_playwright() as playwright:
                    proxy = browser_proxy_options()
                    browser = await playwright.chromium.launch(headless=True, **({"proxy": proxy} if proxy else {}))
                    try:
                        page = await browser.new_page()
                        await page.goto(browser_session.current_url, wait_until="domcontentloaded", timeout=12000)
                        candidate_selection = await LocatorDecisionService().decide(
                            run_id=orm.run_id,
                            event=event,
                            candidates=ranked,
                            page=page,
                            case_execution_id=orm.execution_id,
                            step_id=f"repair:{failure_id}",
                        )
                    finally:
                        await browser.close()
            except Exception as error:
                verification_reason = type(error).__name__

        if candidate_selection:
            trace.extend(candidate_selection["trace"])
        selected = (candidate_selection or {}).get("selected_candidate")
        verification = (candidate_selection or {}).get("verification") or {"verified": False}
        if selected and verification.get("verified"):
            summary = candidate_selection["summary"]
            proposal = LocatorRepairProposal(
                old_locator=failing_loc,
                proposed_locator=selected["locator"],
                confidence=summary.get("confidence"),
                strategy=selected["strategy"],
                reason=(
                    f"Playwright verified this candidate against the observed failure page. Decision engine: {summary['engine']}"
                ),
                file_path=orm.test_nodeid.split("::")[0],
                explanation=diagnosis.root_cause,
                execution_trace=trace,
            )
        else:
            try:
                proposal = self.orchestrator.propose_locator_repair(
                    failing_locator=failing_loc,
                    error_message=SensitiveRedactor.redact_text(orm.error_message or ""),
                    file_path=orm.test_nodeid.split("::")[0],
                )
            except NoLocatorCandidateError as error:
                raise LocatorRepairNotApplicableError(
                    "没有取得可用的替代定位器证据，不生成修复提案。请先采集当前页面与 DOM。"
                ) from error
            proposal.execution_trace = _validated_trace_events(
                trace
                + [
                    make_trace_event(
                        orm.run_id,
                        "failed",
                        stage="verification",
                        title="Repair candidate could not be verified",
                        message=verification_reason,
                        case_execution_id=orm.execution_id,
                        status="FAILED",
                        metadata={
                            "failure_id": failure_id,
                            "verification": verification,
                            "reason": verification_reason,
                        },
                    ),
                    make_trace_event(
                        orm.run_id,
                        "repair_suggested",
                        stage="repair",
                        title="Unverified repair suggestion created",
                        message="Review the proposal manually; the current page did not yield a verified candidate.",
                        case_execution_id=orm.execution_id,
                        status="UNVERIFIED",
                        metadata={"failure_id": failure_id, "verified": False},
                    ),
                ]
            )
        if selected and verification.get("verified"):
            proposal.execution_trace = _validated_trace_events(
                trace
                + [
                    make_trace_event(
                        orm.run_id,
                        "repair_suggested",
                        stage="repair",
                        title="Verified repair suggestion created",
                        message=proposal.proposed_locator,
                        case_execution_id=orm.execution_id,
                        metadata={"failure_id": failure_id, "verified": True},
                    ),
                ]
            )
        if not proposal.proposed_locator.strip() or proposal.proposed_locator.strip() == failing_loc.strip():
            raise LocatorRepairNotApplicableError("候选定位器与原定位器相同，不生成无变化的修复提案。")
        orm.repair_proposal = proposal.model_dump(mode="json")
        await self.run_repo.session.flush()
        return proposal

    @staticmethod
    def _require_locator_failure(orm: FailureRecordORM) -> str:
        category, _, extracted = FailureClassifier.classify(orm.error_message or "", orm.stack_trace or "")
        if category != FailureCategory.LOCATOR_CHANGED:
            raise LocatorRepairNotApplicableError(
                f"当前错误属于 {category.value}，不适用定位器修复。请先核对失败断言、实际结果与测试意图。"
            )
        locator = SensitiveRedactor.redact_text(extracted or orm.failing_locator or "").strip()
        if not locator:
            raise LocatorRepairNotApplicableError("未记录实际失效的定位器，不生成修复提案。")
        return locator

    async def _browser_evidence(self, execution_id: str):
        result = await self.run_repo.session.execute(
            select(BrowserSessionORM)
            .where(BrowserSessionORM.case_execution_id == execution_id)
            .order_by(BrowserSessionORM.started_at.desc())
            .limit(1)
        )
        browser_session = result.scalar_one_or_none()
        if not browser_session or not browser_session.page_evidence_json:
            return browser_session, None
        try:
            return browser_session, json.loads(browser_session.page_evidence_json)
        except (TypeError, json.JSONDecodeError):
            return browser_session, None

    async def review_semantic_repair(
        self, failure_id: str, candidate_locator: str | None = None
    ) -> LocatorSemanticReview:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        old_loc = self._require_locator_failure(orm)
        new_loc = candidate_locator or (orm.repair_proposal or {}).get("proposed_locator", "")
        if not new_loc.strip() or new_loc.strip() == old_loc.strip():
            raise LocatorRepairNotApplicableError("没有有效且不同于原定位器的候选，无法进行语义审查。")

        start = time.perf_counter()
        started_at = utc_now()

        review = await self.orchestrator.review_locator_candidate(
            old_locator=old_loc,
            proposed_locator=new_loc,
            strategy="semantic-attribute",
            dom_snippet=orm.dom_snapshot_path or "",
            error_message=SensitiveRedactor.redact_text(orm.error_message or ""),
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
        await self.ai_repo.record_invocation(
            task="locator_review",
            provider=invocation["provider"],
            model=invocation["model"],
            fallback_used=invocation["fallback_used"],
            started_at=started_at,
            duration_ms=duration_ms,
            input_tokens=140,
            output_tokens=160,
            prompt_version="v1.0",
        )

        return review

    async def get_recurrence(self, failure_id: str) -> list[FailureRecurrenceItem]:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        return await self.history_repo.get_failure_recurrence(
            nodeid=orm.test_nodeid,
            classification=orm.classification,
            exclude_failure_id=failure_id,
        )

    async def apply_repair(self, workspace_id: str, payload: ApplyRepairRequest, *, failure_id: str) -> dict[str, str]:
        """Apply a human-approved repair patch.

        The replacement is validated before it is written: a locator that contains the quote character
        used by the surrounding string (`"[data-testid=\"ok\"]"`) would otherwise produce a file that
        no longer parses. If no safe form of the patch exists, nothing is written and the caller is
        told why — the platform never leaves a workspace in a broken state.
        """
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if orm is None:
            raise ValueError(f"Failure record not found: {failure_id}")
        failing_locator = self._require_locator_failure(orm)
        failure_file = orm.test_nodeid.split("::")[0].replace("\\", "/")
        if payload.old_code != failing_locator or payload.file_path.replace("\\", "/") != failure_file:
            raise ValueError("修复目标与失败记录中的定位器或文件不一致，不写入工作区。")
        if (
            not payload.old_code.strip()
            or not payload.new_code.strip()
            or payload.old_code.strip() == payload.new_code.strip()
        ):
            raise ValueError("修复补丁为空或与原代码相同，不写入工作区。")
        current_content = await self.workspace_service.read_file(workspace_id, payload.file_path)
        if payload.old_code not in current_content:
            raise ValueError(f"Original target code block not found in {payload.file_path}")

        updated_content = self._patched_content(current_content, payload.file_path, payload.old_code, payload.new_code)
        if updated_content is None:
            raise ValueError(
                f"The proposed patch would make {payload.file_path} invalid; nothing was written. "
                "Review the locator and apply it manually."
            )

        await self.workspace_service.write_file(workspace_id, payload.file_path, updated_content)
        return {"status": "applied", "file_path": payload.file_path}

    def _patched_content(self, content: str, file_path: str, old_code: str, new_code: str) -> str | None:
        """Replace `old_code` once, preferring a form that keeps the file parseable."""
        index = content.find(old_code)
        if index == -1:
            return None
        if not file_path.endswith(".py"):
            return content[:index] + new_code + content[index + len(old_code) :]

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
