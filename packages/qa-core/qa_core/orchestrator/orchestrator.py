from __future__ import annotations

from pathlib import Path

from qa_core.ai.provider import AICompletionRequest, FakeAIProvider
from qa_core.author.grounder import KnowledgeGrounder, PytestCodeGenerator
from qa_core.author.models import AuthoringRequest, AuthoringResult
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.models import FailureArtifact
from qa_core.healing.healer import LocatorHealer
from qa_core.healing.models import LocatorRepairProposal
from qa_core.knowledge.loader import KnowledgeLoader


class ProductionQAOrchestrator:
    """Production orchestrator coordinating authoring, failure analysis, healing, and AI assistant routines."""

    def __init__(self, ai_provider=None) -> None:
        self.ai_provider = ai_provider or FakeAIProvider()

    def author_test(self, request: AuthoringRequest, workspace_dir: Path | str | None = None) -> AuthoringResult:
        knowledge = KnowledgeLoader.load_from_workspace(workspace_dir) if workspace_dir else None
        spec = KnowledgeGrounder.ground(request, knowledge)
        file_path, code = PytestCodeGenerator.generate_code(spec)

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

    async def assist_chat(self, prompt: str) -> str:
        res = await self.ai_provider.complete(AICompletionRequest(prompt=prompt))
        return res.content
