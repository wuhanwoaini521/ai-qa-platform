from pathlib import Path

import pytest
from qa_core.author.grounder import KnowledgeGrounder, PytestCodeGenerator
from qa_core.author.models import AuthoringRequest
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.models import FailureCategory
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.healing.healer import LocatorHealer
from qa_core.knowledge.loader import KnowledgeLoader
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator


def test_sensitive_redactor():
    text = "User login with password='secretPassword123' and api_key: 'sk-983489123847923847293847' bearer abc.xyz"
    redacted = SensitiveRedactor.redact_text(text)
    assert "secretPassword123" not in redacted
    assert "sk-983489123847923847293847" not in redacted
    assert "***REDACTED***" in redacted


def test_failure_classifier():
    msg = "TimeoutError: Locator('button#submit') not found within 5000ms"
    category, reason, loc = FailureClassifier.classify(msg)
    assert category == FailureCategory.LOCATOR_CHANGED
    assert loc == "button#submit"

    assert_msg = "AssertionError: Expected title to be 'Dashboard' but got 'Login'"
    cat2, _, _ = FailureClassifier.classify(assert_msg)
    assert cat2 == FailureCategory.ASSERTION_FAILURE


def test_locator_healer_proposal():
    proposal = LocatorHealer.generate_repair_proposal(
        old_locator="button#submit-btn",
        dom_snapshot="<button data-testid='submit-btn'>Submit</button>",
        error_message="element not found",
        file_path="pages/login_page.py",
    )
    assert proposal.old_locator == "button#submit-btn"
    assert proposal.proposed_locator == '[data-testid="btn"]' or "testid" in proposal.proposed_locator
    assert proposal.confidence >= 0.8
    assert proposal.applied is False


def test_knowledge_loader_and_authoring(tmp_path: Path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "auth.md").write_text("# Login Rules\n- `username`: `input#user`\n", encoding="utf-8")

    knowledge = KnowledgeLoader.load_from_workspace(tmp_path)
    assert len(knowledge.pages) == 1
    assert "username" in knowledge.pages[0].locators

    req = AuthoringRequest(
        requirement_title="User Password Reset",
        requirement_description="Allows resetting password via link",
        acceptance_criteria=["User enters email", "Reset link is sent"],
    )
    spec = KnowledgeGrounder.ground(req, knowledge)
    file_path, code = PytestCodeGenerator.generate_code(spec)
    assert "test_user_password_reset.py" in file_path
    assert "def test_user_password_reset" in code


@pytest.mark.asyncio
async def test_production_orchestrator():
    orchestrator = ProductionQAOrchestrator()
    diag = orchestrator.diagnose_failure(
        error_message="TimeoutError: Locator('input.search-bar') not found",
        test_nodeid="tests/test_search.py::test_search_flow",
    )
    assert diag.classification == FailureCategory.LOCATOR_CHANGED
    assert diag.failing_locator == "input.search-bar"

    response = await orchestrator.assist_chat("Explain this test")
    assert len(response) > 0
