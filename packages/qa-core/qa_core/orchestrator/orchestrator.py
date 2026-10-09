from __future__ import annotations

import ast
import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import ValidationError

from qa_core.ai.budget import AIBudgetGuard
from qa_core.ai.models import (
    AICompletionRequest,
    AICompletionResponse,
    CodeAssistantResponse,
    FailureAnalysisResponse,
    LocatorSemanticReview,
    RequirementAnalysisResponse,
    TestCaseGenerationResponse,
    TestDesignGenerationResponse,
)
from qa_core.ai.provider import (
    AIProviderError,
    clean_json_text,
    empty_response_error,
    is_output_limit_finish_reason,
    output_limit_error,
    stream_provider_completion,
)
from qa_core.ai.registry import AIProviderRegistry
from qa_core.author.grounder import KnowledgeGrounder, PytestCodeGenerator
from qa_core.author.models import AuthoringRequest, AuthoringResult
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.models import FailureArtifact
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.healing.healer import LocatorHealer
from qa_core.healing.models import LocatorRepairProposal
from qa_core.knowledge.loader import KnowledgeLoader
from qa_core.prompts import (
    CODE_ASSISTANT_PROMPT,
    FAILURE_DIAGNOSIS_PROMPT,
    LOCATOR_REVIEW_PROMPT,
    REQUIREMENT_ANALYSIS_PROMPT,
    TEST_CASE_GENERATION_PROMPT,
    TEST_DESIGN_PROMPT,
)

FAILURE_DIAGNOSIS_TIMEOUT_SECONDS = 120.0


def _supports_native_streaming(provider) -> bool:
    for wrapper in ("inner", "primary"):
        nested = getattr(provider, wrapper, None)
        if nested is not None:
            return _supports_native_streaming(nested)
    return callable(getattr(provider, "stream_complete", None))


class ProductionQAOrchestrator:
    """Production orchestrator coordinating authoring, failure analysis, healing, and AI assistant routines."""

    def __init__(self, ai_provider=None, budget_guard: AIBudgetGuard | None = None) -> None:
        self.ai_provider = ai_provider or AIProviderRegistry.get_provider()
        #: Metadata of the most recent provider call, so callers can record which provider actually
        #: answered (the fallback wrapper serves a different provider than the configured one).
        self.last_completion: AICompletionResponse | None = None
        self.budget_guard = budget_guard or AIBudgetGuard()

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        """One bounded, redacted, schema-validated path for orchestration calls."""
        self.last_completion = None
        self.budget_guard.check_and_record_request()
        request = request.model_copy(update={"prompt": SensitiveRedactor.redact_text(request.prompt)})
        try:
            response = await self.ai_provider.complete(request)
        except AIProviderError as error:
            self.budget_guard.record_tokens(error.input_tokens, error.output_tokens)
            raise
        if request.response_schema:
            data = (
                response.structured_data
                or request.response_schema.model_validate_json(clean_json_text(response.content)).model_dump()
            )
            response = response.model_copy(
                update={"structured_data": request.response_schema.model_validate(data).model_dump()}
            )
        self.last_completion = response
        self.budget_guard.record_tokens(response.input_tokens, response.output_tokens)
        return response

    async def complete_streaming(
        self,
        request: AICompletionRequest,
        *,
        on_delta: Callable[[int, float], Awaitable[None]] | None = None,
        timeout_seconds: float = FAILURE_DIAGNOSIS_TIMEOUT_SECONDS,
    ) -> AICompletionResponse:
        """Collect a streamed completion while exposing safe progress to the caller."""
        self.last_completion = None
        self.budget_guard.check_and_record_request()
        request = request.model_copy(update={"prompt": SensitiveRedactor.redact_text(request.prompt)})
        started = time.perf_counter()
        content = ""
        provider = getattr(self.ai_provider, "provider_name", "unknown")
        model = getattr(self.ai_provider, "model", "")
        invocation_id = None
        input_tokens = output_tokens = None
        finish_reason = None
        fallback_used = False
        progress_callback = on_delta if _supports_native_streaming(self.ai_provider) else None
        stream = stream_provider_completion(self.ai_provider, request)
        timeout = asyncio.timeout(timeout_seconds)
        try:
            async with timeout:
                async for chunk in stream:
                    content += chunk.content_delta
                    provider = chunk.provider or provider
                    model = chunk.model or model
                    invocation_id = chunk.invocation_id or invocation_id
                    fallback_used = fallback_used or chunk.fallback_used
                    if chunk.usage:
                        input_tokens = chunk.usage.get("prompt_tokens", chunk.usage.get("input_tokens"))
                        output_tokens = chunk.usage.get("completion_tokens", chunk.usage.get("output_tokens"))
                    if chunk.finish_reason:
                        finish_reason = chunk.finish_reason
                    if progress_callback and chunk.content_delta:
                        await progress_callback(len(content), time.perf_counter() - started)
        except TimeoutError:
            if not timeout.expired():
                raise
            raise RuntimeError(f"AI completion timed out after {timeout_seconds:g} seconds.") from None
        except AIProviderError as error:
            if error.code == "output_limit":
                self.budget_guard.record_tokens(
                    error.input_tokens if error.input_tokens is not None else input_tokens,
                    error.output_tokens if error.output_tokens is not None else output_tokens,
                )
            raise
        finally:
            remaining = timeout_seconds - (time.perf_counter() - started)
            try:
                async with asyncio.timeout(max(remaining, 0)):
                    await stream.aclose()
            except TimeoutError:
                if time.perf_counter() - started < timeout_seconds:
                    raise
                raise RuntimeError(f"AI completion timed out after {timeout_seconds:g} seconds.") from None

        if is_output_limit_finish_reason(finish_reason):
            self.budget_guard.record_tokens(input_tokens, output_tokens)
            raise output_limit_error(
                max_tokens=request.max_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        if not content.strip():
            raise empty_response_error(streamed=True)
        structured_data = None
        if request.response_schema:
            try:
                structured_data = request.response_schema.model_validate_json(clean_json_text(content)).model_dump()
            except ValidationError:
                remaining = timeout_seconds - (time.perf_counter() - started)
                if remaining <= 0:
                    raise RuntimeError(f"AI completion timed out after {timeout_seconds:g} seconds.") from None
                self.budget_guard.record_tokens(input_tokens, output_tokens)
                repair_timeout = asyncio.timeout(remaining)
                try:
                    async with repair_timeout:
                        return await self.complete(request)
                except TimeoutError:
                    if not repair_timeout.expired():
                        raise
                    raise RuntimeError(f"AI completion timed out after {timeout_seconds:g} seconds.") from None
        response = AICompletionResponse(
            invocation_id=invocation_id,
            content=content,
            structured_data=structured_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            provider=provider,
            duration_ms=(time.perf_counter() - started) * 1000,
            fallback_used=fallback_used,
            prompt_version=request.prompt_version,
        )
        self.last_completion = response
        self.budget_guard.record_tokens(input_tokens, output_tokens)
        return response

    async def analyze_requirement(
        self,
        title: str,
        description: str = "",
        acceptance_criteria: str = "",
        project_context: str = "",
    ) -> RequirementAnalysisResponse:
        prompt_str = REQUIREMENT_ANALYSIS_PROMPT.format(
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            project_context=project_context,
        )
        req = AICompletionRequest(
            prompt=prompt_str,
            system_instruction=REQUIREMENT_ANALYSIS_PROMPT.system_instruction,
            prompt_id=REQUIREMENT_ANALYSIS_PROMPT.prompt_id,
            prompt_version=REQUIREMENT_ANALYSIS_PROMPT.version,
            response_schema=RequirementAnalysisResponse,
        )
        res = await self.complete(req)
        self.last_completion = res
        return RequirementAnalysisResponse.model_validate(res.structured_data)

    async def generate_test_designs(
        self,
        title: str,
        description: str = "",
        acceptance_criteria: str = "",
        existing_designs: str = "",
    ) -> TestDesignGenerationResponse:
        prompt_str = TEST_DESIGN_PROMPT.format(
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            existing_designs=existing_designs,
        )
        req = AICompletionRequest(
            prompt=prompt_str,
            system_instruction=TEST_DESIGN_PROMPT.system_instruction,
            prompt_id=TEST_DESIGN_PROMPT.prompt_id,
            prompt_version=TEST_DESIGN_PROMPT.version,
            response_schema=TestDesignGenerationResponse,
        )
        res = await self.complete(req)
        self.last_completion = res
        return TestDesignGenerationResponse.model_validate(res.structured_data)

    async def generate_test_cases(
        self,
        requirement_title: str,
        design_title: str,
        category: str = "FUNCTIONAL",
        design_description: str = "",
        acceptance_criteria: str = "",
    ) -> TestCaseGenerationResponse:
        prompt_str = TEST_CASE_GENERATION_PROMPT.format(
            requirement_title=requirement_title,
            design_title=design_title,
            category=category,
            design_description=design_description,
            acceptance_criteria=acceptance_criteria,
        )
        req = AICompletionRequest(
            prompt=prompt_str,
            system_instruction=TEST_CASE_GENERATION_PROMPT.system_instruction,
            prompt_id=TEST_CASE_GENERATION_PROMPT.prompt_id,
            prompt_version=TEST_CASE_GENERATION_PROMPT.version,
            response_schema=TestCaseGenerationResponse,
        )
        res = await self.complete(req)
        self.last_completion = res
        return TestCaseGenerationResponse.model_validate(res.structured_data)

    def author_test(self, request: AuthoringRequest, workspace_dir: Path | str | None = None) -> AuthoringResult:
        knowledge = KnowledgeLoader.load_from_workspace(workspace_dir) if workspace_dir else None
        spec = KnowledgeGrounder.ground(request, knowledge)
        file_path, code = PytestCodeGenerator.generate_code(spec)

        # Validate python syntax with AST
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Generated python code contains syntax error: {e}") from e

        return AuthoringResult(
            suggested_file_path=file_path,
            generated_code=code,
            test_specification=spec,
            explanation=f"Generated test scaffold grounded in {len(spec.steps)} acceptance steps.",
        )

    def diagnose_failure(
        self,
        error_message: str,
        stack_trace: str = "",
        test_nodeid: str = "",
        screenshot_path: str | None = None,
        trace_path: str | None = None,
    ) -> FailureArtifact:
        classification, suggested_action, failing_loc = FailureClassifier.classify(
            error_message=error_message, stack_trace=stack_trace
        )

        return FailureArtifact(
            test_id=test_nodeid.split("::")[-1] if test_nodeid else "unknown",
            nodeid=test_nodeid,
            exception_type=error_message.split(":")[0] if ":" in error_message else "TestFailure",
            error_message=error_message,
            stack_trace=stack_trace,
            screenshot_path=screenshot_path,
            trace_path=trace_path,
            failing_locator=failing_loc,
            classification=classification,
            suggested_action=suggested_action,
        )

    async def diagnose_failure_ai(
        self,
        error_message: str,
        stack_trace: str = "",
        test_nodeid: str = "",
        failing_locator: str | None = None,
        historical_context: str = "No prior executions recorded.",
        on_progress: Callable[[int], Awaitable[None]] | None = None,
        response_language: str = "en",
    ) -> FailureAnalysisResponse:
        language_instruction = (
            "Write every narrative field in Simplified Chinese. Preserve code, selectors, test paths, exception names, and identifiers exactly."
            if response_language.lower().startswith("zh")
            else "Write every narrative field in English. Preserve code, selectors, test paths, exception names, and identifiers exactly."
        )
        prompt_str = FAILURE_DIAGNOSIS_PROMPT.format(
            nodeid=test_nodeid,
            error_message=error_message,
            stack_trace=stack_trace,
            failing_locator=failing_locator or "None",
            historical_context=historical_context,
        )
        req = AICompletionRequest(
            prompt=prompt_str,
            system_instruction=f"{FAILURE_DIAGNOSIS_PROMPT.system_instruction} {language_instruction}",
            prompt_id=FAILURE_DIAGNOSIS_PROMPT.prompt_id,
            prompt_version=FAILURE_DIAGNOSIS_PROMPT.version,
            response_schema=FailureAnalysisResponse,
            max_tokens=5000,
            max_retries=0,
            timeout_seconds=20,
        )
        if on_progress is not None:
            res = await self.complete_streaming(req, on_delta=on_progress)
        else:
            timeout = asyncio.timeout(FAILURE_DIAGNOSIS_TIMEOUT_SECONDS)
            try:
                async with timeout:
                    res = await self.complete(req)
            except TimeoutError:
                if not timeout.expired():
                    raise
                raise RuntimeError(
                    f"AI diagnosis timed out after {FAILURE_DIAGNOSIS_TIMEOUT_SECONDS:g} seconds."
                ) from None
        self.last_completion = res
        analysis = FailureAnalysisResponse.model_validate(res.structured_data)
        return analysis.model_copy(
            update={"provider": res.provider, "fallback_used": res.fallback_used or res.provider == "fake"}
        )

    def propose_locator_repair(
        self,
        failing_locator: str,
        dom_snapshot: str = "",
        error_message: str = "",
        file_path: str | None = None,
    ) -> LocatorRepairProposal:
        return LocatorHealer.generate_repair_proposal(
            old_locator=failing_locator,
            dom_snapshot=dom_snapshot,
            error_message=error_message,
            file_path=file_path,
        )

    async def review_locator_candidate(
        self,
        old_locator: str,
        proposed_locator: str,
        strategy: str = "semantic",
        dom_snippet: str = "",
        error_message: str = "",
    ) -> LocatorSemanticReview:
        prompt_str = LOCATOR_REVIEW_PROMPT.format(
            old_locator=old_locator,
            proposed_locator=proposed_locator,
            strategy=strategy,
            dom_snippet=dom_snippet or "DOM snippet not available",
            error_message=error_message,
        )
        req = AICompletionRequest(
            prompt=prompt_str,
            system_instruction=LOCATOR_REVIEW_PROMPT.system_instruction,
            prompt_id=LOCATOR_REVIEW_PROMPT.prompt_id,
            prompt_version=LOCATOR_REVIEW_PROMPT.version,
            response_schema=LocatorSemanticReview,
        )
        res = await self.complete(req)
        self.last_completion = res
        return LocatorSemanticReview.model_validate(res.structured_data)

    def last_invocation_metadata(self) -> dict:
        """Provider, model and fallback status of the most recent provider response."""
        completion = self.last_completion
        if completion is None:
            return {
                "provider": getattr(self.ai_provider, "provider_name", "unknown"),
                "model": "unresolved",
                "fallback_used": False,
                "input_tokens": None,
                "output_tokens": None,
                "prompt_version": None,
                "retry_count": 0,
            }
        return {
            "provider": completion.provider,
            "model": completion.model,
            "fallback_used": completion.fallback_used or completion.provider == "fake",
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
            "prompt_version": completion.prompt_version,
            "retry_count": completion.retry_count,
        }

    async def assist_code_chat(
        self,
        action: str,
        message: str = "",
        current_file: str | None = None,
        selected_code: str | None = None,
        project_name: str = "",
        requirement_title: str | None = None,
        test_case_title: str | None = None,
        validation_issues: str = "",
        git_diff: str = "",
    ) -> CodeAssistantResponse:
        prompt_str = CODE_ASSISTANT_PROMPT.format(
            action=action,
            message=message or f"Perform {action}",
            current_file=current_file or "None",
            selected_code=selected_code or "None",
            project_name=project_name,
            requirement_title=requirement_title or "None",
            test_case_title=test_case_title or "None",
            validation_issues=validation_issues or "None",
            git_diff=git_diff or "None",
        )
        req = AICompletionRequest(
            prompt=prompt_str,
            system_instruction=CODE_ASSISTANT_PROMPT.system_instruction,
            prompt_id=CODE_ASSISTANT_PROMPT.prompt_id,
            prompt_version=CODE_ASSISTANT_PROMPT.version,
            response_schema=CodeAssistantResponse,
        )
        res = await self.complete(req)
        self.last_completion = res
        return CodeAssistantResponse.model_validate(res.structured_data).model_copy(
            update={
                "provider": res.provider,
                "model": res.model,
                "fallback_used": res.fallback_used or res.provider == "fake",
            }
        )

    async def assist_chat(self, prompt: str) -> str:
        from qa_core.prompts import CHAT_PROMPT

        res = await self.complete(
            AICompletionRequest(
                prompt=CHAT_PROMPT.format(message=prompt),
                system_instruction=CHAT_PROMPT.system_instruction,
                prompt_id=CHAT_PROMPT.prompt_id,
                prompt_version=CHAT_PROMPT.version,
            )
        )
        self.last_completion = res
        return res.content
