"""Structured requirement workflow on the existing governed AI and decision runtimes."""

from __future__ import annotations

import asyncio
import copy
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
from qa_core.prompts import REQUIREMENT_LIFECYCLE_PROMPT

from app.persistence.models import utc_now
from app.ports.repository_scope import RepositoryScopeFactory
from app.services.ai_runtime import build_ai_orchestrator
from app.services.decision_service import DecisionService
from app.services.lifecycle_validation import input_hash, validate_case_model, validate_requirement_replacement
from app.services.test_case_service import TestCaseService
from app.services.test_design_service import TestDesignService

DEFAULT_REQUIREMENT_ANALYSIS_TIMEOUT_SECONDS = 45.0
MIN_REQUIREMENT_ANALYSIS_TIMEOUT_SECONDS = 120.0


class RequirementAnalysisBusy(ValueError):
    pass


def _discard_unknown_analysis_references(analysis: RequirementAnalysis, document: RequirementDocument) -> int:
    known = {
        "criterion_ids": {item.id for item in document.criteria},
        "rule_ids": {item.id for item in document.rules},
        "risk_ids": {item.id for item in analysis.risks},
        "flow_ids": {item.id for item in analysis.business_flow},
    }
    removed = 0

    def keep_known(target, field: str, allowed: set[str]) -> None:
        nonlocal removed
        values = getattr(target, field)
        valid = [value for value in values if value in allowed]
        removed += len(values) - len(valid)
        setattr(target, field, valid)

    flow_ids = known["flow_ids"]
    criterion_ids = known["criterion_ids"]
    for step in analysis.business_flow:
        keep_known(step, "next_ids", flow_ids)
        keep_known(step, "criterion_ids", criterion_ids)
    for risk in analysis.risks:
        keep_known(risk, "criterion_ids", criterion_ids)
    for scenario in analysis.scenarios:
        for field, allowed in known.items():
            keep_known(scenario.coverage, field, allowed)
    if removed:
        note = f"已忽略 {removed} 个指向不存在实体的 AI 引用；相关覆盖关系需人工复核。"
        analysis.coverage_gaps = [*analysis.coverage_gaps, note][:30]
    return removed


def _validate_analysis_payload(payload) -> RequirementAnalysis:
    value = copy.deepcopy(payload)
    ignored_fields = 0
    while True:
        try:
            analysis = RequirementAnalysis.model_validate(value)
            break
        except ValidationError as error:
            extra_errors = [item for item in error.errors() if item["type"] == "extra_forbidden"]
            if not extra_errors:
                raise
            for item in extra_errors:
                current = value
                for part in item["loc"][:-1]:
                    current = current[part]
                key = item["loc"][-1]
                if not isinstance(current, dict) or key not in current:
                    raise
                del current[key]
                ignored_fields += 1
    if ignored_fields:
        note = f"已忽略 AI 响应中的 {ignored_fields} 个非标准字段；生成内容需人工复核。"
        analysis.coverage_gaps = [*analysis.coverage_gaps, note][:30]
    return analysis


class RequirementLifecycleService:
    def __init__(self, repository_scope: RepositoryScopeFactory, orchestrator=None, decisions=None):
        self.repository_scope = repository_scope
        self.orchestrator = orchestrator or build_ai_orchestrator()
        self.decisions = decisions or DecisionService(repository_scope=repository_scope)

    async def recover_interrupted(self):
        async with self.repository_scope() as repositories:
            rows = await repositories.requirements.list_with_qa_model()
            for row in rows:
                raw = row["qa_model"] or {}
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
                    await repositories.requirements.update_qa_model(row["id"], changed)
            await repositories.commit()

    async def _load(self, requirement_id):
        async with self.repository_scope() as repositories:
            row = await repositories.requirements.get_by_id(requirement_id)
            if not row:
                raise ValueError("Requirement not found")
            project = await repositories.projects.get_by_id(row.project_id)
            cases = await repositories.test_cases.list_by_requirement(requirement_id, limit=20)
            raw = row.qa_model or {}
            document = RequirementDocument.model_validate(raw)
            if not document.criteria:
                from project_model.lifecycle import AcceptanceCriterion

                document.criteria = [
                    AcceptanceCriterion(id=f"AC-{number:03}", description=line.strip())
                    for number, line in enumerate(row.acceptance_criteria.splitlines(), 1)
                    if line.strip()
                ][:30]
            project_context = {"project_id": row.project_id, "name": project.name if project else row.project_id}
            existing_cases = [
                {
                    "id": case.id,
                    "title": case.title[:200],
                    "steps": (case.steps or [])[:8],
                    "expected_result": (case.expected_result or "")[:600],
                    "intent": str((case.test_model or {}).get("intent") or "")[:400],
                    "coverage": (case.test_model or {}).get("coverage", {}),
                }
                for case in cases
            ]
            return row.title, row.description, row.project_id, document, raw, project_context, existing_cases

    async def _store(self, requirement_id, document, *, expected=None, analysis_id=None):
        async with self.repository_scope() as repositories:
            requirements = repositories.requirements
            row = await requirements.get_by_id(requirement_id)
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
            await validate_requirement_replacement(
                repositories.test_cases, repositories.test_designs, requirement_id, document
            )
            checked = RequirementDocument.model_validate(document.model_dump())
            stored = await requirements.update_qa_model_if_current(
                requirement_id, original, SensitiveRedactor.redact_value(checked.model_dump(mode="json"))
            )
            if not stored:
                raise RequirementAnalysisBusy("Concurrent requirement update; result was not applied")
            await repositories.commit()

    async def stream(self, requirement_id, *, task_id=None, reserve_ai_call=None):
        title, description, project_id, document, raw, project_context, existing_cases = await self._load(
            requirement_id
        )
        if document.history and document.history[-1].status == "RUNNING":
            if datetime.fromisoformat(document.history[-1].started_at) > utc_now() - timedelta(minutes=10):
                raise RequirementAnalysisBusy("Requirement analysis is already running")
        record = AnalysisRecord(id=uuid4().hex, status="RUNNING", started_at=utc_now().isoformat())
        async with self.repository_scope() as repositories:
            row = await repositories.requirements.get_by_id(requirement_id)
            record.input_hash = input_hash(title, description, row.acceptance_criteria, document)
        document.history = [*document.history[-9:], record]
        await self._store(requirement_id, document, expected=raw)
        active_stage = "context"
        active_stage_started = None

        async def stage(key, title, status, message="", source="deterministic", duration_ms=0):
            nonlocal active_stage, active_stage_started
            active_stage = key
            if status == "RUNNING":
                active_stage_started = time.perf_counter()
            elif status in ("COMPLETED", "FAILED", "SKIPPED"):
                active_stage_started = None
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
                "加载需求输入",
                "COMPLETED",
                f"已加载需求“{title}”及验收标准文本。",
            )
            yield await stage(
                "project_context",
                "加载项目上下文",
                "COMPLETED",
                f"已加载项目 {project_context['name']}（{project_id}）。",
            )
            yield await stage(
                "existing_cases",
                "查找已有测试用例",
                "COMPLETED",
                f"找到 {len(existing_cases)} 个关联用例。"
                if existing_cases
                else "尚无关联用例；本次分析不以既有用例推断覆盖。",
            )
            yield await stage(
                "acceptance_criteria",
                "提取验收标准与业务规则",
                "COMPLETED",
                (
                    f"读取 {len(document.criteria)} 条验收标准、{len(document.rules)} 条业务规则。"
                    if document.criteria
                    else "没有预填验收标准；继续依据需求描述分析，并将不确定内容作为假设或待确认项。"
                ),
            )
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
            if reserve_ai_call is not None and not await reserve_ai_call():
                raise ValueError("Task AI-call budget exhausted before requirement analysis.")
            started = time.perf_counter()
            payload = {
                "title": title,
                "description": description[:5000],
                "project": project_context,
                "model": document.model_dump(exclude={"history"}, mode="json"),
                "existing_cases": existing_cases,
            }
            request = AICompletionRequest(
                prompt=REQUIREMENT_LIFECYCLE_PROMPT.format(requirement=json.dumps(payload, ensure_ascii=False)),
                system_instruction=REQUIREMENT_LIFECYCLE_PROMPT.system_instruction,
                prompt_id=REQUIREMENT_LIFECYCLE_PROMPT.prompt_id,
                prompt_version=REQUIREMENT_LIFECYCLE_PROMPT.version,
                response_schema=RequirementAnalysis,
                max_tokens=6000,
                max_retries=1,
                task_id=task_id,
                run_id=record.id,
            )
            stream_completion = getattr(self.orchestrator, "complete_streaming", None)
            if callable(stream_completion):
                configured_timeout = getattr(provider, "timeout", None)
                if configured_timeout is None:
                    timeout_seconds = DEFAULT_REQUIREMENT_ANALYSIS_TIMEOUT_SECONDS
                else:
                    # The provider timeout limits an individual HTTP read; a healthy stream
                    # can take longer overall while continuing to emit chunks.
                    timeout_seconds = max(MIN_REQUIREMENT_ANALYSIS_TIMEOUT_SECONDS, float(configured_timeout))
                response = await stream_completion(request, timeout_seconds=timeout_seconds)
            else:
                response = await self.orchestrator.complete(request)
            record.provider, record.model = response.provider, response.model
            record.prompt_version = REQUIREMENT_LIFECYCLE_PROMPT.version
            if response.provider == "fake" or response.fallback_used:
                record.status = "FALLBACK"
                raise ValueError("AI unavailable: simulated fallback is not an analyzed requirement")
            analysis = _validate_analysis_payload(response.structured_data)
            _discard_unknown_analysis_references(analysis, document)
            updated = document.model_copy(deep=True, update={"analysis": analysis})
            RequirementDocument.model_validate(updated.model_dump())
            async with self.repository_scope() as repositories:
                await validate_requirement_replacement(
                    repositories.test_cases, repositories.test_designs, requirement_id, updated
                )
            yield await stage(
                "semantic",
                "AI 语义与风险分析",
                "COMPLETED",
                f"识别 {len(analysis.risks)} 项风险、{len(analysis.ambiguities)} 项歧义与 {len(analysis.scenarios)} 个场景",
                response.provider,
                (time.perf_counter() - started) * 1000,
            )
            yield await stage(
                "business_rules",
                "整理业务规则",
                "COMPLETED",
                f"确认 {len(document.rules)} 条持久业务规则，并与分析结果关联。",
            )
            yield await stage(
                "risk_analysis",
                "分析风险与歧义",
                "COMPLETED",
                f"识别 {len(analysis.risks)} 项风险与 {len(analysis.ambiguities)} 项歧义。",
                response.provider,
            )
            yield await stage(
                "coverage_gaps",
                "检查覆盖缺口",
                "COMPLETED",
                f"识别 {len(analysis.coverage_gaps)} 项覆盖缺口。",
                response.provider,
            )
            yield await stage(
                "test_design",
                "生成测试场景草案",
                "COMPLETED",
                f"生成 {len(analysis.scenarios)} 个场景草案；需在 Workspace 中确认后采用。",
                response.provider,
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
                    task_id=task_id,
                    reserve_task_call=reserve_ai_call,
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
                "INVALID_STRUCTURED_OUTPUT"
                if isinstance(error, ValidationError)
                else str(getattr(error, "code", None) or type(error).__name__.upper())
            )
            record.error = SensitiveRedactor.redact_text(str(error))[:1000]
            record.finished_at = utc_now().isoformat()
            failed_duration_ms = (
                (time.perf_counter() - active_stage_started) * 1000 if active_stage_started is not None else 0
            )
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
                    duration_ms=failed_duration_ms,
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
        async with self.repository_scope() as repositories:
            requirements = repositories.requirements
            row = await requirements.get_by_id(requirement_id)
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
            await requirements.update_qa_model_if_current(requirement_id, original, updated)
            await repositories.commit()

    async def adopt_designs(self, requirement_id):
        _, _, _, document, _, _, _ = await self._load(requirement_id)
        if not document.analysis:
            raise ValueError("Analyze this requirement before creating designs")
        async with self.repository_scope() as repositories:
            repo = repositories.test_designs
            existing = await repo.list_by_requirement(requirement_id)
            result = []
            for scenario in document.analysis.scenarios:
                found = next((item for item in existing if (item.scenario_model or {}).get("id") == scenario.id), None)
                if found:
                    found.scenario_model = scenario.model_dump(mode="json")
                    found.description, found.title = scenario.intent, scenario.title
                    item = TestDesignService(repo, repositories.requirements)._to_dto(found)
                else:
                    item = await TestDesignService(repo, repositories.requirements).create_test_design(
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
            await repositories.commit()
            return result

    async def adopt_case(self, design_id):
        async with self.repository_scope() as repositories:
            design = await repositories.test_designs.get_by_id(design_id)
            if not design or not design.scenario_model:
                raise ValueError("Select a structured test design")
            requirement = await repositories.requirements.get_by_id(design.requirement_id)
            existing = await repositories.test_cases.get_by_test_design(design_id)
            if existing:
                return TestCaseService(
                    repositories.test_cases, repositories.requirements, repositories.test_designs
                )._to_dto(existing)
            from project_model.lifecycle import TestScenario

            scenario = TestScenario.model_validate(design.scenario_model)
            data = await validate_case_model(
                repositories.requirements,
                repositories.test_designs,
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
                ),
            )
            item = TestCaseService(
                repositories.test_cases, repositories.requirements, repositories.test_designs
            )._to_dto(await repositories.test_cases.create(data))
            await repositories.commit()
            return item
