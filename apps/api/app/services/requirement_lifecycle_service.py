"""Structured requirement workflow on the existing governed AI and decision runtimes."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from uuid import uuid4

from project_model.lifecycle import (
    AnalysisRecord,
    AnalysisStage,
    ModernTestModel,
    RequirementAnalysis,
    RequirementDocument,
    TestOracle,
)
from project_model.models import DecisionOption, DecisionRequest, TestCaseCreate, TestDesignCreate
from pydantic import ValidationError
from qa_core.ai.models import AICompletionRequest
from qa_core.ai.trace import make_trace_event
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator
from qa_core.prompts import REQUIREMENT_LIFECYCLE_PROMPT
from sqlalchemy import or_, select, update

from app.persistence.database import get_session
from app.persistence.models import RequirementORM, TestCaseORM, TestDesignORM, utc_now
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.services.decision_service import DecisionService
from app.services.lifecycle_validation import input_hash, validate_requirement_replacement
from app.services.test_case_service import TestCaseService
from app.services.test_design_service import TestDesignService


class RequirementAnalysisBusy(ValueError):
    pass


class RequirementLifecycleService:
    @staticmethod
    async def recover_interrupted():
        async with get_session() as session:
            rows = (await session.scalars(select(RequirementORM).where(RequirementORM.qa_model.is_not(None)))).all()
            for row in rows:
                raw = row.qa_model or {}
                if raw.get("history") and raw["history"][-1].get("status") == "RUNNING":
                    changed = {
                        **raw,
                        "history": [
                            *raw["history"][:-1],
                            {
                                **raw["history"][-1],
                                "status": "FAILED",
                                "error": "API restarted before requirement analysis completed",
                                "finished_at": utc_now().isoformat(),
                            },
                        ],
                    }
                    row.qa_model = changed
            await session.commit()

    def __init__(self, orchestrator=None, decisions=None):
        self.orchestrator = orchestrator or ProductionQAOrchestrator()
        self.decisions = decisions or DecisionService()

    async def _load(self, requirement_id):
        async with get_session() as session:
            row = await session.get(RequirementORM, requirement_id)
            if not row:
                raise ValueError("Requirement not found")
            raw = row.qa_model or {}
            document = RequirementDocument.model_validate(raw)
            if not document.criteria:
                from project_model.lifecycle import AcceptanceCriterion

                document.criteria = [
                    AcceptanceCriterion(id=f"AC-{number:03}", description=line.strip())
                    for number, line in enumerate(row.acceptance_criteria.splitlines(), 1)
                    if line.strip()
                ][:30]
            return row.title, row.description, row.project_id, document, raw

    async def _store(self, requirement_id, document, *, expected=None, analysis_id=None):
        async with get_session() as session:
            row = await session.get(RequirementORM, requirement_id)
            if not row:
                raise ValueError("Requirement not found")
            if analysis_id:
                latest = (row.qa_model or {}).get("history", [])
                if not latest or latest[-1]["id"] != analysis_id or latest[-1]["status"] != "RUNNING":
                    raise ValueError("Requirement changed during analysis; result was not applied")
                saved = RequirementDocument.model_validate(row.qa_model)
                if latest[-1].get("input_hash") != input_hash(
                    row.title, row.description, row.acceptance_criteria, saved
                ):
                    raise ValueError("Requirement inputs changed during analysis; result was not applied")
            original = row.qa_model or {}
            if expected is not None and original != expected:
                raise RequirementAnalysisBusy("Requirement changed; reload before analyzing")
            if expected is not None and document.history[-1].input_hash != input_hash(
                row.title, row.description, row.acceptance_criteria, document
            ):
                raise RequirementAnalysisBusy("Requirement inputs changed; reload before analyzing")
            await validate_requirement_replacement(session, requirement_id, document)
            checked = RequirementDocument.model_validate(document.model_dump())
            result = await session.execute(
                update(RequirementORM)
                .where(
                    RequirementORM.id == requirement_id,
                    or_(RequirementORM.qa_model == original, RequirementORM.qa_model.is_(None))
                    if not original
                    else RequirementORM.qa_model == original,
                )
                .values(qa_model=SensitiveRedactor.redact_value(checked.model_dump(mode="json")), updated_at=utc_now())
            )
            if result.rowcount != 1:
                raise RequirementAnalysisBusy("Concurrent requirement update; result was not applied")
            await session.commit()

    async def stream(self, requirement_id):
        title, description, project_id, document, raw = await self._load(requirement_id)
        if document.history and document.history[-1].status == "RUNNING":
            if datetime.fromisoformat(document.history[-1].started_at) > utc_now() - timedelta(minutes=10):
                raise RequirementAnalysisBusy("Requirement analysis is already running")
        record = AnalysisRecord(id=uuid4().hex, status="RUNNING", started_at=utc_now().isoformat())
        async with get_session() as session:
            row = await session.get(RequirementORM, requirement_id)
            record.input_hash = input_hash(title, description, row.acceptance_criteria, document)
        document.history = [*document.history[-9:], record]
        await self._store(requirement_id, document, expected=raw)
        active_stage = "context"

        async def stage(key, title, status, message="", source="deterministic", duration_ms=0):
            nonlocal active_stage
            active_stage = key
            saved = AnalysisStage(
                id=key,
                title=title,
                status={"RUNNING": "running", "COMPLETED": "passed", "FAILED": "failed", "SKIPPED": "skipped"}[status],
                summary=SensitiveRedactor.redact_text(message),
                source=source,
                duration_ms=duration_ms,
                at=utc_now().isoformat(),
            )
            record.stages = [item for item in record.stages if item.id != key] + [saved]
            await self._store(requirement_id, document, analysis_id=record.id)
            return make_trace_event(
                record.id,
                "workflow.step",
                stage=key,
                title=title,
                status=status,
                message=saved.summary,
                duration_ms=duration_ms,
                step_id=f"{record.id}:{key}",
                metadata={"requirement_id": requirement_id, "project_id": project_id, "source": source},
            )

        try:
            yield await stage(
                "context",
                "读取需求与验收标准",
                "COMPLETED",
                f"读取 {len(document.criteria)} 条验收标准、{len(document.rules)} 条业务规则",
            )
            if not document.criteria:
                raise ValueError("Add explicit acceptance criteria before analyzing")
            provider = getattr(self.orchestrator.ai_provider, "primary", self.orchestrator.ai_provider)
            record.provider, record.model = (
                getattr(provider, "provider_name", "unknown"),
                getattr(provider, "model", ""),
            )
            yield await stage("semantic", "AI 语义与风险分析", "RUNNING", source=record.provider)
            record.prompt_version = REQUIREMENT_LIFECYCLE_PROMPT.version
            if record.provider == "fake":
                record.status = "FALLBACK"
                raise ValueError(
                    "Fake AI is configured; reference material cannot be presented as real analysis. Configure a real provider and retry."
                )
            started = time.perf_counter()
            payload = {
                "title": title,
                "description": description[:5000],
                "model": document.model_dump(exclude={"history"}, mode="json"),
            }
            response = await self.orchestrator.complete(
                AICompletionRequest(
                    prompt=REQUIREMENT_LIFECYCLE_PROMPT.format(requirement=json.dumps(payload, ensure_ascii=False)),
                    system_instruction=REQUIREMENT_LIFECYCLE_PROMPT.system_instruction,
                    prompt_id=REQUIREMENT_LIFECYCLE_PROMPT.prompt_id,
                    prompt_version=REQUIREMENT_LIFECYCLE_PROMPT.version,
                    response_schema=RequirementAnalysis,
                    max_tokens=4500,
                    run_id=record.id,
                )
            )
            record.provider, record.model = response.provider, response.model
            record.prompt_version = REQUIREMENT_LIFECYCLE_PROMPT.version
            if response.provider == "fake" or response.fallback_used:
                record.status = "FALLBACK"
                raise ValueError("AI unavailable: simulated fallback is not an analyzed requirement")
            analysis = RequirementAnalysis.model_validate(response.structured_data)
            updated = document.model_copy(deep=True, update={"analysis": analysis})
            RequirementDocument.model_validate(updated.model_dump())
            async with get_session() as session:
                await validate_requirement_replacement(session, requirement_id, updated)
            yield await stage(
                "semantic",
                "AI 语义与风险分析",
                "COMPLETED",
                f"识别 {len(analysis.risks)} 项风险、{len(analysis.ambiguities)} 项歧义与 {len(analysis.scenarios)} 个场景",
                response.provider,
                (time.perf_counter() - started) * 1000,
            )
            yield await stage("decision", "Jev 聚焦优先级决策", "RUNNING", source="jev")
            started = time.perf_counter()
            for name, candidates in (
                ("requirement_risk_priority", analysis.risks),
                ("requirement_scenario_priority", analysis.scenarios),
            ):
                result = await self.decisions.choose(
                    DecisionRequest(
                        name=name,
                        state={
                            "criteria": [item.model_dump() for item in document.criteria],
                            "risks": [item.model_dump() for item in analysis.risks],
                        },
                        options=[
                            DecisionOption(
                                key=item.id,
                                description=(
                                    getattr(item, "intent", None) or getattr(item, "impact", "") or item.title
                                )[:1000],
                            )
                            for item in candidates[:12]
                        ],
                        instructions="Choose the most important candidate to validate first. Consider purchase-flow criticality, explicit risk/AC references and automation effort. Select only a supplied ID; abstain when evidence is insufficient.",
                    ),
                    run_id=record.id,
                    allow_missing_confidence=True,
                )
                decision = result.model_dump(mode="json")
                decision["name"] = name
                record.decisions.append(decision)
                if not result.fallback_used and result.choice in {item.id for item in candidates}:
                    candidates.sort(key=lambda item: item.id != result.choice)
                    if name.endswith("scenario_priority"):
                        candidates[0].priority = "P0"
                        candidates[0].rationale = f"Jev 首选 {result.choice}；依据已关联风险与验收标准。"
                else:
                    candidates.sort(
                        key=lambda item: (
                            {"High": 0, "Medium": 1, "Low": 2}.get(getattr(item, "severity", "Medium"), 1),
                            item.id,
                        )
                    )
            remote = all(not item["fallback_used"] and item["provider"] == "jev" for item in record.decisions)
            yield await stage(
                "decision",
                "Jev 聚焦优先级决策",
                "COMPLETED" if remote else "SKIPPED",
                "Jev 已选择优先风险与优先场景" if remote else "Jev 不可用或弃权；保留本地明确排序，未伪造 Jev 成功",
                "jev" if remote else "local_strategy",
                (time.perf_counter() - started) * 1000,
            )
            document.analysis = analysis
            record.analysis_snapshot = analysis.model_copy(deep=True)
            record.status = "SUCCESS"
            record.finished_at = utc_now().isoformat()
            yield await stage(
                "coverage", "构建可追溯测试模型", "COMPLETED", "覆盖引用已校验；覆盖率由实际实体与运行记录计算"
            )
            yield make_trace_event(
                record.id,
                "run.completed",
                stage="completed",
                title="需求分析完成",
                metadata={
                    "requirement_id": requirement_id,
                    "provider": record.provider,
                    "model": record.model,
                    "jev_connected": remote,
                },
            )
        except (asyncio.CancelledError, GeneratorExit):
            record.status, record.error, record.finished_at = (
                "FAILED",
                "Analysis cancelled before completion",
                utc_now().isoformat(),
            )
            try:
                await asyncio.shield(self._store(requirement_id, document, analysis_id=record.id))
            except ValueError:
                await asyncio.shield(self._finish_failed(requirement_id, record))
            raise
        except Exception as error:
            record.status = "FALLBACK" if record.status == "FALLBACK" else "FAILED"
            record.error_code = (
                "INVALID_STRUCTURED_OUTPUT" if isinstance(error, ValidationError) else type(error).__name__.upper()
            )
            record.error = SensitiveRedactor.redact_text(str(error))[:1000]
            record.finished_at = utc_now().isoformat()
            try:
                summary = (
                    "AI 返回的内容未通过 RequirementAnalysis JSON Schema 校验；Jev 尚未运行，分析结果未应用。"
                    if record.error_code == "INVALID_STRUCTURED_OUTPUT"
                    else record.error
                )
                yield await stage(
                    active_stage,
                    "分析未完成",
                    "FAILED",
                    summary,
                    source=record.provider
                    if active_stage == "semantic"
                    else "jev"
                    if active_stage == "decision"
                    else "deterministic",
                )
            except (ValueError, RequirementAnalysisBusy):
                await self._finish_failed(requirement_id, record)
            yield make_trace_event(
                record.id,
                "run.failed",
                stage="failed",
                title="需求分析未完成",
                message=record.error,
                metadata={
                    "requirement_id": requirement_id,
                    "fallback": record.status == "FALLBACK",
                    "error_code": record.error_code,
                },
            )

    async def _finish_failed(self, requirement_id, record):
        """Keep current content; only close this workflow's still-owned invocation."""
        async with get_session() as session:
            row = await session.get(RequirementORM, requirement_id)
            history = (row.qa_model or {}).get("history", []) if row else []
            if not history or history[-1]["id"] != record.id or history[-1]["status"] != "RUNNING":
                return
            original = row.qa_model
            updated = {
                **original,
                "history": [
                    *history[:-1],
                    {
                        **history[-1],
                        "status": record.status,
                        "error": record.error,
                        "error_code": record.error_code,
                        "finished_at": record.finished_at,
                    },
                ],
            }
            await session.execute(
                update(RequirementORM)
                .where(RequirementORM.id == requirement_id, RequirementORM.qa_model == original)
                .values(qa_model=updated)
            )
            await session.commit()

    async def adopt_designs(self, requirement_id):
        _, _, _, document, _ = await self._load(requirement_id)
        if not document.analysis:
            raise ValueError("Analyze this requirement before creating designs")
        async with get_session() as session:
            repo = TestDesignRepository(session)
            existing = await repo.list_by_requirement(requirement_id)
            result = []
            for scenario in document.analysis.scenarios:
                found = next((item for item in existing if (item.scenario_model or {}).get("id") == scenario.id), None)
                if found:
                    found.scenario_model = scenario.model_dump(mode="json")
                    found.description, found.title = scenario.intent, scenario.title
                    item = TestDesignService(repo)._to_dto(found)
                else:
                    item = await TestDesignService(repo).create_test_design(
                        TestDesignCreate(
                            requirement_id=requirement_id,
                            title=scenario.title,
                            description=scenario.intent,
                            category="API"
                            if scenario.domain == "API"
                            else "NEGATIVE"
                            if scenario.path_type == "negative"
                            else "FUNCTIONAL",
                            risk="High" if scenario.priority == "P0" else "Medium",
                            scenario_model=scenario,
                            status="READY",
                        )
                    )
                result.append(item)
            await session.commit()
            return result

    async def adopt_case(self, design_id):
        async with get_session() as session:
            design = await session.get(TestDesignORM, design_id)
            if not design or not design.scenario_model:
                raise ValueError("Select a structured test design")
            requirement = await session.get(RequirementORM, design.requirement_id)
            existing = await session.scalar(select(TestCaseORM).where(TestCaseORM.test_design_id == design_id))
            if existing:
                return TestCaseService(TestCaseRepository(session))._to_dto(existing)
            from project_model.lifecycle import TestScenario

            scenario = TestScenario.model_validate(design.scenario_model)
            item = await TestCaseService(TestCaseRepository(session)).create_test_case(
                TestCaseCreate(
                    project_id=requirement.project_id,
                    requirement_id=requirement.id,
                    test_design_id=design_id,
                    title=scenario.title,
                    steps=scenario.actions,
                    expected_result="\n".join(scenario.expected_outcomes),
                    priority=scenario.priority,
                    test_model=ModernTestModel(
                        intent=scenario.intent,
                        scenario_id=scenario.id,
                        coverage=scenario.coverage,
                        path_type=scenario.path_type,
                        technique=scenario.technique,
                        oracles=[
                            TestOracle(
                                kind=scenario.domain, description=outcome, criterion_ids=scenario.coverage.criterion_ids
                            )
                            for outcome in scenario.expected_outcomes
                        ],
                        evidence=["Screenshot", "DOM", "Network"],
                        missing=["确认测试环境与输入数据"],
                    ),
                )
            )
            await session.commit()
            return item
