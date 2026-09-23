import pytest
from qa_core.contracts import (
    AuthoringRequest,
    ExecutionRequest,
    FailureContext,
    HealingRequest,
)
from qa_core.fake_adapters import (
    FakeBrowserExplorer,
    FakeFailureAnalyzer,
    FakeLocatorHealer,
    FakeQAOrchestrator,
    FakeTestAuthor,
    FakeTestRunner,
)


@pytest.mark.asyncio
async def test_fake_test_runner_success():
    runner = FakeTestRunner(simulate_failure=False)
    report = await runner.run_tests(ExecutionRequest(project_id="proj_1", workspace_path="/tmp"))
    assert report.total == 2
    assert report.passed == 2
    assert report.failed == 0


@pytest.mark.asyncio
async def test_fake_test_runner_failure():
    runner = FakeTestRunner(simulate_failure=True)
    report = await runner.run_tests(ExecutionRequest(project_id="proj_1", workspace_path="/tmp"))
    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1


@pytest.mark.asyncio
async def test_fake_failure_analyzer():
    analyzer = FakeFailureAnalyzer()
    analysis = await analyzer.analyze_failure(
        FailureContext(
            test_name="test_checkout",
            error_message="TimeoutError: Locator button#submit not found",
            stack_trace="",
            failing_locator="button#submit",
        )
    )
    assert analysis.category == "LOCATOR_CHANGED"
    assert analysis.healing_possible is True


@pytest.mark.asyncio
async def test_fake_test_author():
    author = FakeTestAuthor()
    result = await author.generate_test(
        AuthoringRequest(
            requirement_title="User Registration",
            requirement_description="User can register with email",
            acceptance_criteria=["Valid email registers successfully"],
        )
    )
    assert "test_user_registration.py" in result.suggested_file_path
    assert "playwright.sync_api" in result.generated_code


@pytest.mark.asyncio
async def test_fake_locator_healer():
    healer = FakeLocatorHealer()
    result = await healer.heal_locator(
        HealingRequest(
            old_locator="#login-btn",
            page_source_or_dom="<html></html>",
            target_description="Login button",
        )
    )
    assert result.success is True
    assert result.new_locator == '[data-testid="submit-btn"]'


@pytest.mark.asyncio
async def test_fake_browser_explorer():
    explorer = FakeBrowserExplorer()
    session = await explorer.start_session("https://example.com")
    assert session.target_url == "https://example.com"
    assert len(session.steps) > 0


@pytest.mark.asyncio
async def test_fake_qa_orchestrator():
    orchestrator = FakeQAOrchestrator()
    report, analyses = await orchestrator.orchestrate_run(ExecutionRequest(project_id="proj_1", workspace_path="/tmp"))
    assert report.failed == 1
    assert len(analyses) == 1
    assert analyses[0].category == "LOCATOR_CHANGED"
