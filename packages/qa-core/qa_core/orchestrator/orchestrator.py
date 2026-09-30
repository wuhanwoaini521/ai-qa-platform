from __future__ import annotations

import ast
from pathlib import Path

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
from qa_core.ai.registry import AIProviderRegistry
from qa_core.author.grounder import KnowledgeGrounder, PytestCodeGenerator
from qa_core.author.models import AuthoringRequest, AuthoringResult
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.models import FailureArtifact, FailureCategory
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


class ProductionQAOrchestrator:
    """Production orchestrator coordinating authoring, failure analysis, healing, and AI assistant routines."""

    def __init__(self, ai_provider=None, budget_guard: AIBudgetGuard | None = None) -> None:
        self.ai_provider = ai_provider or AIProviderRegistry.get_provider()
        #: Metadata of the most recent provider call, so callers can record which provider actually
        #: answered (the fallback wrapper serves a different provider than the configured one).
        self.last_completion: AICompletionResponse | None = None
        self.budget_guard = budget_guard or AIBudgetGuard()

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
        )
        res = await self.ai_provider.complete(req)
        self.last_completion = res
        if res.structured_data:
            return RequirementAnalysisResponse.model_validate(res.structured_data)

        # Fallback analysis
        return RequirementAnalysisResponse(
            summary=f"Requirement analysis for '{title}'.",
            risks=["Potential edge cases in boundary conditions", "Asynchronous state transitions"],
            ambiguities=["Validation rules need explicit definition"],
            suggested_test_dimensions=["FUNCTIONAL", "BOUNDARY", "NEGATIVE", "API", "UI"],
        )

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
        )
        res = await self.ai_provider.complete(req)
        self.last_completion = res
        if res.structured_data:
            return TestDesignGenerationResponse.model_validate(res.structured_data)

        return TestDesignGenerationResponse(
            suggestions=[
                {
                    "title": f"Verify Functional Flow: {title}",
                    "category": "FUNCTIONAL",
                    "description": description,
                    "risk": "Low",
                },
                {
                    "title": f"Boundary Limits: {title}",
                    "category": "BOUNDARY",
                    "description": "Test input limits",
                    "risk": "Medium",
                },
                {
                    "title": f"Negative Error Handling: {title}",
                    "category": "NEGATIVE",
                    "description": "Test invalid payload",
                    "risk": "High",
                },
            ]
        )

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
        )
        res = await self.ai_provider.complete(req)
        self.last_completion = res
        if res.structured_data:
            return TestCaseGenerationResponse.model_validate(res.structured_data)

        return TestCaseGenerationResponse(
            test_cases=[
                {
                    "title": f"Verify {design_title} primary flow",
                    "preconditions": "Application is loaded",
                    "steps": ["Navigate to target", "Execute interaction", "Verify assertion"],
                    "expected_result": "Action succeeds and UI state matches expected result.",
                    "priority": "P1",
                    "tags": ["smoke", category.lower()],
                }
            ]
        )

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
    ) -> FailureAnalysisResponse:
        prompt_str = FAILURE_DIAGNOSIS_PROMPT.format(
            nodeid=test_nodeid,
            error_message=error_message,
            stack_trace=stack_trace,
            failing_locator=failing_locator or "None",
            historical_context=historical_context,
        )
        req = AICompletionRequest(
            prompt=prompt_str,
            system_instruction=FAILURE_DIAGNOSIS_PROMPT.system_instruction,
            prompt_id=FAILURE_DIAGNOSIS_PROMPT.prompt_id,
            prompt_version=FAILURE_DIAGNOSIS_PROMPT.version,
        )
        res = await self.ai_provider.complete(req)
        self.last_completion = res
        if res.structured_data:
            analysis = FailureAnalysisResponse.model_validate(res.structured_data)
            return analysis.model_copy(
                update={"provider": res.provider, "fallback_used": res.fallback_used}
            )

        # Deterministic fallback
        classification, suggested_action, _ = FailureClassifier.classify(error_message, stack_trace)
        return FailureAnalysisResponse(
            classification=classification.value if isinstance(classification, FailureCategory) else str(classification),
            root_cause=suggested_action,
            evidence=[error_message],
            hypotheses=["Element state or locator mismatch"],
            recommended_actions=[suggested_action],
            confidence=0.85,
            provider=res.provider,
            fallback_used=res.fallback_used,
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
        )
        res = await self.ai_provider.complete(req)
        self.last_completion = res
        if res.structured_data:
            return LocatorSemanticReview.model_validate(res.structured_data)

        return LocatorSemanticReview(
            is_semantically_equivalent=True,
            confidence=0.85,
            explanation=f"Candidate selector '{proposed_locator}' preserves target element intent.",
        )

    def last_invocation_metadata(self) -> dict:
        """Provider, model and fallback status of the most recent provider response."""
        completion = self.last_completion
        if completion is None:
            return {
                "provider": getattr(self.ai_provider, "provider_name", "unknown"),
                "model": "unresolved",
                "fallback_used": False,
            }
        return {
            "provider": completion.provider,
            "model": completion.model,
            "fallback_used": completion.fallback_used,
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
        )
        res = await self.ai_provider.complete(req)
        self.last_completion = res
        if res.structured_data:
            return CodeAssistantResponse.model_validate(res.structured_data)

        return CodeAssistantResponse(
            reply=res.content,
            suggested_code=None,
            target_file=None,
            action_type=action,
            suggestions=[],
        )

    async def assist_chat(self, prompt: str) -> str:
        res = await self.ai_provider.complete(AICompletionRequest(prompt=prompt))
        self.last_completion = res
        return res.content
