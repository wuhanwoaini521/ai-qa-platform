from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator
from uuid import uuid4

from project_model.models import QAChatRequest, QAChatResponse
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

    async def handle_request(self, req: QAChatRequest) -> QAChatResponse:
        action = req.action
        ctx = req.context

        val_issues = ""
        if ctx.latest_validation and ctx.latest_validation.issues:
            val_issues = "\n".join(f"- Line {i.line}: {i.message}" for i in ctx.latest_validation.issues[:5])

        start = time.perf_counter()
        started_at = utc_now()

        res = await self.orchestrator.assist_code_chat(
            action=action,
            message=req.message,
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
        await self.ai_repo.record_invocation(
            task=f"assistant_{action}",
            provider=invocation["provider"],
            model=invocation["model"],
            fallback_used=invocation["fallback_used"],
            started_at=started_at,
            duration_ms=duration_ms,
            input_tokens=150,
            output_tokens=180,
            prompt_version="v1.0",
        )

        # Fallback formatting for specific quick actions if LLM returned basic reply
        suggested_code = res.suggested_code
        target_file = res.target_file

        if action == "generate_draft" and not suggested_code:
            title = ctx.test_case_title or ctx.requirement_title or "sample_flow"
            slug = title.lower().replace(" ", "_").replace("-", "_")[:35].strip("_")
            suggested_code = f'''import pytest
from playwright.sync_api import Page, expect

@pytest.mark.ui
def test_{slug}(page: Page):
    """
    Generated from QA Assistant
    Target: {title}
    """
    page.goto("/")
    # Automated interaction steps
    expect(page).to_have_title(r".*")
'''
            target_file = f"tests/test_{slug}.py"

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
            prompt = "\n".join(
                [
                    f"Action: {req.action}",
                    f"User request: {req.message or f'Please help with {req.action}.'}",
                    f"Project: {ctx.project_name or ctx.project_id}",
                    f"Requirement: {ctx.requirement_title or 'None'}",
                    f"Test case: {ctx.test_case_title or 'None'}",
                    f"Current file: {ctx.current_file or 'None'}",
                    "Selected code:",
                    ctx.selected_code or "None",
                    "Validation issues:",
                    validation_issues or "None",
                    "Relevant diff:",
                    ctx.git_diff or "None",
                    "Respond with a concise, user-facing Markdown answer. For generated code, use a fenced code block. "
                    "Do not reveal private chain-of-thought or hidden reasoning; provide conclusions and verifiable evidence only.",
                ]
            )
            completion = AICompletionRequest(
                prompt=prompt,
                system_instruction=(
                    "You are a QA automation assistant. Explain what the evidence supports and give practical, "
                    "verifiable guidance. Never expose private chain-of-thought."
                ),
                temperature=0.2,
                max_tokens=2000,
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

            if req.action == "generate_draft" and not re.search(r"```", answer):
                title = ctx.test_case_title or ctx.requirement_title or "sample_flow"
                slug = re.sub(r"[^a-zA-Z0-9_]+", "_", title.lower()).strip("_")[:35] or "sample_flow"
                sample = (
                    "\n\n```python\n"
                    "import pytest\nfrom playwright.sync_api import Page, expect\n\n"
                    f"@pytest.mark.ui\ndef test_{slug}(page: Page):\n"
                    f'    """Generated from QA Assistant: {title}."""\n'
                    '    page.goto("/")\n    expect(page).to_have_title(r".*")\n'
                    "```"
                )
                answer += sample
                yield make_trace_event(
                    run_id,
                    "model.delta",
                    stage="model",
                    title="生成测试草稿",
                    content=sample,
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
                await self.ai_repo.record_invocation(
                    task=f"assistant_{req.action}",
                    provider=final_provider,
                    model=final_model,
                    fallback_used=fallback_used,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    input_tokens=_usage_count(usage, "prompt_tokens", 150),
                    output_tokens=_usage_count(usage, "completion_tokens", 180),
                    prompt_version="v1.0",
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
                await self.ai_repo.record_invocation(
                    task=f"assistant_{req.action}",
                    provider=final_provider,
                    model=final_model,
                    fallback_used=fallback_used,
                    started_at=started_at,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    input_tokens=_usage_count(usage, "prompt_tokens", 150),
                    output_tokens=_usage_count(usage, "completion_tokens", None),
                    prompt_version="v1.0",
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
