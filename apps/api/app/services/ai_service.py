from __future__ import annotations

import time

from project_model.models import (
    AIProviderStatus,
    AIStatusResponse,
    AIUsageSummary,
    RequirementAnalysisDTO,
    TestCaseGenerationItem,
    TestDesignSuggestion,
)
from qa_core.ai.budget import AIBudgetGuard
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.persistence.models import utc_now
from app.repositories.ai_repo import AIRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository


class AIService:
    def __init__(
        self,
        ai_repo: AIRepository | None = None,
        requirement_repo: RequirementRepository | None = None,
        test_design_repo: TestDesignRepository | None = None,
        test_case_repo: TestCaseRepository | None = None,
        test_run_repo: TestRunRepository | None = None,
        project_repo: ProjectRepository | None = None,
        orchestrator: ProductionQAOrchestrator | None = None,
    ) -> None:
        self.ai_repo = ai_repo or AIRepository()
        self.requirement_repo = requirement_repo or RequirementRepository()
        self.test_design_repo = test_design_repo or TestDesignRepository()
        self.test_case_repo = test_case_repo or TestCaseRepository()
        self.test_run_repo = test_run_repo or TestRunRepository()
        self.project_repo = project_repo or ProjectRepository()
        self.orchestrator = orchestrator or ProductionQAOrchestrator()
        self.budget_guard = AIBudgetGuard()

    async def get_status(self) -> AIStatusResponse:
        provider = self.orchestrator.ai_provider
        health = await provider.check_health()

        # Map to AIProviderStatus safely, never exposing secrets
        status_val = AIProviderStatus.AVAILABLE
        if health.status.value == "DISABLED":
            status_val = AIProviderStatus.DISABLED
        elif health.status.value == "AUTH_ERROR":
            status_val = AIProviderStatus.AUTH_ERROR
        elif health.status.value == "RATE_LIMITED":
            status_val = AIProviderStatus.RATE_LIMITED
        elif health.status.value == "TIMEOUT":
            status_val = AIProviderStatus.TIMEOUT
        elif health.status.value == "UNAVAILABLE":
            status_val = AIProviderStatus.UNAVAILABLE

        return AIStatusResponse(
            provider=health.provider,
            status=status_val,
            message=health.message,
            model=health.model,
            base_url=health.base_url,
        )

    async def get_usage(self, limit: int = 50) -> AIUsageSummary:
        return await self.ai_repo.get_usage_summary(limit=limit)

    async def analyze_requirement(self, requirement_id: str) -> RequirementAnalysisDTO:
        req = await self.requirement_repo.get_by_id(requirement_id)
        if not req:
            raise ValueError(f"Requirement with ID {requirement_id} not found.")

        start = time.perf_counter()
        started_at = utc_now()
        analysis = await self.orchestrator.analyze_requirement(
            title=req.title,
            description=req.description,
            acceptance_criteria=req.acceptance_criteria,
            project_context=f"Project ID: {req.project_id}",
        )
        duration_ms = (time.perf_counter() - start) * 1000.0

        invocation = self.orchestrator.last_invocation_metadata()
        await self.ai_repo.record_invocation(
            task="requirement_analysis",
            provider=invocation["provider"],
            model=invocation["model"],
            fallback_used=invocation["fallback_used"],
            started_at=started_at,
            duration_ms=duration_ms,
            input_tokens=180,
            output_tokens=210,
            prompt_version="v1.0",
        )

        return RequirementAnalysisDTO(
            summary=analysis.summary,
            risks=analysis.risks,
            ambiguities=analysis.ambiguities,
            suggested_test_dimensions=analysis.suggested_test_dimensions,
        )

    async def generate_test_designs(self, requirement_id: str) -> list[TestDesignSuggestion]:
        req = await self.requirement_repo.get_by_id(requirement_id)
        if not req:
            raise ValueError(f"Requirement with ID {requirement_id} not found.")

        existing = await self.test_design_repo.list_by_requirement(requirement_id)
        existing_str = "\n".join(f"- {d.title} ({d.category})" for d in existing)

        start = time.perf_counter()
        started_at = utc_now()
        res = await self.orchestrator.generate_test_designs(
            title=req.title,
            description=req.description,
            acceptance_criteria=req.acceptance_criteria,
            existing_designs=existing_str,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0

        invocation = self.orchestrator.last_invocation_metadata()
        await self.ai_repo.record_invocation(
            task="test_design",
            provider=invocation["provider"],
            model=invocation["model"],
            fallback_used=invocation["fallback_used"],
            started_at=started_at,
            duration_ms=duration_ms,
            input_tokens=200,
            output_tokens=250,
            prompt_version="v1.0",
        )

        return [
            TestDesignSuggestion(
                title=s.title if hasattr(s, "title") else s["title"],
                category=s.category if hasattr(s, "category") else s.get("category", "FUNCTIONAL"),
                description=s.description if hasattr(s, "description") else s.get("description", ""),
                risk=s.risk if hasattr(s, "risk") else s.get("risk", "Medium"),
            )
            for s in res.suggestions
        ]

    async def generate_test_cases(self, test_design_id: str) -> list[TestCaseGenerationItem]:
        design = await self.test_design_repo.get_by_id(test_design_id)
        if not design:
            raise ValueError(f"Test Design with ID {test_design_id} not found.")

        req = await self.requirement_repo.get_by_id(design.requirement_id)
        req_title = req.title if req else "General Requirement"
        req_ac = req.acceptance_criteria if req else ""

        start = time.perf_counter()
        started_at = utc_now()
        res = await self.orchestrator.generate_test_cases(
            requirement_title=req_title,
            design_title=design.title,
            category=design.category,
            design_description=design.description,
            acceptance_criteria=req_ac,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0

        invocation = self.orchestrator.last_invocation_metadata()
        await self.ai_repo.record_invocation(
            task="test_case_generation",
            provider=invocation["provider"],
            model=invocation["model"],
            fallback_used=invocation["fallback_used"],
            started_at=started_at,
            duration_ms=duration_ms,
            input_tokens=250,
            output_tokens=320,
            prompt_version="v1.0",
        )

        return [
            TestCaseGenerationItem(
                title=c.title if hasattr(c, "title") else c["title"],
                preconditions=c.preconditions if hasattr(c, "preconditions") else c.get("preconditions", ""),
                steps=c.steps if hasattr(c, "steps") else c.get("steps", []),
                expected_result=c.expected_result if hasattr(c, "expected_result") else c.get("expected_result", ""),
                priority=c.priority if hasattr(c, "priority") else c.get("priority", "P1"),
                tags=c.tags if hasattr(c, "tags") else c.get("tags", []),
            )
            for c in res.test_cases
        ]
