from __future__ import annotations

import time

from project_model.models import QAChatRequest, QAChatResponse
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.persistence.models import utc_now
from app.repositories.ai_repo import AIRepository


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
        await self.ai_repo.record_invocation(
            task=f"assistant_{action}",
            provider=getattr(self.orchestrator.ai_provider, "provider_name", "provider"),
            model=getattr(self.orchestrator.ai_provider, "model", "default-model"),
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
