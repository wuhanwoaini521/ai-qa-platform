"""Structured requirement workflow on the existing governed AI and decision runtimes."""

from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from project_model.lifecycle import (
    AnalysisRecord,
    AnalysisStage,
    GroundedAssertion,
    ModernTestModel,
    RequirementAnalysis,
    RequirementDocument,
    ScriptBinding,
    TestOracle,
)
from project_model.models import DecisionOption, DecisionRequest, TestCaseCreate, TestDesignCreate
from pydantic import BaseModel, Field, ValidationError
from qa_core.ai.models import AICompletionRequest
from qa_core.ai.trace import make_trace_event
from qa_core.author import GroundingValidator
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.prompts import ASSERTION_SCRIPT_PROMPT, GROUNDED_ASSERTION_PROMPT, REQUIREMENT_LIFECYCLE_PROMPT

from app.persistence.models import utc_now
from app.ports.repository_scope import RepositoryScopeFactory
from app.repositories.run_history_repo import RunHistoryRepository
from app.services.ai_runtime import build_ai_orchestrator
from app.services.decision_service import DecisionService
from app.services.lifecycle_validation import input_hash, validate_case_model, validate_requirement_replacement
from app.services.task_code_generation_service import TaskCodeGenerationService
from app.services.task_errors import TaskBlocked
from app.services.test_case_service import TestCaseService
from app.services.test_design_service import TestDesignService
from app.services.workspace_service import WorkspaceService


class AssertionDraftItem(BaseModel):
    criterion_id: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=8, max_length=400)
    check: str = Field(default="", max_length=300)


class AssertionDraftResponse(BaseModel):
    assertions: list[AssertionDraftItem] = Field(min_length=1, max_length=30)


class AssertionScriptResponse(BaseModel):
    file_path: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1)
    used_criterion_ids: list[str] = Field(min_length=1, max_length=30)


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


def _is_stale(entry: dict, after_seconds: int) -> bool:
    """An analysis is only abandoned when its own start is older than the window."""
    started = entry.get("started_at")
    if not started:
        return True
    try:
        moment = datetime.fromisoformat(str(started))
    except ValueError:
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment < utc_now() - timedelta(seconds=after_seconds)


class RequirementLifecycleService:
    def __init__(self, repository_scope: RepositoryScopeFactory, orchestrator=None, decisions=None):
        self.repository_scope = repository_scope
        self.orchestrator = orchestrator or build_ai_orchestrator()
        self.decisions = decisions or DecisionService(repository_scope=repository_scope)

    # A second replica starts while the first is still waiting for the model. Only an analysis older
    # than this window can be called abandoned; `stream` already treats a younger RUNNING entry as live.
    STALE_AFTER_SECONDS = 600

    async def recover_interrupted(self):
        async with self.repository_scope() as repositories:
            rows = await repositories.requirements.list_with_qa_model()
            for row in rows:
                raw = row["qa_model"] or {}
                if (
                    raw.get("history")
                    and raw["history"][-1].get("status") == "RUNNING"
                    and _is_stale(raw["history"][-1], self.STALE_AFTER_SECONDS)
                ):
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
            # Bound existing-case excerpts to the analysis prompt budget; this does not alter persisted TestCases.
            existing_cases = [
                {
                    "id": case.id,
                    "title": case.title[:200],
                    "steps": [str(step)[:200] for step in (case.steps or [])[:3]],
                    "expected_result": (case.expected_result or "")[:350],
                    "intent": str((case.test_model or {}).get("intent") or "")[:250],
                    "coverage": (case.test_model or {}).get("coverage", {}),
                }
                for case in cases
            ]
            return row.title, row.description, row.project_id, document, raw, project_context, existing_cases

    async def _store(self, requirement_id, document, *, expected=None, analysis_id=None, check_input_hash=True):
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
            # The input hash protects an analysis result from being written over changed inputs.
            # Draft-only writes (for example grounded assertions) do not replace analysis output,
            # so they rely on the optimistic-concurrency check instead.
            if (
                expected is not None
                and check_input_hash
                and document.history
                and document.history[-1].input_hash
                != input_hash(row.title, row.description, row.acceptance_criteria, document)
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
                max_tokens=10000,
                max_retries=1,
                thinking_mode="disabled" if record.model.casefold().startswith("deepseek-") else None,
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
                    # Once a scenario has a lifecycle record, it may contain deliberate human
                    # edits. Re-adopting the immutable analysis snapshot must never overwrite them.
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

    async def draft_assertions(self, requirement_id):
        """Draft assertions grounded in the requirement's acceptance criteria.

        Nothing is applied automatically: drafts stay unadopted until a human adopts them, and the
        deterministic runner remains the only source of PASS/FAIL.
        """
        title, description, _project_id, document, raw, _context, _cases = await self._load(requirement_id)
        criteria = {item.id: item.description for item in document.criteria}
        if not criteria:
            raise ValueError("Acceptance criteria are required before assertions can be grounded")
        provider = getattr(self.orchestrator.ai_provider, "primary", self.orchestrator.ai_provider)
        provider_name = getattr(provider, "provider_name", "unknown")
        if provider_name == "fake":
            raise ValueError(
                "Fake AI is configured; grounded assertions require a real provider. Configure one and retry."
            )
        request = AICompletionRequest(
            prompt=GROUNDED_ASSERTION_PROMPT.format(
                title=title,
                description=description[:4000],
                criteria="\n".join(f"- {cid}: {text}" for cid, text in criteria.items()),
            ),
            system_instruction=GROUNDED_ASSERTION_PROMPT.system_instruction,
            prompt_id=GROUNDED_ASSERTION_PROMPT.prompt_id,
            prompt_version=GROUNDED_ASSERTION_PROMPT.version,
            response_schema=AssertionDraftResponse,
            max_tokens=4000,
            max_retries=1,
        )
        response = await self.orchestrator.complete(request)
        if response.provider == "fake" or response.fallback_used:
            raise ValueError("AI unavailable: simulated fallback cannot ground assertions")
        payload = AssertionDraftResponse.model_validate(response.structured_data)
        unknown = sorted({item.criterion_id for item in payload.assertions if item.criterion_id not in criteria})
        if unknown:
            raise ValueError("Assertion draft cited unknown acceptance criteria: " + ", ".join(unknown))
        statements = [item.statement.strip() for item in payload.assertions]
        if len(statements) != len(set(statements)):
            raise ValueError("Assertion draft contains duplicate statements")
        source = f"{response.provider}/{response.model}"
        # Never discard human-adopted assertions; only refresh the unadopted drafts.
        kept = [item for item in document.assertions if item.adopted]
        used_ids = {item.id for item in kept}
        drafted = []
        for item in payload.assertions:
            index = 1
            candidate = f"ASR-{item.criterion_id}-{index}"
            while candidate in used_ids:
                index += 1
                candidate = f"ASR-{item.criterion_id}-{index}"
            used_ids.add(candidate)
            drafted.append(
                GroundedAssertion(
                    id=candidate,
                    criterion_id=item.criterion_id,
                    statement=item.statement.strip(),
                    check=item.check.strip(),
                    adopted=False,
                    source=source,
                    created_at=utc_now().isoformat(),
                )
            )
        document.assertions = [*kept, *drafted]
        await self._store(requirement_id, document, expected=raw, check_input_hash=False)
        return document.assertions

    async def generate_assertion_script(self, requirement_id):
        """Turn human-adopted assertions into a script draft.

        The draft is returned to the caller only. Nothing is written to the workspace here: the
        human still saves it through the existing workspace editor, which is the approval step.
        """
        title, description, project_id, document, _raw, _context, _cases = await self._load(requirement_id)
        adopted = [item for item in document.assertions if item.adopted]
        if not adopted:
            raise ValueError("Adopt at least one assertion draft before generating a script")
        provider = getattr(self.orchestrator.ai_provider, "primary", self.orchestrator.ai_provider)
        if getattr(provider, "provider_name", "unknown") == "fake":
            raise ValueError("Fake AI is configured; script generation requires a real provider")
        for item in adopted:
            if SensitiveRedactor.contains_redaction_placeholder(
                item.statement
            ) or SensitiveRedactor.contains_redaction_placeholder(item.check):
                raise ValueError(
                    "Adopted assertion contains a redaction placeholder; restore the real expectation before generating"
                )
        workspace_dir = WorkspaceService().get_workspace_dir(project_id)
        listing = ""
        fixtures = "(none)"
        if workspace_dir.exists():
            listing = "\n".join(
                sorted(
                    str(path.relative_to(workspace_dir))
                    for path in workspace_dir.rglob("*.py")
                    if "__pycache__" not in path.parts
                )[:40]
            )
            conftest = workspace_dir / "conftest.py"
            if conftest.is_file():
                names = re.findall(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", conftest.read_text(), re.MULTILINE)
                if names:
                    fixtures = ", ".join(sorted(set(names)))
        request = AICompletionRequest(
            prompt=ASSERTION_SCRIPT_PROMPT.format(
                title=title,
                description=description[:3000],
                criteria="\n".join(f"- {item.id}: {item.description}" for item in document.criteria) or "(none)",
                fixtures=fixtures,
                workspace=listing or "(empty workspace)",
                assertions="\n".join(
                    f"- {item.criterion_id} | {item.statement} | {item.check or 'no explicit check'}"
                    for item in adopted
                ),
            ),
            system_instruction=ASSERTION_SCRIPT_PROMPT.system_instruction,
            prompt_id=ASSERTION_SCRIPT_PROMPT.prompt_id,
            prompt_version=ASSERTION_SCRIPT_PROMPT.version,
            response_schema=AssertionScriptResponse,
            max_tokens=6000,
            max_retries=1,
        )
        response = await self.orchestrator.complete(request)
        if response.provider == "fake" or response.fallback_used:
            raise ValueError("AI unavailable: simulated fallback cannot generate a script")
        payload = AssertionScriptResponse.model_validate(response.structured_data)
        adopted_ids = {item.criterion_id for item in adopted}
        used_ids = set(payload.used_criterion_ids)
        unknown = sorted(used_ids - adopted_ids)
        if unknown:
            raise ValueError("Generated script cites assertions that were not adopted: " + ", ".join(unknown))
        missing = sorted(adopted_ids - used_ids)
        if missing:
            raise ValueError("Generated script omitted adopted assertions: " + ", ".join(missing))
        try:
            ast.parse(payload.code)
        except SyntaxError as error:
            raise ValueError(f"Generated script is not valid Python: {error}") from error
        try:
            TaskCodeGenerationService._validate_goal_generated_test(payload.code, payload.file_path)
        except TaskBlocked as error:
            raise ValueError(f"Generated script violates the test policy: {error}") from error
        self._validate_script_asserts_a_real_page(payload.code)
        markers = set(re.findall(r"#\s*criterion:\s*(AC-[A-Za-z0-9-]+)", payload.code))
        if not adopted_ids <= markers:
            absent = ", ".join(sorted(adopted_ids - markers))
            raise ValueError("Generated script is missing '# criterion:' traceability markers for: " + absent)
        unexpected = sorted(markers - adopted_ids)
        if unexpected:
            raise ValueError("Generated script references criteria that were not adopted: " + ", ".join(unexpected))
        referenced = set(re.findall(r"ASR-[A-Za-z0-9-]+", payload.code))
        allowed_assertions = {item.id for item in adopted}
        foreign = sorted(referenced - allowed_assertions)
        if foreign:
            raise ValueError("Generated script references assertions that were not adopted: " + ", ".join(foreign))
        file_path = payload.file_path.strip()
        if not (file_path.startswith("tests/") and file_path.endswith(".py")) or ".." in Path(file_path).parts:
            raise ValueError("Generated script path must be a tests/*.py file inside the workspace")
        if workspace_dir.exists():
            report = GroundingValidator(workspace_dir).validate(payload.code, file_path)
            if not report.grounded:
                detail = "; ".join(f"{item.kind}: {item.reference}" for item in report.violations[:5])
                raise ValueError(f"Generated script is not grounded in the workspace: {detail}")
        return {
            "file_path": file_path,
            "code": payload.code,
            "used_criterion_ids": sorted(set(payload.used_criterion_ids)),
            "assertion_ids": [item.id for item in adopted if item.criterion_id in markers],
            "provider": response.provider,
            "model": response.model,
        }

    async def set_assertion_adoption(self, requirement_id, assertion_id, adopted):
        title, description, _project_id, document, raw, _context, _cases = await self._load(requirement_id)
        target = next((item for item in document.assertions if item.id == assertion_id), None)
        if target is None:
            raise LookupError(f"Assertion not found: {assertion_id}")
        target.adopted = bool(adopted)
        await self._store(requirement_id, document, expected=raw, check_input_hash=False)
        return target

    @staticmethod
    def _validate_script_asserts_a_real_page(code):
        """Reject scripts that fabricate the page they assert on (false-green guard)."""
        tree = ast.parse(code)
        # Launching a browser is allowed (workspaces without a page fixture need it); fabricating
        # the page under test or intercepting its network is not.
        forbidden = {"set_content", "route", "unroute", "route_from_har", "add_init_script"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            if name in forbidden:
                raise ValueError(
                    f"Generated script builds its own page ({name}); assertions must target the real page under test"
                )
        navigates = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"goto", "navigate"}
            for node in ast.walk(tree)
        )
        if not navigates:
            raise ValueError("Generated script never navigates (page.goto) to the page it asserts on")

    async def case_assertions(self, case_id):
        """Case-level assertions, with nodeids derived from the requirement's saved scripts.

        Deriving at read time keeps one source of truth (the requirement document) and means a case
        adopted before the script existed still reports the right test function.
        """
        async with self.repository_scope() as repositories:
            case = await repositories.test_cases.get_by_id(case_id)
            if case is None:
                raise LookupError(case_id)
            requirement = (
                await repositories.requirements.get_by_id(case.requirement_id) if case.requirement_id else None
            )
            model = dict(case.test_model or {})
            assertions = [dict(entry) for entry in (model.get("assertions") or [])]
            project_id = case.project_id
            document = (
                RequirementDocument.model_validate(requirement.qa_model)
                if requirement is not None and requirement.qa_model
                else None
            )
        pairing_by_criterion: dict[str, str] = {}
        if document is not None:
            for binding in document.scripts:
                for pairing in binding.nodeid_criteria:
                    for criterion in pairing.criterion_ids:
                        pairing_by_criterion.setdefault(criterion, pairing.nodeid)
        for entry in assertions:
            entry["nodeid"] = entry.get("nodeid") or pairing_by_criterion.get(entry.get("criterion_id", ""), "")
        latest: dict[str, dict] = {}
        nodeids = [entry["nodeid"] for entry in assertions if entry.get("nodeid")]
        if nodeids:
            for execution, run in await RunHistoryRepository().get_latest_executions_with_runs(nodeids, project_id):
                latest.setdefault(
                    execution.nodeid,
                    {
                        "run_id": run.id,
                        "run_status": getattr(run.status, "value", run.status),
                        "execution_status": getattr(execution.status, "value", execution.status),
                        "finished_at": (execution.finished_at or run.finished_at).isoformat()
                        if (execution.finished_at or run.finished_at)
                        else None,
                        "artifact_count": len(execution.artifact_paths or []),
                    },
                )
        items = []
        for entry in assertions:
            record = latest.get(entry.get("nodeid") or "")
            items.append(
                {
                    **entry,
                    "state": record["execution_status"]
                    if record
                    else ("NEVER_RUN" if entry.get("nodeid") else "UNBOUND"),
                    "run": record,
                }
            )
        return {"case_id": case_id, "assertions": items}

    async def discard_assertion(self, requirement_id, assertion_id):
        """Forget an assertion (used when its text can no longer be turned into a test)."""
        _title, _desc, _project_id, document, raw, _ctx, _cases = await self._load(requirement_id)
        if not any(item.id == assertion_id for item in document.assertions):
            raise LookupError(assertion_id)
        document.assertions = [item for item in document.assertions if item.id != assertion_id]
        kept = []
        for binding in document.scripts:
            remaining = [identifier for identifier in binding.assertion_ids if identifier != assertion_id]
            if not remaining:
                continue
            binding.assertion_ids = remaining
            binding.nodeid_criteria = [
                pairing
                for pairing in binding.nodeid_criteria
                if set(pairing.criterion_ids) <= {item.criterion_id for item in document.assertions}
            ]
            kept.append(binding)
        document.scripts = kept
        await self._store(requirement_id, document, expected=raw, check_input_hash=False)

    async def save_assertion_script(self, requirement_id, *, path, code, assertion_ids):
        """Persist a human-approved script and record which assertions it implements.

        The write is compare-and-swap (never overwrites an existing file) and the binding is what
        later maps real TestRun executions back to the assertions that motivated them.
        """
        _title, _desc, project_id, document, raw, _ctx, _cases = await self._load(requirement_id)
        adopted = {item.id: item for item in document.assertions if item.adopted}
        requested = list(dict.fromkeys(assertion_ids))
        if not requested or any(identifier not in adopted for identifier in requested):
            raise ValueError("Only adopted assertions can be saved into a script")
        if not (path.startswith("tests/") and path.endswith(".py")) or ".." in Path(path).parts:
            raise ValueError("Script path must be a tests/*.py file inside the workspace")
        try:
            tree = ast.parse(code)
        except SyntaxError as error:
            raise ValueError(f"Script is not valid Python: {error}") from error
        nodeids = [
            f"{path}::{node.name}"
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test")
        ]
        if not nodeids:
            raise ValueError("Script must define at least one test function")
        # The assertion edge is decided by the code's own traceability markers, never by the caller.
        markers = set(re.findall(r"#\s*criterion:\s*(AC-[A-Za-z0-9-]+)", code))
        unknown_markers = sorted(markers - {item.criterion_id for item in adopted.values()})
        if unknown_markers:
            raise ValueError("Script markers cite criteria without an adopted assertion: " + ", ".join(unknown_markers))
        derived = sorted(item.id for item in adopted.values() if item.criterion_id in markers)
        paired = []
        marker_re = re.compile(r"#\s*criterion:\s*(AC-[A-Za-z0-9-]+)")
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test"):
                continue
            segment = ast.get_source_segment(code, node) or ""
            node_criteria = sorted(set(marker_re.findall(segment)))
            if not node_criteria:
                raise ValueError(
                    f"Test function {node.name} has no '# criterion:' marker; assertions would be unmappable"
                )
            paired.append({"nodeid": f"{path}::{node.name}", "criterion_ids": node_criteria})
        if set(derived) != set(requested):
            missing = ", ".join(sorted(set(derived) - set(requested)))
            extra = ", ".join(sorted(set(requested) - set(derived)))
            detail = []
            if missing:
                detail.append(f"missing {missing}")
            if extra:
                detail.append(f"not implemented in code {extra}")
            raise ValueError("Script markers do not match the requested assertions: " + "; ".join(detail))

        ai_provider = getattr(self.orchestrator.ai_provider, "primary", self.orchestrator.ai_provider)
        provider_name = str(getattr(ai_provider, "provider_name", "") or "")
        model_name = str(getattr(ai_provider, "model", "") or "")

        paired_criteria = {criterion for entry in paired for criterion in entry["criterion_ids"]}
        unpaired = sorted(markers - paired_criteria)
        if unpaired:
            raise ValueError(
                "Every '# criterion:' marker must live inside a test function; unpaired: " + ", ".join(unpaired)
            )

        workspace = WorkspaceService()
        created = False
        try:
            await workspace.write_file_if_unchanged(project_id, path, code, False, None)
            created = True
        except FileExistsError:
            existing = await workspace.read_file(project_id, path)
            if hashlib.sha256(existing.encode()).hexdigest() != hashlib.sha256(code.encode()).hexdigest():
                raise FileExistsError("A different script already exists at this path; refusing to overwrite") from None
        try:
            binding = ScriptBinding(
                path=path,
                nodeids=nodeids,
                assertion_ids=derived,
                criterion_ids=sorted({adopted[identifier].criterion_id for identifier in derived}),
                nodeid_criteria=paired,
                provider=provider_name,
                model=model_name,
                saved_at=utc_now().isoformat(),
            )
            document.scripts = [item for item in document.scripts if item.path != path][:9] + [binding]
            await self._store(requirement_id, document, expected=raw, check_input_hash=False)
        except Exception:
            if created:
                await workspace.delete_file(project_id, path)
            raise
        return binding

    @staticmethod
    def _resolve_assertion_state(adopted: bool, entry: dict | None, active_paths: set[str], path: str) -> str:
        if not adopted:
            return "NOT_ADOPTED"
        if entry is None:
            return "RUNNING" if path in active_paths else "NEVER_RUN"
        execution_status = entry["execution_status"]
        run_status = entry["run_status"]
        if execution_status in {"PASSED", "FAILED"}:
            if run_status == "ERROR":
                return "BLOCKED"
            return execution_status
        if execution_status == "SKIPPED":
            return "BLOCKED"
        if execution_status in {"CANCELLED", "ERROR"}:
            return "CANCELLED" if execution_status == "CANCELLED" else "BLOCKED"
        if run_status in {"QUEUED", "RUNNING"}:
            return "RUNNING"
        if run_status == "CANCELLED":
            return "CANCELLED"
        if run_status == "ERROR":
            return "BLOCKED"
        if run_status in {"PASSED", "FAILED"}:
            return "RECORD_INACCESSIBLE"
        return "UNKNOWN"

    async def assertion_runs(self, requirement_id):
        """Map every assertion to its latest real execution record (never inferred pass/fail)."""
        _title, _desc, project_id, document, _raw, _ctx, _cases = await self._load(requirement_id)
        bindings = list(document.scripts)
        latest: dict[str, dict] = {}
        active_paths: set[str] = set()
        if bindings:
            all_nodeids = [nodeid for binding in bindings for nodeid in binding.nodeids]
            rows = await RunHistoryRepository().get_latest_executions_with_runs(all_nodeids, project_id)
            nodeid_index = {nodeid: binding for binding in bindings for nodeid in binding.nodeids}
            for execution, run in rows:
                binding = nodeid_index.get(execution.nodeid)
                if binding is None or execution.nodeid in latest:
                    continue
                latest[execution.nodeid] = {
                    "run_id": run.id,
                    "run_status": getattr(run.status, "value", run.status),
                    "nodeid": execution.nodeid,
                    "execution_status": getattr(execution.status, "value", execution.status),
                    "finished_at": (run.finished_at or execution.finished_at or run.created_at).isoformat()
                    if (run.finished_at or execution.finished_at or run.created_at)
                    else None,
                    "artifact_count": len(execution.artifact_paths or []),
                    "error_message": SensitiveRedactor.redact_text(execution.error_message or "")[:300],
                }
            async with self.repository_scope() as repositories:
                runs = await repositories.test_runs.list_runs(project_id, limit=25)
            for run in runs:
                run_status = getattr(run.status, "value", run.status)
                for nodeid in run.nodeids or []:
                    if nodeid not in nodeid_index:
                        continue
                    if run_status in {"QUEUED", "RUNNING"}:
                        active_paths.add(nodeid_index[nodeid].path)
                    if nodeid in latest:
                        continue
                    # Terminal run without execution rows (Jenkins, collection error, stale cancel):
                    # report the run-level truth instead of pretending nothing ever ran.
                    if run_status in {"PASSED", "FAILED", "CANCELLED", "ERROR", "SKIPPED"}:
                        latest[nodeid] = {
                            "run_id": run.id,
                            "run_status": run_status,
                            "nodeid": nodeid,
                            "execution_status": None,
                            "finished_at": (run.finished_at or run.created_at).isoformat()
                            if (run.finished_at or run.created_at)
                            else None,
                            "artifact_count": len(getattr(run, "external_artifacts", []) or []),
                            "error_message": "",
                        }
        assertions = []
        for item in document.assertions:
            binding = next((candidate for candidate in bindings if item.id in candidate.assertion_ids), None)
            entry = None
            if binding is not None:
                pairing = next(
                    (
                        candidate
                        for candidate in binding.nodeid_criteria
                        if item.criterion_id in candidate.criterion_ids
                    ),
                    None,
                )
                if pairing is not None:
                    entry = latest.get(pairing.nodeid)
                elif binding.nodeid_criteria:
                    # Paired bindings never fall back to file level: unpaired assertions stay unstated.
                    entry = None
                else:
                    # Legacy bindings created before pairing keep file-level behaviour.
                    candidates = [latest[nodeid] for nodeid in binding.nodeids if nodeid in latest]
                    if candidates:
                        entry = max(candidates, key=lambda item: item.get("finished_at") or "")
            state = self._resolve_assertion_state(item.adopted, entry, active_paths, binding.path if binding else "")
            assertions.append(
                {
                    "assertion_id": item.id,
                    "criterion_id": item.criterion_id,
                    "adopted": item.adopted,
                    "state": state,
                    "run": entry,
                }
            )
        return {
            "requirement_id": requirement_id,
            "scripts": [binding.model_dump(mode="json") for binding in bindings],
            "assertions": assertions,
        }

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
            requirement_document = (
                RequirementDocument.model_validate(requirement.qa_model) if requirement.qa_model else None
            )
            covered = set(scenario.coverage.criterion_ids)
            adopted_assertions = [
                assertion
                for assertion in (requirement_document.assertions if requirement_document else [])
                if assertion.adopted and assertion.criterion_id in covered
            ]
            case_assertions = [
                {
                    "id": f"TCA-{assertion.id.removeprefix('ASR-')}",
                    "criterion_id": assertion.criterion_id,
                    "statement": assertion.statement,
                    "check": assertion.check,
                    "source_assertion_id": assertion.id,
                }
                for assertion in adopted_assertions
            ]
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
                        assertions=case_assertions,
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
