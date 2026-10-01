from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import AsyncGenerator

from qa_core.ai.trace import AITraceEvent, make_trace_event
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.models import FailureCategory
from qa_core.failure.redactor import SensitiveRedactor

from app.repositories.failure_analysis_repo import FailureAnalysisRepository
from app.services.failure_service import FailureService
from app.services.locator_decision_service import LocatorDecisionService
from app.services.workspace_service import SecurityException


class FailureWorkflowService:
    """Evidence-based diagnosis across UI, API and Python failures; never writes or reruns tests."""

    def __init__(self, failure_service: FailureService, decision_service: LocatorDecisionService | None = None):
        self.failures = failure_service
        self.decisions = decision_service or LocatorDecisionService()
        self.history = FailureAnalysisRepository()

    async def attach_verification(self, failure_id: str, analysis_id: str, run_id: str) -> None:
        failure = await self.failures.run_repo.get_failure_by_id(failure_id)
        run = await self.failures.run_repo.get_by_id(run_id)
        original = await self.failures.run_repo.get_by_id(failure.run_id) if failure else None
        if not failure or not run or not original or run.id == original.id:
            raise ValueError("Verification requires a new run for this failure")
        if run.workspace_id != original.workspace_id or run.project_id != original.project_id:
            raise ValueError("Verification run belongs to a different workspace or project")
        if run.nodeids != [failure.test_nodeid]:
            raise ValueError("Verification run must execute exactly the failed test case")
        analyses = await self.history.list(failure_id)
        analysis = next((item for item in analyses if item["id"] == analysis_id), None)
        if analysis is None or run.created_at.isoformat() < analysis["created_at"]:
            raise ValueError("Verification run must be created after the selected analysis")
        await self.history.attach_verification(analysis_id, failure_id, run_id)

    async def list_history(self, failure_id: str) -> list[dict]:
        rows = await self.history.list(failure_id)
        failure = await self.failures.run_repo.get_failure_by_id(failure_id)
        if failure is None:
            return rows
        for row in rows:
            run_id = row["result"].get("verification_run_id")
            if not run_id:
                continue
            run = await self.failures.run_repo.get_by_id(run_id)
            if not run or row["result"].get("verification_run_status") == run.status:
                continue
            completed = run.status in {"PASSED", "FAILED", "ERROR", "CANCELLED"}
            executions = await self.failures.run_repo.list_executions(run.id)
            execution = next((item for item in executions if item.nodeid == failure.test_nodeid), None)
            verified = run.status == "PASSED" and execution is not None and execution.status == "PASSED"
            result = {**row["result"], "verified": verified, "verification_run_status": run.status}
            event = make_trace_event(
                failure.run_id,
                "workflow.step",
                stage="verification",
                step_id=f"{row['id']}:verification",
                title="验证修复结果",
                status="COMPLETED" if verified else "FAILED" if completed else "RUNNING",
                message=f"实际复测 {run.id} · {run.status}" if completed else f"复测 {run.id} 已提交，等待执行结果",
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
            await self.history.append(row["id"], event, result=result)
        return await self.history.list(failure_id)

    async def stream(self, failure_id: str) -> AsyncGenerator[AITraceEvent, None]:
        failure = await self.failures.run_repo.get_failure_by_id(failure_id)
        if failure is None:
            raise ValueError("Failure record not found")
        analysis_id = await self.history.create(failure_id)
        queue: asyncio.Queue[AITraceEvent | None] = asyncio.Queue()
        active_stage = "context"
        stage_started: dict[str, float] = {}

        async def publish(event: AITraceEvent, result: dict | None = None):
            event.metadata = {**event.metadata, "analysis_id": analysis_id}
            event = AITraceEvent.model_validate(SensitiveRedactor.redact_value(event.model_dump(mode="json")))
            await self.history.append(analysis_id, event, result=result)
            await queue.put(event)

        async def step(key: str, status: str, message: str, **metadata):
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
                )
            )

        async def analyze():
            try:
                category, explanation, locator = FailureClassifier.classify(failure.error_message, failure.stack_trace)
                browser, page_evidence = await self.failures._browser_evidence(failure.execution_id)
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
                await step("context", "RUNNING", "正在读取测试与运行上下文")
                run = await self.failures.run_repo.get_by_id(failure.run_id)
                environment = SensitiveRedactor.redact_value(run.environment or {}) if run else {}
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
                    raw_candidates = []
                    seen = set()
                    for control in (page_evidence or {}).get("controls") or []:
                        for item in control.get("candidates") or []:
                            identity = (item.get("kind"), item.get("value"), item.get("name"))
                            if identity not in seen:
                                seen.add(identity)
                                raw_candidates.append(item)
                    failed_locator = locator or failure.failing_locator or ""
                    event = {
                        "candidates": raw_candidates,
                        "failed_locator": failed_locator,
                        "url": browser.current_url if browser else "",
                        "action": "click",
                        "context": {"failed_locator": failed_locator, "error_excerpt": failure.error_message[:500]},
                    }
                    candidates = self.decisions.generate_candidates(event)
                    ignored = {"old", "button", "element", "locator", "get", "by", "role", "name", "test", "id"}
                    tokens = set(re.findall(r"[a-z0-9]+", failed_locator.lower())) - ignored
                    eligible_candidates = [
                        item
                        for item in candidates
                        if tokens
                        & set(
                            re.findall(
                                r"[a-z0-9]+",
                                f"{item.get('value', '')} {item.get('name', '')}".lower(),
                            )
                        )
                    ]
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
                await step("diagnosis", "RUNNING", "AI 正在基于当前证据分析根因")
                diagnosis = await self.failures.diagnose_failure_ai(
                    failure_id,
                    on_event=publish,
                    extra_context=json.dumps(
                        {
                            "domain": domain,
                            "region": region,
                            "source_path": file_path,
                            "source_excerpt": SensitiveRedactor.redact_text(source[:5500]),
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
                selection = None
                if category == FailureCategory.LOCATOR_CHANGED and eligible_candidates:
                    await step("decision", "RUNNING", "正在选择证据支持的候选 Locator")
                    selection = await self.decisions.decide(
                        run_id=failure.run_id,
                        event=event,
                        candidates=eligible_candidates,
                        page=None,
                        case_execution_id=failure.execution_id,
                        on_event=publish,
                    )
                    summary = selection["summary"]
                    await step(
                        "decision",
                        "COMPLETED" if summary.get("selected_locator") else "BLOCKED",
                        f"{summary['engine']} · {summary.get('selected_locator') or '未选出候选'}",
                        **summary,
                    )
                else:
                    await step(
                        "decision",
                        "SKIPPED" if category != FailureCategory.LOCATOR_CHANGED else "BLOCKED",
                        "当前错误不适用 Locator 决策"
                        if category != FailureCategory.LOCATOR_CHANGED
                        else "没有与失效目标关联的候选证据，未调用 Jev",
                    )
                await step("suggestion", "RUNNING", "正在整理修复建议和验证条件")
                await step(
                    "suggestion",
                    "COMPLETED" if diagnosis.recommended_actions else "BLOCKED",
                    "；".join(diagnosis.recommended_actions[:4]) or "证据不足，未生成修复建议",
                    recommended_actions=diagnosis.recommended_actions,
                    hypotheses=diagnosis.hypotheses,
                    candidate_verified=False,
                    changes_applied=False,
                )
                await step(
                    "verification",
                    "PENDING",
                    "尚未应用补丁或执行复测；分析完成不代表修复成功",
                    test_rerun=False,
                    candidate_verified=False,
                    changes_applied=False,
                )
                result = {
                    "domain": domain,
                    "diagnosis": diagnosis.model_dump(mode="json", exclude={"execution_trace"}),
                    "selection": selection["summary"] if selection else None,
                    "verified": False,
                }
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "run.completed",
                        stage="workflow",
                        title="分析完成，等待验证",
                        metadata={"analysis_id": analysis_id, **result},
                    ),
                    result=result,
                )
            except asyncio.CancelledError:
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "run.cancelled",
                        stage=active_stage,
                        title="分析已取消",
                        status="CANCELLED",
                        message="用户中止了分析，未执行修复或复测",
                    )
                )
                raise
            except Exception as error:
                await step(active_stage, "FAILED", str(error)[:500])
                await publish(
                    make_trace_event(
                        failure.run_id,
                        "run.failed",
                        stage=active_stage,
                        title="分析失败",
                        status="FAILED",
                        message=SensitiveRedactor.redact_text(str(error))[:500],
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(analyze(), name=f"failure-workflow-{analysis_id}")
        try:
            while (event := await queue.get()) is not None:
                yield event
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
