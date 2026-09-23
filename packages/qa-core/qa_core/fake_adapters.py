from __future__ import annotations

import uuid

from qa_core.contracts import (
    AuthoringRequest,
    AuthoringResult,
    BrowserExplorer,
    ExecutionReport,
    ExecutionRequest,
    ExplorationSession,
    ExplorationStep,
    FailureAnalysis,
    FailureAnalyzer,
    FailureContext,
    HealingRequest,
    HealingResult,
    LocatorHealer,
    QAOrchestrator,
    TestAuthor,
    TestResultItem,
    TestRunner,
)


class FakeTestRunner(TestRunner):
    """Deterministic fake test runner for development and offline testing."""

    def __init__(self, simulate_failure: bool = False):
        self.simulate_failure = simulate_failure

    async def run_tests(self, request: ExecutionRequest) -> ExecutionReport:
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        if self.simulate_failure:
            return ExecutionReport(
                run_id=run_id,
                total=2,
                passed=1,
                failed=1,
                skipped=0,
                duration_ms=1450.0,
                results=[
                    TestResultItem(
                        test_id="test_login_success",
                        title="Verify user login succeeds with valid credentials",
                        status="PASSED",
                        duration_ms=620.0,
                    ),
                    TestResultItem(
                        test_id="test_checkout_flow",
                        title="Verify checkout submission with cart items",
                        status="FAILED",
                        duration_ms=830.0,
                        error_message="TimeoutError: Locator button#submit-order not found within 5000ms",
                        stack_trace="tests/flows/test_checkout.py:42 in test_checkout_flow",
                        artifacts=["screenshots/test_checkout_failed.png"],
                    ),
                ],
            )

        return ExecutionReport(
            run_id=run_id,
            total=2,
            passed=2,
            failed=0,
            skipped=0,
            duration_ms=1200.0,
            results=[
                TestResultItem(
                    test_id="test_login_success",
                    title="Verify user login succeeds with valid credentials",
                    status="PASSED",
                    duration_ms=580.0,
                ),
                TestResultItem(
                    test_id="test_checkout_flow",
                    title="Verify checkout submission with cart items",
                    status="PASSED",
                    duration_ms=620.0,
                ),
            ],
        )


class FakeFailureAnalyzer(FailureAnalyzer):
    """Deterministic fake failure analyzer returning structured failure taxonomy."""

    async def analyze_failure(self, context: FailureContext) -> FailureAnalysis:
        if "Locator" in context.error_message or "not found" in context.error_message:
            return FailureAnalysis(
                category="LOCATOR_CHANGED",
                root_cause=f"Element selector '{context.failing_locator or 'unknown'}' did not match DOM elements.",
                confidence=0.92,
                suggested_action="Apply locator self-healing or update selector to use semantic data-testid.",
                healing_possible=True,
            )
        return FailureAnalysis(
            category="ASSERTION_FAILURE",
            root_cause="Actual value did not match expected business condition.",
            confidence=0.85,
            suggested_action="Review test logic or backend response state.",
            healing_possible=False,
        )


class FakeTestAuthor(TestAuthor):
    """Deterministic fake test author generating structured Playwright test templates."""

    async def generate_test(self, request: AuthoringRequest) -> AuthoringResult:
        test_slug = request.requirement_title.lower().replace(" ", "_")[:30]
        code = f'''import pytest
from playwright.sync_api import Page, expect

@pytest.mark.ui
def test_{test_slug}(page: Page):
    """
    Requirement: {request.requirement_title}
    Description: {request.requirement_description}
    """
    page.goto("/")
    # Generated test steps based on acceptance criteria
    expect(page).to_have_title(r".*")
'''
        return AuthoringResult(
            suggested_file_path=f"tests/test_{test_slug}.py",
            generated_code=code,
            page_objects=[{"name": "MainPage", "path": "pages/main_page.py"}],
            explanation=f"Generated standard Playwright test scaffold for '{request.requirement_title}'.",
        )


class FakeLocatorHealer(LocatorHealer):
    """Deterministic fake locator healer."""

    async def heal_locator(self, request: HealingRequest) -> HealingResult:
        if "#" in request.old_locator or "." in request.old_locator:
            return HealingResult(
                success=True,
                new_locator='[data-testid="submit-btn"]',
                strategy_used="semantic-attribute-fallback",
                confidence=0.95,
            )
        return HealingResult(
            success=False,
            new_locator=None,
            strategy_used="none",
            confidence=0.0,
        )


class FakeBrowserExplorer(BrowserExplorer):
    """Deterministic fake browser explorer for AI sessions."""

    async def start_session(self, url: str) -> ExplorationSession:
        return ExplorationSession(
            session_id=f"session_{uuid.uuid4().hex[:8]}",
            target_url=url,
            steps=[
                ExplorationStep(action="NAVIGATE", target=url),
                ExplorationStep(action="ASSERT", target="body", value="Visible"),
            ],
            discovered_elements=["button#login", "input#username", "input#password"],
        )


class FakeQAOrchestrator(QAOrchestrator):
    """Coordinates fake runner and failure analyzer."""

    def __init__(self, runner: TestRunner | None = None, analyzer: FailureAnalyzer | None = None):
        self.runner = runner or FakeTestRunner(simulate_failure=True)
        self.analyzer = analyzer or FakeFailureAnalyzer()

    async def orchestrate_run(self, request: ExecutionRequest) -> tuple[ExecutionReport, list[FailureAnalysis]]:
        report = await self.runner.run_tests(request)
        analyses: list[FailureAnalysis] = []
        for res in report.results:
            if res.status == "FAILED":
                analysis = await self.analyzer.analyze_failure(
                    FailureContext(
                        test_name=res.title,
                        error_message=res.error_message or "",
                        stack_trace=res.stack_trace or "",
                    )
                )
                analyses.append(analysis)
        return report, analyses
