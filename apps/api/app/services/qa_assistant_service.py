from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from uuid import uuid4

from project_model.models import QAChatRequest, QAChatResponse
from qa_core.ai.budget import AIBudgetGuard
from qa_core.ai.models import AICompletionRequest
from qa_core.ai.provider import stream_provider_completion
from qa_core.ai.trace import AITraceEvent, make_trace_event
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.persistence.models import utc_now
from app.repositories.ai_repo import AIRepository

logger = logging.getLogger("app.ai")


class QAAssistantService:
    def __init__(
        self,
        orchestrator: ProductionQAOrchestrator | None = None,
        ai_repo: AIRepository | None = None,
    ) -> None:
        self.orchestrator = orchestrator or ProductionQAOrchestrator()
        self.ai_repo = ai_repo or AIRepository()
        self.budget_guard = getattr(self.orchestrator, "budget_guard", None) or AIBudgetGuard()

    async def handle_request(self, req: QAChatRequest) -> QAChatResponse:
        action = req.action
        ctx = req.context

        val_issues = ""
        if ctx.latest_validation and ctx.latest_validation.issues:
            val_issues = "\n".join(f"- Line {i.line}: {i.message}" for i in ctx.latest_validation.issues[:5])

        start = time.perf_counter()
        started_at = utc_now()
        from qa_core.ai.context import ContextSelector

        from app.services.workspace_service import WorkspaceService

        bundle = ContextSelector().select(
            WorkspaceService().get_workspace_dir(ctx.project_id), test_nodeid=ctx.current_file, query=req.message
        )

        res = await self.orchestrator.assist_code_chat(
            action=action,
            message=req.message + "\nRelated repository context:\n" + bundle.render(),
            current_file=ctx.current_file,
            selected_code=ctx.selected_code,
            project_name=ctx.project_name,
            requirement_title=ctx.requirement_title,
            test_case_title=ctx.test_case_title,
            validation_issues=val_issues,
            git_diff=ctx.git_diff or "",
        )

        duration_ms = (time.perf_counter() - start) * 1000.0

        # Record AI Invocation
        invocation = self.orchestrator.last_invocation_metadata()
        if not getattr(getattr(self.orchestrator, "ai_provider", None), "records_usage", False):
            await self.ai_repo.record_invocation(
                task=f"assistant_{action}",
                provider=invocation["provider"],
                model=invocation["model"],
                fallback_used=invocation["fallback_used"],
                started_at=started_at,
                duration_ms=duration_ms,
                input_tokens=invocation.get("input_tokens"),
                output_tokens=invocation.get("output_tokens"),
                prompt_version=invocation.get("prompt_version"),
            )

        suggested_code = res.suggested_code
        target_file = res.target_file

        return QAChatResponse(
            response=res.reply,
            suggested_code=suggested_code,
            target_file=target_file,
            action_type=action if (not res.action_type or res.action_type == "reply") else res.action_type,
        )

    async def stream_request(self, req: QAChatRequest) -> AsyncGenerator[AITraceEvent, None]:
        """Stream a provider-neutral execution trace and answer for one Assistant run."""
        run_id = uuid4().hex
        started_at = utc_now()
        started = time.perf_counter()
        provider = getattr(self.orchestrator.ai_provider, "primary", self.orchestrator.ai_provider)
        configured_provider = getattr(provider, "provider_name", "unknown")
        configured_model = getattr(provider, "model", "")
        final_provider = configured_provider
        final_model = configured_model
        fallback_used = configured_provider == "fake"
        usage: dict[str, int | float | None] = {}
        answer = ""
        run_status = "FAILED"
        safe_error = "provider_unavailable"

        yield make_trace_event(
            run_id,
            "run.started",
            stage="run",
            title="AI 正在分析",
            metadata={"feature": "qa_assistant", "action": req.action},
        )
        try:
            ctx = req.context
            issues = ctx.latest_validation.issues[:5] if ctx.latest_validation else []
            yield make_trace_event(
                run_id,
                "context.loaded",
                stage="context",
                title="读取工作区上下文",
                message=ctx.current_file or ctx.project_name or "QA Assistant context ready",
                metadata={
                    "project_id": ctx.project_id,
                    "current_file": ctx.current_file,
                    "selected_code_chars": len(ctx.selected_code or ""),
                    "validation_issue_count": len(issues),
                },
            )
            yield make_trace_event(
                run_id,
                "evidence.collected",
                stage="evidence",
                title="整理可用证据",
                message=f"{int(bool(ctx.current_file)) + int(bool(ctx.selected_code)) + len(issues)} evidence source(s)",
                metadata={"source_count": int(bool(ctx.current_file)) + int(bool(ctx.selected_code)) + len(issues)},
            )

            validation_issues = "\n".join(f"- Line {item.line}: {item.message}" for item in issues)
            from qa_core.ai.context import ContextSelector
            from qa_core.failure.redactor import SensitiveRedactor
            from qa_core.prompts import ASSISTANT_STREAM_PROMPT

            from app.services.workspace_service import WorkspaceService

            bundle = ContextSelector().select(
                WorkspaceService().get_workspace_dir(ctx.project_id),
                test_nodeid=ctx.current_file,
            )
            prompt = ASSISTANT_STREAM_PROMPT.format(
                action=req.action,
                message=req.message or f"Please help with {req.action}.",
                project=ctx.project_name or ctx.project_id,
                requirement=ctx.requirement_title or "None",
                case=ctx.test_case_title or "None",
                current_file=ctx.current_file or "None",
                selected_code=(ctx.selected_code or "None")[:12000],
                repository_context=bundle.render(),
                validation=validation_issues or "None",
                diff=(ctx.git_diff or "None")[:4000],
            )
            completion = AICompletionRequest(
                run_id=run_id,
                prompt=SensitiveRedactor.redact_text(prompt),
                system_instruction=ASSISTANT_STREAM_PROMPT.system_instruction,
                prompt_id=ASSISTANT_STREAM_PROMPT.prompt_id,
                prompt_version=ASSISTANT_STREAM_PROMPT.version,
                temperature=0.2,
                max_tokens=2000,
            )
            self.budget_guard.check_and_record_request()
            yield make_trace_event(
                run_id,
                "context.loaded",
                stage="context",
                title="检索相关代码与 fixture",
                message=f"{len(bundle.fragments)} files · {bundle.total_chars} characters",
                metadata={
                    "paths": bundle.paths,
                    "omitted": bundle.omitted,
                    "prompt_version": completion.prompt_version,
                },
            )
            yield make_trace_event(
                run_id,
                "model.started",
                stage="model",
                title="请求 AI Provider",
                message=f"{configured_provider} · {configured_model}".strip(" ·"),
                metadata={"provider": configured_provider, "model": configured_model},
            )

            async for chunk in stream_provider_completion(self.orchestrator.ai_provider, completion):
                final_provider = chunk.provider or final_provider
                final_model = chunk.model or final_model
                fallback_used = fallback_used or chunk.fallback_used or final_provider == "fake"
                if chunk.usage:
                    usage.update({key: value for key, value in chunk.usage.items() if value is not None})
                if chunk.content_delta:
                    answer += chunk.content_delta
                    yield make_trace_event(
                        run_id,
                        "model.delta",
                        stage="model",
                        title="AI 回答增量",
                        content=chunk.content_delta,
                    )

            self.budget_guard.record_tokens(
                _usage_count(usage, "prompt_tokens", None), _usage_count(usage, "completion_tokens", None)
            )
            if not answer.strip():
                raise RuntimeError("empty_model_response")

            duration_ms = (time.perf_counter() - started) * 1000
            yield make_trace_event(
                run_id,
                "model.completed",
                stage="model",
                title="AI 生成完成",
                metadata={
                    "provider": final_provider,
                    "model": final_model,
                    "fallback_used": fallback_used,
                    "duration_ms": round(duration_ms, 1),
                    "usage": usage,
                },
            )
            yield make_trace_event(
                run_id,
                "validation.started",
                stage="validation",
                title="检查回答格式",
            )
            yield make_trace_event(
                run_id,
                "validation.completed",
                stage="validation",
                title="回答可用",
                message="Assistant response is non-empty.",
                metadata={"response_chars": len(answer)},
            )
            run_status = "SUCCESS"
            try:
                if not getattr(getattr(self.orchestrator, "ai_provider", None), "records_usage", False):
                    await self.ai_repo.record_invocation(
                        task=f"assistant_{req.action}",
                        provider=final_provider,
                        model=final_model,
                        fallback_used=fallback_used,
                        started_at=started_at,
                        duration_ms=duration_ms,
                        input_tokens=_usage_count(usage, "prompt_tokens", None),
                        output_tokens=_usage_count(usage, "completion_tokens", None),
                        prompt_version="v2.0",
                        status="SUCCESS",
                    )
            except Exception as error:
                logger.warning("AI invocation recording failed error_type=%s", type(error).__name__)
            yield make_trace_event(
                run_id,
                "run.completed",
                stage="run",
                title="AI 分析完成",
                metadata={
                    "provider": final_provider,
                    "model": final_model,
                    "fallback_used": fallback_used,
                    "duration_ms": round(duration_ms, 1),
                },
            )
        except (asyncio.CancelledError, GeneratorExit):
            run_status = "CANCELLED"
            raise
        except Exception as error:
            error_text = str(error).lower()
            if "authentication" in error_text or "api key" in error_text:
                safe_error = "authentication_error"
            elif "rate_limit" in error_text or "429" in error_text:
                safe_error = "rate_limited"
            elif "timeout" in error_text:
                safe_error = "timeout"
            elif "connection" in error_text or "network" in error_text:
                safe_error = "connection_error"
            elif "empty_model_response" in error_text:
                safe_error = "empty_response"
            logger.warning(
                "AI run failed run_id=%s provider=%s model=%s feature=qa_assistant error_type=%s",
                run_id,
                final_provider,
                final_model,
                type(error).__name__,
            )
            try:
                if not getattr(getattr(self.orchestrator, "ai_provider", None), "records_usage", False):
                    await self.ai_repo.record_invocation(
                        task=f"assistant_{req.action}",
                        provider=final_provider,
                        model=final_model,
                        fallback_used=fallback_used,
                        started_at=started_at,
                        duration_ms=(time.perf_counter() - started) * 1000,
                        input_tokens=_usage_count(usage, "prompt_tokens", None),
                        output_tokens=_usage_count(usage, "completion_tokens", None),
                        prompt_version="v2.0",
                        status="FAILED",
                        error_type=safe_error,
                    )
            except Exception as telemetry_error:
                logger.warning("AI invocation recording failed error_type=%s", type(telemetry_error).__name__)
            yield make_trace_event(
                run_id,
                "run.failed",
                stage="run",
                title="AI Provider 不可用",
                message=safe_error,
                metadata={"provider": final_provider, "model": final_model, "failure_reason": safe_error},
            )
        finally:
            logger.info(
                "AI run run_id=%s provider=%s model=%s feature=qa_assistant duration_ms=%.1f status=%s fallback_used=%s tool_count=0",
                run_id,
                final_provider,
                final_model,
                (time.perf_counter() - started) * 1000,
                run_status,
                fallback_used,
            )


def _usage_count(usage: dict[str, int | float | None], key: str, fallback: int | None) -> int | None:
    value = usage.get(key)
    return int(value) if isinstance(value, (int, float)) and value >= 0 else fallback
