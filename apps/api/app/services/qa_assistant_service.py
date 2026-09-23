from __future__ import annotations

from project_model.models import QAChatRequest, QAChatResponse
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator


class QAAssistantService:
    def __init__(self, orchestrator: ProductionQAOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or ProductionQAOrchestrator()

    async def handle_request(self, req: QAChatRequest) -> QAChatResponse:
        action = req.action
        ctx = req.context

        if action == "explain":
            file_name = ctx.current_file or "the selected test"
            return QAChatResponse(
                response=f"This test in `{file_name}` automates the QA scenario for '{ctx.requirement_title or 'user requirement'}'. It initializes page objects, performs user interactions, and verifies DOM state expectations.",
                action_type="explain",
            )

        if action == "generate_draft":
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
    # Fill in automated verification steps
    expect(page).to_have_title(r".*")
'''
            return QAChatResponse(
                response=f"Generated standard Playwright test template for '{title}'.",
                suggested_code=suggested_code,
                target_file=f"tests/test_{slug}.py",
                action_type="generate_draft",
            )

        if action == "suggest_refactor":
            return QAChatResponse(
                response="Refactor suggestion: Extract hardcoded locators into a dedicated Page Object under `pages/` and wrap common multi-step sequences into `flows/`.",
                action_type="suggest_refactor",
            )

        if action == "analyze_error":
            validation = ctx.latest_validation
            if validation and validation.issues:
                err_msgs = "\n".join(f"- Line {i.line}: {i.message}" for i in validation.issues[:3])
                return QAChatResponse(
                    response=f"Found {len(validation.issues)} validation issues:\n{err_msgs}\n\nSuggested Fix: Check syntax and ensure imported fixtures exist in workspace.",
                    action_type="analyze_error",
                )
            return QAChatResponse(
                response="No syntax errors detected in workspace.",
                action_type="analyze_error",
            )

        # Default chat
        content = await self.orchestrator.assist_chat(req.message or "QA Assistant query")
        return QAChatResponse(
            response=f"QA Assistant: {content}",
            action_type="chat",
        )
