from pathlib import Path

import pytest
from project_model.models import AIProviderSettingsUpdate, QAChatRequest
from pydantic import ValidationError
from qa_core.ai.provider import FallbackAIProvider
from qa_core.ai.registry import AIProviderRegistry
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
    assert proposal.proposed_locator in {'[data-testid="submit-btn"]', 'role=button[name="Submit"]'}
    assert proposal.confidence >= 0.8
    assert proposal.applied is False


def test_locator_healer_does_not_invent_candidates_without_dom_evidence():
    proposal = LocatorHealer.generate_repair_proposal(
        old_locator="button#missing-submit",
        dom_snapshot="<main><button>Continue</button></main>",
    )
    assert proposal.proposed_locator == "button#missing-submit"
    assert proposal.confidence == 0
    assert "No replacement is recommended" in proposal.reason

    ambiguous = LocatorHealer.generate_repair_proposal(
        old_locator="button#submit-btn",
        dom_snapshot='<button data-testid="submit-btn">Submit</button><button data-testid="submit-btn">Submit</button>',
    )
    assert ambiguous.confidence == 0


def test_locator_candidates_rank_semantic_unique_targets_first():
    from qa_core.healing.locator_intelligence import rank_locator_candidates

    ranked = rank_locator_candidates([
        {"kind": "css", "value": "button.primary"},
        {"kind": "role", "value": "button", "name": "Save", "exact": True},
        {"kind": "test_id", "value": "save", "nth": 1},
    ])
    assert [item["kind"] for item in ranked] == ["role", "test_id", "css"]


def test_ai_provider_registry_uses_runtime_settings():
    AIProviderRegistry.reset()
    try:
        AIProviderRegistry.configure_runtime({
            "provider": "openai-compatible",
            "api_key": "runtime-secret",
            "model": "runtime-model",
            "base_url": "https://ai.example/v1",
            "timeout": "12",
            "max_retries": "1",
        })
        provider = AIProviderRegistry.get_provider()
        assert isinstance(provider, FallbackAIProvider)
        assert provider.primary.api_key == "runtime-secret"
        assert provider.primary.model == "runtime-model"
        assert provider.primary.base_url == "https://ai.example/v1"
    finally:
        AIProviderRegistry.reset()


def test_provider_settings_and_qa_assistant_contracts_are_validated():
    settings = AIProviderSettingsUpdate.model_validate({
        "provider": "openai-compatible",
        "model": "gpt-test",
        "base_url": "https://ai.example/v1",
        "timeout": 15,
        "max_retries": 2,
    })
    assert settings.provider == "openai-compatible"

    with pytest.raises(ValidationError):
        QAChatRequest.model_validate({"message": "broken old shape", "project_id": "project-1"})


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
