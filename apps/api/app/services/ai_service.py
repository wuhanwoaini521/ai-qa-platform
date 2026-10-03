from __future__ import annotations

import logging
import time
from datetime import datetime

from project_model.models import (
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
from app.services.ai_observability import log_ai_execution
from app.services.operation_trace import trace_progress

logger = logging.getLogger("app.ai")


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
        self.requirement_repo = requirement_repo
        self.test_design_repo = test_design_repo
        self.test_case_repo = test_case_repo
        self.test_run_repo = test_run_repo
        self.project_repo = project_repo
        self.orchestrator = orchestrator or ProductionQAOrchestrator()
        self.budget_guard = AIBudgetGuard()

    async def get_status(self) -> AIStatusResponse:
        from app.services.ai_settings_service import AISettingsService

        return await AISettingsService().get_status()

    async def get_usage(
        self, limit: int = 50, since: datetime | None = None, feature: str | None = None
    ) -> AIUsageSummary:
        return await self.ai_repo.get_usage_summary(limit=limit, since=since, feature=feature)

    async def analyze_requirement(self, requirement_id: str) -> RequirementAnalysisDTO:
        req = await self.requirement_repo.get_by_id(requirement_id)
        if not req:
            raise ValueError(f"Requirement with ID {requirement_id} not found.")

        await trace_progress("context.loaded", "需求与测试上下文已加载")
        await trace_progress("model.started", "调用 AI 模型")
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
        await trace_progress("model.completed", "模型调用完成", metadata=invocation, duration_ms=duration_ms)
        log_ai_execution(
            logger,
            feature="requirement_analysis",
            provider=invocation["provider"],
            model=invocation["model"],
            duration_ms=duration_ms,
            status="SUCCESS",
            fallback_used=invocation["fallback_used"],
        )
        if not getattr(getattr(self.orchestrator, "ai_provider", None), "records_usage", False):
            await self.ai_repo.record_invocation(
                task="requirement_analysis",
                provider=invocation["provider"],
                model=invocation["model"],
                fallback_used=invocation["fallback_used"],
                started_at=started_at,
                duration_ms=duration_ms,
                input_tokens=invocation.get("input_tokens"),
                output_tokens=invocation.get("output_tokens"),
                prompt_version=invocation.get("prompt_version"),
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

        await trace_progress("context.loaded", "需求与测试上下文已加载")
        await trace_progress("model.started", "调用 AI 模型")
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
        await trace_progress("model.completed", "模型调用完成", metadata=invocation, duration_ms=duration_ms)
        log_ai_execution(
            logger,
            feature="test_design",
            provider=invocation["provider"],
            model=invocation["model"],
            duration_ms=duration_ms,
            status="SUCCESS",
            fallback_used=invocation["fallback_used"],
        )
        if not getattr(getattr(self.orchestrator, "ai_provider", None), "records_usage", False):
            await self.ai_repo.record_invocation(
                task="test_design",
                provider=invocation["provider"],
                model=invocation["model"],
                fallback_used=invocation["fallback_used"],
                started_at=started_at,
                duration_ms=duration_ms,
                input_tokens=invocation.get("input_tokens"),
                output_tokens=invocation.get("output_tokens"),
                prompt_version=invocation.get("prompt_version"),
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

        await trace_progress("context.loaded", "需求与测试上下文已加载")
        await trace_progress("model.started", "调用 AI 模型")
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
        await trace_progress("model.completed", "模型调用完成", metadata=invocation, duration_ms=duration_ms)
        log_ai_execution(
            logger,
            feature="test_case_generation",
            provider=invocation["provider"],
            model=invocation["model"],
            duration_ms=duration_ms,
            status="SUCCESS",
            fallback_used=invocation["fallback_used"],
        )
        if not getattr(getattr(self.orchestrator, "ai_provider", None), "records_usage", False):
            await self.ai_repo.record_invocation(
                task="test_case_generation",
                provider=invocation["provider"],
                model=invocation["model"],
                fallback_used=invocation["fallback_used"],
                started_at=started_at,
                duration_ms=duration_ms,
                input_tokens=invocation.get("input_tokens"),
                output_tokens=invocation.get("output_tokens"),
                prompt_version=invocation.get("prompt_version"),
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
