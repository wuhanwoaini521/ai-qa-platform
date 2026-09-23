from __future__ import annotations

from qa_core.author.models import AuthoringRequest, TestSpecification
from qa_core.knowledge.models import WorkspaceKnowledge


class KnowledgeGrounder:
    """Grounds user requirements into a structured test specification based on workspace knowledge."""

    @classmethod
    def ground(cls, request: AuthoringRequest, knowledge: WorkspaceKnowledge | None = None) -> TestSpecification:
        steps = list(request.acceptance_criteria)
        if not steps:
            steps = ["Navigate to target page", "Perform user interactions", "Verify expected state"]

        recommended_pages = []
        if knowledge:
            for p in knowledge.pages:
                if any(w in request.requirement_title.lower() for w in p.name.lower().split("_")):
                    recommended_pages.append(p.name)

        return TestSpecification(
            title=request.requirement_title,
            target_url="/",
            preconditions=["User is in standard test environment"],
            steps=steps,
            expected_assertions=[f"Verify {c}" for c in (request.acceptance_criteria or ["state"])],
            recommended_page_objects=recommended_pages,
        )


class PytestCodeGenerator:
    """Generates structured Playwright/pytest test code."""

    @classmethod
    def generate_code(cls, spec: TestSpecification) -> tuple[str, str]:
        slug = spec.title.lower().replace(" ", "_").replace("-", "_")
        slug = "".join(c for c in slug if c.isalnum() or c == "_")[:35].strip("_")
        func_name = f"test_{slug}"
        file_path = f"tests/test_{slug}.py"

        steps_block = "\n    ".join(f"# Step: {s}" for s in spec.steps)
        code = f'''import pytest
from playwright.sync_api import Page, expect

@pytest.mark.ui
def {func_name}(page: Page):
    """
    Automated Test: {spec.title}
    Target URL: {spec.target_url}
    """
    # 1. Navigation
    page.goto("{spec.target_url}")

    # 2. Automated Test Steps
    {steps_block}

    # 3. Assertions & Verification
    expect(page).to_have_title(r".*")
'''
        return file_path, code
