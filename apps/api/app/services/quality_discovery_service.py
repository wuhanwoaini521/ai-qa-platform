from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Callable, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from project_model.lifecycle import StructuredRequirementModel
from project_model.models import DecisionOption, DecisionRequest
from pydantic import BaseModel, Field, field_validator, model_validator
from qa_core.ai.browser_safety import classify_browser_action
from qa_core.ai.models import AICompletionRequest
from qa_core.failure.redactor import SensitiveRedactor
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.persistence.models import (
    QualityDiscoveryRunORM,
    utc_now,
)
from app.ports.browser_runtime import BrowserRuntime
from app.repositories.artifact_repo import ArtifactRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.decision_service import DecisionService
from app.settings import get_config


class DiscoveryMode(StrEnum):
    EXPLORE = "EXPLORE"
    VALIDATE = "VALIDATE"
    AUDIT = "AUDIT"


class DiscoveryStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class _GapActionLockEntry:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.users = 0


class DiscoveryRunCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    start_url: str = Field(min_length=8, max_length=2048)
    mode: DiscoveryMode = DiscoveryMode.EXPLORE
    requirement_id: str | None = Field(default=None, max_length=36)
    requirement_text: str = Field(default="", max_length=20_000)
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("start_url")
    @classmethod
    def validate_start_url(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("Start URL must be a valid http(s) URL without embedded credentials.")
        if parts.query or parts.fragment:
            raise ValueError(
                "Start URL must not include query or fragment data; it may contain credentials or session tokens."
            )
        return value.strip()

    @field_validator("allowed_domains")
    @classmethod
    def normalize_allowed_domains(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            host = value.strip().lower().rstrip(".")
            if (
                not host
                or "/" in host
                or ":" in host
                or "@" in host
                or "?" in host
                or "#" in host
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))
                or ("." not in host and host != "localhost")
            ):
                raise ValueError("Allowed domains must contain host names only.")
            normalized.append(host)
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_requirement_input(self):
        if self.requirement_id and self.requirement_text.strip():
            raise ValueError("Choose an existing Requirement or paste Requirement text, not both.")
        if self.mode in {DiscoveryMode.VALIDATE, DiscoveryMode.AUDIT} and not (
            self.requirement_id or self.requirement_text.strip()
        ):
            raise ValueError(f"{self.mode.value} mode requires a Requirement.")
        return self


class RequirementCheck(BaseModel):
    target: str = Field(min_length=1, max_length=160)
    attribute: Literal["enabled", "selected", "visible"]
    expected: bool
    when: Literal["always", "size_unselected", "size_selected", "after_action"] = "always"
    criterion: str = Field(default="", max_length=500)


class ExpectedState(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    condition: str = Field(default="", max_length=500)
    expected: str = Field(default="", max_length=500)


class ExpectedTransition(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    action: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=120)
    criterion: str = Field(default="", max_length=500)


class RequirementSignal(BaseModel):
    feature: str = Field(min_length=1, max_length=200)
    actors: list[str] = Field(default_factory=list, max_length=12)
    preconditions: list[str] = Field(default_factory=list, max_length=12)
    business_rules: list[str] = Field(default_factory=list, max_length=20)
    actions: list[str] = Field(default_factory=list, max_length=20)
    expected_behavior: str = Field(default="", max_length=1000)
    expected_states: list[ExpectedState] = Field(default_factory=list, max_length=16)
    expected_transitions: list[ExpectedTransition] = Field(default_factory=list, max_length=16)
    negative_states: list[str] = Field(default_factory=list, max_length=12)
    exceptions: list[str] = Field(default_factory=list, max_length=12)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    checks: list[RequirementCheck] = Field(default_factory=list, max_length=8)
    risk: str = Field(default="unknown", max_length=40)
    unknown: list[str] = Field(default_factory=list, max_length=12)
    ambiguous: bool = False


class RequirementAnalysisItem(BaseModel):
    feature: str = Field(min_length=1, max_length=200)
    expected_behavior: str = Field(default="", max_length=1000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    checks: list[RequirementCheck] = Field(default_factory=list, max_length=8)
    risk: str = Field(default="unknown", max_length=40)
    ambiguous: bool = False


class RequirementAnalysis(BaseModel):
    requirements: list[RequirementAnalysisItem] = Field(default_factory=list, max_length=4)
    ambiguities: list[str] = Field(default_factory=list, max_length=20)


class FeatureSignal(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    target_id: str | None = Field(default=None, max_length=32)
    evidence_text: str = Field(default="", max_length=240)
    confidence: float = Field(default=0.5, ge=0, le=1)


class DiscoveryGoal(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    feature: str = Field(default="", max_length=160)
    requirement_id: str | None = Field(default=None, max_length=80)
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    rationale: str = Field(default="", max_length=300)


class DiscoveryPlan(BaseModel):
    page_type: str = Field(default="unknown", max_length=80)
    features: list[FeatureSignal] = Field(default_factory=list, max_length=20)
    goals: list[DiscoveryGoal] = Field(default_factory=list, max_length=20)
    candidate_ids: list[str] = Field(default_factory=list, max_length=20)
    done: bool = False
    reason_summary: str = Field(default="", max_length=300)


class DiscoveryBlocked(RuntimeError):
    pass


class QualityDiscoveryService:
    """Runs bounded, evidence-backed product exploration independently of Browser Agent goals."""

    TERMINAL = {
        DiscoveryStatus.COMPLETED.value,
        DiscoveryStatus.BLOCKED.value,
        DiscoveryStatus.FAILED.value,
        DiscoveryStatus.STOPPED.value,
        DiscoveryStatus.BUDGET_EXHAUSTED.value,
    }

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        browser_runtime: BrowserRuntime,
        decisions: DecisionService | None = None,
        provider_factory: Callable | None = None,
        workspace_service=None,
    ) -> None:
        self.session_factory = session_factory
        self.browser_runtime = browser_runtime
        self.decisions = decisions or DecisionService()
        self._uses_runtime_provider = provider_factory is None
        if provider_factory is None:
            from qa_core.ai.registry import AIProviderRegistry

            provider_factory = AIProviderRegistry.get_provider
        self.provider_factory = provider_factory
        self.workspace_service = workspace_service
        self._tasks: dict[str, asyncio.Task] = {}
        self._resume_events: dict[str, asyncio.Event] = {}
        self._stop_events: dict[str, asyncio.Event] = {}
        self._gap_action_locks: dict[tuple[str, str, str], _GapActionLockEntry] = {}

    def _assert_runtime_ready(self, config) -> None:
        if not self._uses_runtime_provider:
            return
        runtime = get_config()
        if config.require_ai and (
            not runtime.ai.enabled
            or runtime.ai.provider.casefold() == "fake"
            or not runtime.ai.api_key.get_secret_value().strip()
        ):
            raise DiscoveryBlocked(
                "Quality Discovery requires a configured real AI provider; no exploration was started."
            )
        if config.require_jev and (not runtime.jev.enabled or not runtime.jev.api_key.get_secret_value().strip()):
            raise DiscoveryBlocked("Quality Discovery requires configured Jev; no exploration action was executed.")

    @staticmethod
    def _provider_thinking_mode() -> str | None:
        ai = get_config().ai
        return "disabled" if ai.model.casefold().startswith("deepseek-") else None

    async def create(self, data: DiscoveryRunCreate, requested_by: str) -> QualityDiscoveryRunORM:
        config = get_config().discovery
        if not config.enabled:
            raise ValueError("Quality Discovery is disabled by configuration.")
        async with self.session_factory() as session:
            project = await ProjectRepository(session).get_by_id(data.project_id)
            if project is None:
                raise ValueError("Project not found.")
            if data.requirement_id:
                requirement = await RequirementRepository(session).get_by_id(data.requirement_id)
                if requirement is None or requirement.project_id != data.project_id:
                    raise ValueError("Requirement does not belong to the selected project.")
            row = await QualityDiscoveryRepository(session).create(
                project_id=data.project_id,
                requested_by=requested_by,
                mode=data.mode.value,
                start_url=data.start_url,
                requirement_id=data.requirement_id,
                requirement_text=data.requirement_text.strip(),
                allowed_domains=data.allowed_domains,
            )
            await session.commit()
            run_id = row.id
        self._schedule(run_id)
        return await self.get(run_id)

    async def get(self, run_id: str) -> QualityDiscoveryRunORM | None:
        async with self.session_factory() as session:
            row = await QualityDiscoveryRepository(session).get(run_id)
            if row is not None:
                row.result = self._enrich_gap_context(json.loads(json.dumps(row.result or {})))
            return row

    async def list(self, project_id: str, limit: int = 25) -> list[QualityDiscoveryRunORM]:
        async with self.session_factory() as session:
            rows = await QualityDiscoveryRepository(session).list_by_project(project_id, limit)
            for row in rows:
                row.result = self._enrich_gap_context(json.loads(json.dumps(row.result or {})))
            return rows

    async def act_on_gap(self, run_id: str, gap_id: str, action: str) -> dict[str, Any]:
        key = (run_id, gap_id, action)
        async with self._gap_action_lock(key):
            return await self._act_on_gap(run_id, gap_id, action)

    @asynccontextmanager
    async def _gap_action_lock(self, key: tuple[str, str, str]):
        entry = self._gap_action_locks.get(key)
        if entry is None:
            entry = self._gap_action_locks[key] = _GapActionLockEntry()
        entry.users += 1
        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            entry.users -= 1
            if entry.users == 0 and self._gap_action_locks.get(key) is entry:
                del self._gap_action_locks[key]

    async def _act_on_gap(self, run_id: str, gap_id: str, action: str) -> dict[str, Any]:
        row = await self.get(run_id)
        if row is None:
            raise ValueError("Quality Discovery run not found.")
        result = row.result or {}
        recorded = (result.get("gap_actions") or {}).get(gap_id, {}).get(action)
        if recorded:
            if action in {"create_requirement_draft", "generate_tests", "generate_automation"}:
                # A prior request may have committed the action then failed while
                # rebuilding the derived quality-map projection.
                await self._build_quality_map(run_id)
            return recorded
        gap = next((item for item in result.get("gaps", []) if item.get("id") == gap_id), None)
        if gap is None:
            raise ValueError("Quality gap not found.")
        allowed_actions = {
            "UNDOCUMENTED_FEATURE": {"create_requirement_draft"},
            "TEST_MISSING": {"create_requirement_draft", "generate_tests"},
            "AUTOMATION_MISSING": {"generate_automation"},
            "AUTOMATION_FAILING": {"open_failure"},
            "IMPLEMENTED_BROKEN": {"open_failure"},
            "FUNCTION_BROKEN": {"open_failure"},
        }
        category = gap.get("category")
        if action not in allowed_actions.get(category, set()):
            raise ValueError(f"Action '{action}' is not available for '{category}' gaps.")
        feature = next(
            (item for item in result.get("features", []) if item.get("feature_id") == gap.get("item_id")), None
        )

        if action == "create_requirement_draft":
            if feature is None:
                raise ValueError("This gap is not linked to a product feature.")
            response = await self._create_requirement_draft(run_id, gap_id)
            if response["created"]:
                await self._build_quality_map(run_id)
            return response

        if action == "generate_tests":
            self._assert_real_ai_available()
            if feature is None:
                raise ValueError("This gap is not linked to a product feature.")
            source_requirements = [
                item
                for item in result.get("requirements", [])
                if item.get("id") in feature.get("requirement_ids", []) and item.get("source_id") != "PASTED"
            ]
            requirement_id = next(
                (item.get("source_id") for item in source_requirements if item.get("source_id")), None
            )
            requirement_id = requirement_id or (result.get("requirement_drafts") or {}).get(feature["feature_id"])
            if not requirement_id:
                raise ValueError("Create a Requirement Draft from this gap before generating cases.")
            from project_model.models import TestCaseCreate, TestDesignCategory, TestDesignCreate

            from app.repositories.test_design_repo import TestDesignRepository
            from app.services.ai_service import AIService
            from app.services.test_case_service import TestCaseService
            from app.services.test_design_service import TestDesignService

            design_title = f"Discovery — {feature['name']}"[:200]
            async with self.session_factory() as session:
                design_service = TestDesignService(TestDesignRepository(session), RequirementRepository(session))
                existing_designs = await design_service.list_by_requirement(requirement_id)
                design = next((item for item in existing_designs if item.title == design_title), None)
                if design is None:
                    journey = next(
                        (
                            item
                            for item in result.get("journeys", [])
                            if any(
                                step.get("state_id") in feature.get("state_ids", []) for step in item.get("steps", [])
                            )
                        ),
                        None,
                    )
                    context = {
                        "feature": {
                            key: feature.get(key)
                            for key in ("name", "description", "page_type", "status", "evidence_ids", "state_ids")
                        },
                        "risk": gap.get("risk"),
                        "gap": gap.get("category"),
                        "observed_journey": journey.get("steps", []) if journey else [],
                        "generation_constraints": [
                            "Generate a compact set of evidence-grounded happy, negative, boundary, or recovery cases as relevant."
                        ],
                    }
                    design = await design_service.create_test_design(
                        TestDesignCreate(
                            requirement_id=requirement_id,
                            title=design_title,
                            category=TestDesignCategory.FUNCTIONAL,
                            description=json.dumps(context, ensure_ascii=False)[:3000],
                            risk=str(gap.get("risk") or "Medium"),
                        )
                    )
                    await session.commit()
            async with self.session_factory() as session:
                ai = AIService(
                    requirement_repo=RequirementRepository(session),
                    test_design_repo=TestDesignRepository(session),
                    test_case_repo=TestCaseRepository(session),
                    test_run_repo=TestRunRepository(session),
                    project_repo=ProjectRepository(session),
                )
                generated = await ai.generate_test_cases(design.id)
            if not generated:
                raise ValueError("AI returned no test case proposals for this feature.")
            response = None
            for attempt in range(5):
                try:
                    async with self.session_factory() as session:
                        discovery_repo = QualityDiscoveryRepository(session)
                        current = await discovery_repo.get(run_id)
                        if current is None:
                            raise ValueError("Quality Discovery run not found.")
                        result = json.loads(json.dumps(current.result or {}))
                        response = (result.get("gap_actions") or {}).get(gap_id, {}).get(action)
                        if response is None:
                            case_repo = TestCaseRepository(session)
                            case_service = TestCaseService(
                                case_repo, RequirementRepository(session), TestDesignRepository(session)
                            )
                            created_cases = []
                            for item in generated[:8]:
                                created_cases.append(
                                    await case_service.create_test_case(
                                        TestCaseCreate(
                                            project_id=current.project_id,
                                            requirement_id=requirement_id,
                                            test_design_id=design.id,
                                            title=item.title,
                                            preconditions=item.preconditions,
                                            steps=item.steps,
                                            expected_result=item.expected_result,
                                            priority=item.priority,
                                            tags=list(
                                                dict.fromkeys([*item.tags, "quality-discovery", feature["feature_id"]])
                                            )[:20],
                                        )
                                    )
                                )
                            response = {
                                "status": "generated",
                                "test_design_id": design.id,
                                "test_case_ids": [item.id for item in created_cases],
                                "test_cases": [item.model_dump(mode="json") for item in created_cases],
                            }
                            self._apply_gap_action_result(result, gap_id, action, response, feature["feature_id"])
                            events = result.setdefault("events", [])
                            events.append(
                                {
                                    "id": uuid4().hex[:12],
                                    "type": "gap.tests_generated",
                                    "message": f"已为 {feature['name']} 生成 {len(created_cases)} 个测试用例。"[:300],
                                    "metadata": {"gap_id": gap_id},
                                    "created_at": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                            del events[: -get_config().discovery.max_events]
                            states, actions, features = (
                                result.get(name, []) for name in ("states", "actions", "features")
                            )
                            await discovery_repo.update(
                                run_id,
                                result=result,
                                progress={"states": len(states), "actions": len(actions), "features": len(features)},
                            )
                            await session.commit()
                    break
                except (StaleDataError, OperationalError) as exc:
                    if not self._is_retryable_write_conflict(exc) or attempt == 4:
                        raise
                    await asyncio.sleep(0.01 * (attempt + 1))
            if response is None:
                raise RuntimeError("Could not persist generated Test Cases and the Gap action.")
            # Cases and the idempotency record commit together. Rebuilding this projection
            # is safe to retry if the caller loses the response after the commit.
            await self._build_quality_map(run_id)
            return response

        if action == "generate_automation":
            self._assert_real_ai_available()
            if feature is None or not feature.get("test_case_ids"):
                raise ValueError("Generate or link a TestCase before generating its automation.")
            from app.repositories.automation_binding_repo import AutomationBindingRepository
            from app.repositories.workspace_repo import WorkspaceRepository
            from app.services.automation_binding_service import AutomationBindingService
            from app.services.workspace_service import WorkspaceService

            async with self.session_factory() as session:
                discovery_repo = QualityDiscoveryRepository(session)
                current = await discovery_repo.get(run_id)
                if current is None:
                    raise ValueError("Quality Discovery run not found.")
                current_result = json.loads(json.dumps(current.result or {}))
                recorded = (current_result.get("gap_actions") or {}).get(gap_id, {}).get(action)
                if recorded:
                    response = recorded
                else:
                    response = None
                case_repo = TestCaseRepository(session)
                binding_service = AutomationBindingService(
                    AutomationBindingRepository(session),
                    case_repo,
                    WorkspaceRepository(session),
                    self.workspace_service or WorkspaceService(),
                )
                candidates = feature["test_case_ids"]
                selected_case = next(
                    (
                        case_id
                        for case_id in candidates
                        if not any(
                            item.get("test_case_id") == case_id and item.get("automation_status") == "ACTIVE"
                            for item in feature.get("automation", [])
                        )
                    ),
                    candidates[0],
                )
                if response is None:
                    binding, code = await binding_service.generate_automation_draft(
                        selected_case,
                        idempotency_key=f"{run_id}:{gap_id}:{selected_case}",
                    )
                    response = {
                        "status": "generated",
                        "test_case_id": selected_case,
                        "binding": binding.model_dump(mode="json"),
                        "code": code,
                    }
                    self._apply_gap_action_result(current_result, gap_id, action, response, feature["feature_id"])
                    events = current_result.setdefault("events", [])
                    events.append(
                        {
                            "id": uuid4().hex[:12],
                            "type": "gap.automation_generated",
                            "message": f"已为 {feature['name']} 生成自动化草稿。",
                            "metadata": {"gap_id": gap_id, "test_case_id": selected_case},
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    del events[: -get_config().discovery.max_events]
                    await discovery_repo.update(run_id, result=current_result)
                    await session.commit()
            if response is None:
                raise RuntimeError("Could not persist the generated automation and Gap action.")
            # The binding and action journal share one database transaction. The file
            # uses a deterministic action key so a retry can recover a pre-commit draft.
            await self._build_quality_map(run_id)
            return response

        if action == "open_failure":
            if feature is None:
                raise ValueError("This gap has no linked feature or failure record.")
            failed = [
                item for item in feature.get("automation", []) if item.get("last_run_status") in {"FAILED", "ERROR"}
            ]
            if not failed:
                raise ValueError("No failing automation execution is linked to this gap.")
            latest_failure = self._latest_automation_run(failed)
            return {
                "status": "available",
                "project_id": row.project_id,
                "run_id": latest_failure.get("last_run_id"),
                "automation": latest_failure,
            }

        raise ValueError("Unsupported Quality Gap action.")

    def _assert_real_ai_available(self) -> None:
        runtime = get_config()
        if (
            not runtime.ai.enabled
            or runtime.ai.provider.casefold() == "fake"
            or not runtime.ai.api_key.get_secret_value().strip()
        ):
            raise DiscoveryBlocked("This action requires a configured real AI provider; no draft was generated.")

    async def _create_requirement_draft(self, run_id: str, gap_id: str) -> dict[str, Any]:
        from project_model.models import RequirementCreate, RequirementStatus

        for attempt in range(5):
            try:
                async with self.session_factory() as session:
                    repo = QualityDiscoveryRepository(session)
                    row = await repo.get(run_id)
                    if row is None:
                        raise ValueError("Quality Discovery run not found.")
                    result = json.loads(json.dumps(row.result or {}))
                    recorded = (result.get("gap_actions") or {}).get(gap_id, {}).get("create_requirement_draft")
                    if recorded:
                        return recorded
                    gap = next((item for item in result.get("gaps", []) if item.get("id") == gap_id), None)
                    feature = next(
                        (
                            item
                            for item in result.get("features", [])
                            if item.get("feature_id") == (gap or {}).get("item_id")
                        ),
                        None,
                    )
                    if gap is None or feature is None:
                        raise ValueError("Quality gap not found or is not linked to a product feature.")
                    existing = (result.get("requirement_drafts") or {}).get(feature["feature_id"])
                    if existing:
                        return {"requirement_id": existing, "status": "DRAFT", "created": False}
                    criteria = [
                        criterion
                        for item in result.get("requirements", [])
                        if item.get("source_id") == "PASTED"
                        and self._similarity(item.get("feature", ""), feature["name"]) >= 0.34
                        for criterion in item.get("acceptance_criteria", [])
                    ]
                    source_text = row.requirement_text or ""
                    description = (
                        feature.get("description")
                        or f"功能由 Quality Discovery 在 {feature.get('page') or row.start_url} 上观察到。"
                    )
                    requirement = await RequirementRepository(session).create(
                        RequirementCreate(
                            project_id=row.project_id,
                            title=f"{feature['name']} — Discovery Draft"[:200],
                            description=(description + (f"\n\n来源需求：{source_text[:1500]}" if source_text else ""))[
                                :5000
                            ],
                            acceptance_criteria="\n".join(item for item in criteria if item)[:5000],
                            status=RequirementStatus.DRAFT,
                        )
                    )
                    response = {"requirement_id": requirement.id, "status": "DRAFT", "created": True}
                    self._apply_gap_action_result(
                        result,
                        gap_id,
                        "create_requirement_draft",
                        response,
                        feature["feature_id"],
                    )
                    row.result = result
                    row.updated_at = utc_now()
                    await session.commit()
                    return response
            except (StaleDataError, OperationalError) as exc:
                if not self._is_retryable_write_conflict(exc) or attempt == 4:
                    raise
                await asyncio.sleep(0.01 * (attempt + 1))
        raise RuntimeError("Could not persist the Requirement draft action.")

    async def _record_gap_action(
        self,
        run_id: str,
        gap_id: str,
        action: str,
        response: dict[str, Any],
        *,
        feature_id: str | None = None,
    ) -> None:
        def change(result):
            self._apply_gap_action_result(result, gap_id, action, response, feature_id)

        await self._change_result(run_id, change)
        await self._build_quality_map(run_id)

    @staticmethod
    def _apply_gap_action_result(
        result: dict[str, Any],
        gap_id: str,
        action: str,
        response: dict[str, Any],
        feature_id: str | None,
    ) -> None:
        result.setdefault("gap_actions", {}).setdefault(gap_id, {})[action] = response
        if action != "create_requirement_draft" or not feature_id:
            return
        requirement_id = response["requirement_id"]
        result.setdefault("requirement_drafts", {})[feature_id] = requirement_id
        feature = next((item for item in result.get("features", []) if item.get("feature_id") == feature_id), None)
        if feature is None:
            return
        requirement_item_id = f"{requirement_id}:REQ-001"
        feature.setdefault("requirement_ids", [])
        if requirement_item_id not in feature["requirement_ids"]:
            feature["requirement_ids"].append(requirement_item_id)
        if not any(item.get("id") == requirement_item_id for item in result.setdefault("requirements", [])):
            result["requirements"].append(
                {
                    "id": requirement_item_id,
                    "source_id": requirement_id,
                    "feature": feature.get("name", "Feature"),
                    "expected_behavior": feature.get("description", ""),
                    "acceptance_criteria": [],
                    "checks": [],
                    "ambiguous": False,
                    "draft": True,
                    "check_status": "NOT_RUN",
                    "status": "NOT_VERIFIED",
                }
            )
        model_data = result.get("requirement_model") or {"source_id": "PASTED", "features": [], "ambiguities": []}
        expectation = {
            "id": requirement_item_id,
            "source_id": requirement_id,
            "feature": feature.get("name", "Feature"),
            "expected_behavior": feature.get("description", ""),
            "risk": "high" if feature.get("coverage_status") == "NOT_COVERED" else "medium",
        }
        if not any(item.get("id") == requirement_item_id for item in model_data.get("features", [])):
            model_data.setdefault("features", []).append(expectation)
        model_data["source_id"] = requirement_id
        result["requirement_model"] = StructuredRequirementModel.model_validate(model_data).model_dump(mode="json")

    async def pause(self, run_id: str) -> QualityDiscoveryRunORM | None:
        row = await self.get(run_id)
        if row is None or row.status not in {DiscoveryStatus.QUEUED.value, DiscoveryStatus.RUNNING.value}:
            return None
        self._resume_events.setdefault(run_id, asyncio.Event()).clear()
        return await self._update(run_id, status=DiscoveryStatus.PAUSED.value)

    async def resume(self, run_id: str) -> QualityDiscoveryRunORM | None:
        row = await self.get(run_id)
        if row is None or row.status not in {DiscoveryStatus.PAUSED.value, DiscoveryStatus.RUNNING.value}:
            return None
        resume_event = self._resume_events.setdefault(run_id, asyncio.Event())
        resume_event.set()
        self._stop_events.setdefault(run_id, asyncio.Event()).clear()
        if row.status == DiscoveryStatus.PAUSED.value:
            await self._update(run_id, status=DiscoveryStatus.RUNNING.value)
        active = self._tasks.get(run_id)
        if active is None or active.done():
            self._schedule(run_id)
        return await self.get(run_id)

    async def stop(self, run_id: str) -> QualityDiscoveryRunORM | None:
        row = await self.get(run_id)
        if row is None or row.status in self.TERMINAL:
            return None
        self._stop_events.setdefault(run_id, asyncio.Event()).set()
        resume_event = self._resume_events.setdefault(run_id, asyncio.Event())
        resume_event.set()
        if run_id not in self._tasks or self._tasks[run_id].done():
            row = await self._update(run_id, status=DiscoveryStatus.STOPPED.value, finished_at=utc_now())
            await self._event(run_id, "run.stopped", "用户停止了探索。")
            return row
        return await self.get(run_id)

    def _schedule(self, run_id: str) -> None:
        active = self._tasks.get(run_id)
        if active is not None and not active.done():
            return
        self._resume_events.setdefault(run_id, asyncio.Event()).set()
        self._stop_events.setdefault(run_id, asyncio.Event()).clear()
        task = asyncio.create_task(self._execute(run_id), name=f"quality-discovery:{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed, key=run_id: self._tasks.pop(key, None))

    async def _execute(self, run_id: str) -> None:
        session_id: str | None = None
        try:
            row = await self.get(run_id)
            if row is None or row.status in self.TERMINAL:
                return
            config = get_config().discovery
            result = json.loads(json.dumps(row.result or {}))
            runtime = get_config()
            await self._change_result(
                run_id,
                lambda current: current.update(
                    {
                        "runtime_config": {
                            "ai_provider": runtime.ai.provider,
                            "ai_model": runtime.ai.model,
                            "jev_provider": runtime.jev.provider,
                            "jev_model": runtime.jev.model,
                            "require_ai": config.require_ai,
                            "require_jev": config.require_jev,
                            "safe_mode": config.safe_mode,
                            "max_actions": config.max_actions,
                            "max_states": config.max_states,
                            "max_depth": config.max_depth,
                            "max_candidates": config.max_candidates,
                            "feature_mapping_confidence": config.feature_mapping_confidence,
                        }
                    }
                ),
            )
            self._assert_runtime_ready(config)
            await self._update(run_id, status=DiscoveryStatus.RUNNING.value, error=None)
            await self._event(run_id, "run.started", "正在初始化产品探索。")
            requirement_input = await self._requirement_input(row)
            if requirement_input and not result.get("requirements"):
                analysis = await self._analyze_requirements(run_id, requirement_input)
                result = await self._append_requirements(run_id, analysis)
            allow_cart_mutation = row.mode in {DiscoveryMode.VALIDATE.value, DiscoveryMode.AUDIT.value} and bool(
                requirement_input and self._requirement_allows_cart_mutation(requirement_input["text"])
            )
            allow_repeat_cart_mutation = allow_cart_mutation and bool(
                requirement_input and self._requirement_allows_repeat_cart_mutation(requirement_input["text"])
            )
            allowed_hosts = self._allowed_hosts(row)
            session = await self.browser_runtime.create_session(block_service_workers=True)
            session_id = session.id
            restrict_navigation = getattr(self.browser_runtime, "restrict_navigation", None)
            if callable(restrict_navigation):
                await restrict_navigation(session_id, allowed_hosts)
            resume_url = self._resume_url(result, row.start_url)
            response_status = await self.browser_runtime.navigate(session_id, resume_url)
            page = await self.browser_runtime.get_page(session_id)
            if not self._host_allowed(page.url, allowed_hosts):
                raise DiscoveryBlocked("Navigation redirected outside the start domain and allowed domain list.")
            if response_status is not None and response_status >= 500:
                raise DiscoveryBlocked(f"Start URL returned HTTP {response_status}; exploration stopped.")

            started = time.monotonic()
            persisted_elapsed = max(0.0, (utc_now() - row.created_at).total_seconds())
            max_runtime = config.max_runtime_minutes * 60
            while True:
                await self._wait_if_paused(run_id)
                if self._stop_events[run_id].is_set():
                    await self._finish(run_id, DiscoveryStatus.STOPPED.value, "用户停止了探索。")
                    return
                current = await self.get(run_id)
                if current is None:
                    return
                current_result = current.result or {}
                action_count = len(current_result.get("actions") or [])
                failures = sum(
                    action.get("status") in {"FAILED", "TARGET_NOT_VERIFIED", "BLOCKED_BY_DOMAIN_POLICY"}
                    for action in current_result.get("actions") or []
                )
                if (
                    action_count >= config.max_actions
                    or max(persisted_elapsed, time.monotonic() - started) >= max_runtime
                ):
                    await self._finish(run_id, DiscoveryStatus.BUDGET_EXHAUSTED.value, "探索预算已达到配置上限。")
                    await self._build_quality_map(run_id)
                    return
                if failures >= config.max_failures:
                    await self._finish(run_id, DiscoveryStatus.BUDGET_EXHAUSTED.value, "已达到最大失败动作数量上限。")
                    await self._build_quality_map(run_id)
                    return

                snapshot = await self.browser_runtime.snapshot(
                    session_id,
                    include_screenshot=config.screenshot,
                    full_page=True,
                )
                if not self._host_allowed(snapshot.url, allowed_hosts):
                    raise DiscoveryBlocked("The current page left the start domain and allowed domain list.")
                controls = self._safe_controls(snapshot.controls)
                scroll = await page.evaluate(
                    "() => ({y: Math.round(window.scrollY), height: document.documentElement.scrollHeight, viewport: window.innerHeight})"
                )
                state_id, fingerprint = self._state_fingerprint(snapshot, controls, scroll)
                similar_state = self._find_similar_state(
                    current_result, snapshot, controls, config.state_similarity_threshold
                )
                state = self._state_record(snapshot, controls, scroll, state_id, fingerprint)
                if not config.capture_console:
                    state["console_errors"] = []
                if not config.capture_network:
                    state["network"] = {"responses": {}, "failures": 0, "sample_count": 0}
                if similar_state and not self._find_state(current_result, fingerprint):
                    state["similar_to_state_id"] = similar_state["state_id"]
                    state["similarity"] = similar_state["score"]
                if (
                    not self._find_state(current_result, fingerprint)
                    and len(current_result.get("states") or []) >= config.max_states
                ):
                    await self._finish(run_id, DiscoveryStatus.BUDGET_EXHAUSTED.value, "已达到最大产品状态数量上限。")
                    await self._build_quality_map(run_id)
                    return
                screenshot_count = sum(
                    bool(item.get("screenshot_evidence_id")) for item in current_result.get("states", [])
                )
                if not self._find_state(current_result, fingerprint):
                    state["evidence_id"] = await self._save_state_evidence(run_id, state_id, state)
                if (
                    snapshot.screenshot
                    and screenshot_count < config.max_screenshots
                    and not self._find_state(current_result, fingerprint)
                ):
                    state["screenshot_evidence_id"] = await self._save_screenshot(run_id, state_id, snapshot.screenshot)
                result = await self._upsert_state(run_id, state)
                state = self._find_state(result, fingerprint) or state
                if row.mode == DiscoveryMode.VALIDATE.value and self._all_acceptance_criteria_passed(
                    result.get("requirements") or [],
                    result.get("states") or [],
                    result.get("edges") or [],
                    result.get("actions") or [],
                ):
                    await self._finish(run_id, DiscoveryStatus.COMPLETED.value, None)
                    await self._build_quality_map(run_id)
                    return
                safe_title = self._safe_title(snapshot.title)
                await self._event(
                    run_id,
                    "state.observed",
                    f"已观察：{safe_title or self._safe_url(snapshot.url)}",
                    {"state_id": state_id},
                )

                depth_limited = int(state.get("depth", 0)) >= config.max_depth
                blocked_candidates = self._blocked_candidates(
                    state, allowed_hosts, allow_cart_mutation=allow_cart_mutation
                )
                await self._record_frontier(
                    run_id, state_id, blocked_candidates, "BLOCKED_BY_POLICY", "安全策略禁止执行此动作。"
                )
                candidates = self._candidate_actions(
                    state,
                    allowed_hosts,
                    len(state.get("controls", [])) + 1,
                    allow_cart_mutation=allow_cart_mutation,
                    skip_empty_cart_revisit=(
                        not allow_cart_mutation and self._has_observed_empty_cart(current_result.get("states") or [])
                    ),
                )
                attempted = set(state.get("attempted_candidate_ids") or [])
                skipped = set(state.get("skipped_candidate_ids") or [])
                handled = attempted | skipped
                pending = [candidate for candidate in candidates if candidate["candidate_id"] not in handled]
                pending = self._prioritize_variant_actions_before_cart(
                    pending,
                    current_result.get("actions") or [],
                    current_result.get("states") or [],
                    state,
                )
                pending = self._prioritize_cart_verification_after_add(
                    pending,
                    state,
                    current_result.get("actions") or [],
                    current_result.get("states") or [],
                    allow_repeat_same_variant=allow_repeat_cart_mutation,
                )
                if depth_limited and pending:
                    await self._record_frontier(
                        run_id, state_id, pending, "PENDING", "当前状态已达到探索深度上限，候选动作未执行。"
                    )
                    await self._finish(
                        run_id,
                        DiscoveryStatus.BUDGET_EXHAUSTED.value,
                        "已达到最大探索深度，当前状态仍有未检查的安全控件。",
                    )
                    await self._build_quality_map(run_id)
                    return
                if not pending and state.get("depth", 0) > 0:
                    back = self._back_candidate(current_result, state, allowed_hosts)
                    if back and back["candidate_id"] not in attempted:
                        pending = [back]
                if not pending:
                    await self._finish(run_id, DiscoveryStatus.COMPLETED.value, None)
                    await self._build_quality_map(run_id)
                    return

                if state.get("similar_to_state_id"):
                    await self._skip_candidates(
                        run_id,
                        fingerprint,
                        pending,
                        f"与代表状态 {state['similar_to_state_id']} 的页面结构相似，已跳过重复动作采样。",
                    )
                    continue

                all_pending = pending
                pending = all_pending[: config.max_candidates]
                await self._record_frontier(run_id, state_id, all_pending, "PENDING", "安全候选动作等待 Jev 分批选择。")
                plan = await self._plan_next(run_id, row, snapshot, state, pending, result.get("requirements") or [])
                await self._record_ai(run_id, plan.pop("_usage"))
                result = await self._record_features(run_id, plan, state)
                for candidate in pending:
                    if candidate.get("action_type") == "search":
                        candidate["value"] = self._search_value_for_goal(
                            state,
                            plan,
                            result.get("requirements") or [],
                            current_result.get("actions") or [],
                            current_result.get("states") or [],
                        )
                await self._set_state_page_type(run_id, fingerprint, plan.get("page_type", "unknown"))
                # AI may prioritize candidates, but it cannot remove service-generated safe options.
                suggested = [
                    key for key in plan.get("candidate_ids", []) if key in {item["candidate_id"] for item in pending}
                ]
                if plan.get("done") and not suggested:
                    await self._skip_candidates(
                        run_id,
                        fingerprint,
                        pending,
                        "AI marked these remaining actions as having no meaningful exploration value.",
                    )
                    if len(all_pending) > len(pending):
                        continue
                    await self._finish(run_id, DiscoveryStatus.COMPLETED.value, None)
                    await self._build_quality_map(run_id)
                    return
                ordered_pending = sorted(
                    pending,
                    key=lambda item: (
                        suggested.index(item["candidate_id"]) if item["candidate_id"] in suggested else len(suggested)
                    ),
                )
                decision_pending = self._filter_repeated_search_candidates(
                    ordered_pending, current_result.get("actions") or []
                )
                decision_pending = self._filter_repeated_select_candidates(
                    decision_pending,
                    current_result.get("actions") or [],
                    current_result.get("states") or [],
                    state,
                    allow_repeat_same_variant=allow_repeat_cart_mutation,
                )
                decision_candidate_ids = {item["candidate_id"] for item in decision_pending}
                repeated_searches = [
                    item
                    for item in ordered_pending
                    if item["candidate_id"] not in decision_candidate_ids and item.get("action_type") == "search"
                ]
                repeated_selections = [
                    item
                    for item in ordered_pending
                    if item["candidate_id"] not in decision_candidate_ids and item.get("action_type") == "select"
                ]
                if repeated_searches:
                    await self._skip_candidates(
                        run_id,
                        fingerprint,
                        repeated_searches,
                        "本次探索已经执行过通用搜索，跳过重复搜索以检查其他功能。",
                    )
                if repeated_selections:
                    await self._skip_candidates(
                        run_id,
                        fingerprint,
                        repeated_selections,
                        "当前商品的该规格控件已经产生过一次状态变化，跳过重复切换。",
                    )
                if not decision_pending:
                    if len(all_pending) > len(pending):
                        continue
                    await self._finish(run_id, DiscoveryStatus.COMPLETED.value, None)
                    await self._build_quality_map(run_id)
                    return
                choices = {item["candidate_id"]: item for item in decision_pending}
                suggested = [candidate_id for candidate_id in suggested if candidate_id in choices]
                decision = await self.decisions.choose(
                    DecisionRequest(
                        name="exploration_action_selection",
                        state={
                            "state_id": state_id,
                            "url": self._safe_url(snapshot.url),
                            "page_type": plan.get("page_type", "unknown"),
                            "goal": row.mode,
                            "active_goal": self._active_goal_context(
                                plan,
                                result.get("requirements") or [],
                                current_result.get("actions") or [],
                                current_result.get("states") or [],
                            ),
                            "planner_guidance": {
                                "goals": plan.get("goals", [])[:10],
                                "priority_candidate_ids": suggested,
                            },
                            "candidates": [
                                {
                                    "key": candidate_id,
                                    "action": candidate["action_type"],
                                    "target": candidate["target"],
                                    "expected_effect": candidate["expected_effect"],
                                    "target_role": candidate.get("target_role"),
                                    "target_tag": candidate.get("target_tag"),
                                    "operation": candidate.get("operation"),
                                    "planner_priority": (
                                        suggested.index(candidate_id) + 1 if candidate_id in suggested else None
                                    ),
                                }
                                for candidate_id, candidate in choices.items()
                            ],
                        },
                        options=[
                            DecisionOption(
                                key=candidate_id,
                                description=(
                                    f"AI planner priority {suggested.index(candidate_id) + 1}; "
                                    if candidate_id in suggested
                                    else ""
                                )
                                + f"{candidate['action_type']} {candidate['target']}: {candidate['expected_effect']}"[
                                    :1000
                                ],
                            )
                            for candidate_id, candidate in choices.items()
                        ],
                        instructions=(
                            "若提供 active_goal，先按该目标及其关联验收标准选择最相关的安全动作；"
                            "否则根据当前模式和未覆盖的规划目标推进最高优先级目标。"
                            "候选按 AI planner 的目标相关性排序；优先选择排名靠前且与当前状态相符的动作。"
                            "若排序靠前的动作有具体状态或安全冲突，才选择其他候选或拒绝。"
                            "confidence 表示当前动作作为有证据支持的下一步的把握，不表示其他候选都无效。"
                            "多步验收标准应按步骤逐步验证；不要要求单个中间动作独立完成整条验收标准。"
                            "选项仅来自服务端观察到的安全控件；必须原样返回其中一个 key，不得发明动作。"
                        ),
                    ),
                    run_id=run_id,
                )
                decision_id = uuid4().hex
                await self._record_decision(
                    run_id,
                    decision,
                    decision_id=decision_id,
                    candidate_ids=list(choices),
                    priority_candidate_ids=suggested,
                )
                if not decision.choice or decision.choice not in choices:
                    await self._record_frontier(
                        run_id, state_id, pending, "BLOCKED", "Jev 未返回有效候选；动作未执行。"
                    )
                    raise DiscoveryBlocked("Jev 未返回可执行的候选动作。")
                if config.require_jev and decision.fallback_used:
                    await self._record_frontier(
                        run_id, state_id, pending, "BLOCKED", "Jev fallback 被配置禁止；动作未执行。"
                    )
                    raise DiscoveryBlocked("Jev 不可用或置信度不足；按配置停止，未执行候选动作。")
                selected = choices[decision.choice]
                await self._record_frontier(run_id, state_id, [selected], "SELECTED", "Jev 选择了此候选动作。")
                await self._event(
                    run_id,
                    "decision.selected",
                    f"Jev 选择：{selected['target']}",
                    {
                        "candidate_id": decision.choice,
                        "decision_id": decision_id,
                        "candidate_count": len(choices),
                        "provider": decision.provider,
                        "fallback_used": decision.fallback_used,
                    },
                )
                await self._execute_candidate(run_id, session_id, state, selected, decision_id=decision_id)
                await self._wait_if_paused(run_id)
        except asyncio.CancelledError:
            raise
        except DiscoveryBlocked as error:
            await self._finish(run_id, DiscoveryStatus.BLOCKED.value, self._safe_error(error))
            await self._build_quality_map(run_id)
        except Exception as error:
            await self._finish(run_id, DiscoveryStatus.FAILED.value, self._safe_error(error))
            await self._build_quality_map(run_id)
        finally:
            if session_id:
                await self.browser_runtime.close_session(session_id)

    async def _requirement_input(self, row: QualityDiscoveryRunORM) -> dict[str, str] | None:
        text = row.requirement_text
        if row.requirement_id:
            async with self.session_factory() as session:
                requirement = await RequirementRepository(session).get_by_id(row.requirement_id)
            if requirement is None:
                raise DiscoveryBlocked("Selected Requirement no longer exists.")
            text = "\n".join(
                part for part in (requirement.title, requirement.description, requirement.acceptance_criteria) if part
            )
        if not text.strip():
            return None
        return {"text": text[:20_000], "source_id": row.requirement_id or "PASTED"}

    @staticmethod
    def _requirement_analysis_chunks(text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        criterion_pattern = re.compile(r"^(?:AC[-_]?\d+\s*:|[A-Z][A-Z0-9_-]{0,15}\d+\s*:|[-*•]\s+|\d+[.)]\s+)", re.I)
        criteria = [line for line in lines if criterion_pattern.match(line)]
        context = [line for line in lines if not criterion_pattern.match(line)]
        if len(criteria) > 1:
            prefix = "\n".join(context)
            return [
                "\n".join(part for part in (prefix, *criteria[index : index + 2]) if part)
                for index in range(0, len(criteria), 2)
            ]

        if len(text) <= 1800:
            return [text]
        pieces = [piece.strip() for piece in re.split(r"(?<=[.!?。！？])\s*|\r?\n+", text) if piece.strip()]
        chunks: list[str] = []
        current = ""
        for piece in pieces:
            while len(piece) > 1800:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(piece[:1800])
                piece = piece[1800:]
            if current and len(current) + len(piece) + 1 > 1800:
                chunks.append(current)
                current = ""
            current = f"{current}\n{piece}" if current else piece
        if current:
            chunks.append(current)
        return chunks or [text]

    async def _analyze_requirements(self, run_id: str, requirement: dict[str, str]) -> dict[str, Any]:
        provider = self.provider_factory()
        requirements_by_feature: dict[str, dict[str, Any]] = {}
        ambiguities: list[str] = []
        explicit_criteria = {
            criterion_id
            for line in requirement["text"].splitlines()
            if (criterion_id := self._criterion_id(line))
            and self._is_explicit_acceptance_criterion(line, requirement["text"])
        }
        for chunk in self._requirement_analysis_chunks(requirement["text"]):
            response = await provider.complete(
                AICompletionRequest(
                    run_id=run_id,
                    prompt=json.dumps({"source_id": requirement["source_id"], "text": chunk}, ensure_ascii=False),
                    system_instruction=(
                        "Analyze this part of a QA requirement. Return only the declared compact schema. "
                        "Group related criteria into at most four features. Keep expected_behavior to one short sentence and copy each criterion verbatim once. "
                        "List ambiguity rather than inventing details. A concrete acceptance criterion with a stated action and observable outcome is not ambiguous merely because a surrounding user story is broad. "
                        "Mark a criterion ambiguous only when it is internally conflicting or lacks information needed to distinguish plausible outcomes, and identify that missing detail. "
                        "Extract checks only for directly observable enabled/selected state or exact visible text. "
                        "For visible checks, use a literal target quoted in the criterion; do not infer targets. "
                        "Use when=after_action for results expected after interaction and size-specific conditions only when stated. "
                        "Copy the source criterion exactly into check.criterion. A page transition alone does not prove a business outcome."
                    ),
                    response_schema=RequirementAnalysis,
                    prompt_id="quality_discovery_requirements",
                    prompt_version="1",
                    temperature=0.1,
                    max_tokens=1600,
                    timeout_seconds=30,
                    thinking_mode=self._provider_thinking_mode(),
                    max_retries=0,
                )
            )
            compact = RequirementAnalysis.model_validate(response.structured_data or json.loads(response.content))
            await self._record_ai(
                run_id,
                {
                    "provider": response.provider,
                    "model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            )
            for item in compact.requirements:
                signal = RequirementSignal.model_validate(item.model_dump(mode="json")).model_dump(mode="json")
                criteria = signal.get("acceptance_criteria") or []
                if criteria and all(self._criterion_id(criterion) in explicit_criteria for criterion in criteria):
                    signal["ambiguous"] = False
                key = signal["feature"].strip().casefold()
                existing = requirements_by_feature.get(key)
                if existing is None:
                    requirements_by_feature[key] = signal
                    continue
                existing["acceptance_criteria"] = list(
                    dict.fromkeys([*existing["acceptance_criteria"], *signal["acceptance_criteria"]])
                )
                checks = {json.dumps(check, sort_keys=True): check for check in existing["checks"]}
                checks.update({json.dumps(check, sort_keys=True): check for check in signal["checks"]})
                existing["checks"] = list(checks.values())[:8]
                existing["ambiguous"] = existing["ambiguous"] or signal["ambiguous"]
                if existing["risk"] == "unknown":
                    existing["risk"] = signal["risk"]
            ambiguities.extend(
                item
                for item in compact.ambiguities
                if self._criterion_id(item) not in explicit_criteria and item not in ambiguities
            )

        data = {"requirements": list(requirements_by_feature.values()), "ambiguities": ambiguities[:20]}
        for index, item in enumerate(data["requirements"], start=1):
            item["id"] = f"{requirement['source_id']}:REQ-{index:03d}"
            item["source_id"] = requirement["source_id"]
        structured = StructuredRequirementModel.model_validate(
            {
                "source_id": requirement["source_id"],
                "features": [
                    {key: value for key, value in item.items() if key != "checks"} for item in data["requirements"]
                ],
                "ambiguities": data["ambiguities"],
            }
        )
        result = {
            "requirements": data["requirements"],
            "requirement_model": structured.model_dump(mode="json"),
            "ambiguities": data["ambiguities"],
        }
        await self._event(run_id, "requirement.analyzed", f"已结构化 {len(data['requirements'])} 个需求点。")
        return result

    @staticmethod
    def _criterion_id(value: str) -> str | None:
        match = re.match(r"\s*(AC[-_]?\d+)\s*:", str(value), re.I)
        return re.sub(r"[-_]", "", match.group(1)).casefold() if match else None

    @staticmethod
    def _is_explicit_acceptance_criterion(criterion: str, requirement_text: str = "") -> bool:
        text = criterion.casefold()
        empty_state_is_explicit = (
            re.search(r"无匹配|没有匹配|no\s+matches?", text, re.I)
            and re.search(r"明确空状态|清晰空状态|空状态|empty\s+state", text, re.I)
            and re.search(r"无商品卡片|不显示商品卡片|no\s+product\s+cards?", text, re.I)
        )
        if empty_state_is_explicit:
            return True

        same_variant_repeat_is_explicit = (
            re.search(r"重复|再次|again|repeatedly|twice", text, re.I)
            and re.search(r"相同|同一|same", text, re.I)
            and re.search(r"规格|variant|sku", text, re.I)
            and re.search(r"合并|merge", text, re.I)
            and re.search(r"数量|件数|quantity|count", text, re.I)
            and re.search(r"重新计算|重算|recalculat", text, re.I)
            and re.search(r"金额|总价|价格|amount|total|price", text, re.I)
            and re.search(
                r"价格\s*乘\s*数量|单价.{0,12}数量|price\s*(?:[×x*]|times)\s*(?:the\s+)?(?:quantity|qty)|"
                r"price.{0,24}(?:quantity|qty)",
                requirement_text,
                re.I,
            )
        )
        return bool(same_variant_repeat_is_explicit)

    async def _plan_next(
        self,
        run_id: str,
        row: QualityDiscoveryRunORM,
        snapshot,
        state: dict[str, Any],
        candidates: list[dict[str, Any]],
        requirements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        provider = self.provider_factory()
        prompt = {
            "mode": row.mode,
            "requirements": requirements[:20],
            "observation": {
                "url": self._safe_url(snapshot.url),
                "title": self._safe_title(snapshot.title),
                "visible_text": SensitiveRedactor.redact_text(snapshot.text[:5000]),
                "accessibility_tree": SensitiveRedactor.redact_text(snapshot.accessibility_tree[:8000]),
                "controls": state["controls"][:40],
                "network": self._network_summary(snapshot.network),
                "state_id": state["state_id"],
            },
            "candidates": [
                {
                    key: candidate.get(key)
                    for key in ("candidate_id", "action_type", "target_id", "target", "expected_effect")
                }
                for candidate in candidates
            ],
            "requested_output": "Return page_type, evidence-grounded feature signals, concise exploration goals linked to requirements when possible, and safe candidate_ids only.",
            "rule": "Return only candidate_ids supplied above. A feature signal must cite a visible target_id or exact visible evidence_text.",
        }
        response = await provider.complete(
            AICompletionRequest(
                run_id=run_id,
                prompt=json.dumps(prompt, ensure_ascii=False, separators=(",", ":")),
                system_instruction=(
                    "You are the page-understanding and exploration-planning component of a QA discovery workflow. "
                    "AI proposes; Jev makes the action choice; the browser service executes only its returned choice. "
                    "Return concise exploration goals, preferring requirement-linked and high-risk behavior not yet covered by this graph. "
                    "Report only capabilities supported by the current page. Never invent selectors or IDs. "
                    "Never propose payment, checkout, order placement, account changes, submission of arbitrary forms, deletion, or external navigation. "
                    "Return a compact structured plan and no chain of thought."
                ),
                response_schema=DiscoveryPlan,
                prompt_id="quality_discovery_planning",
                prompt_version="1",
                temperature=0.1,
                max_tokens=1800,
                timeout_seconds=20,
                thinking_mode=self._provider_thinking_mode(),
                max_retries=0,
            )
        )
        plan = DiscoveryPlan.model_validate(response.structured_data or json.loads(response.content)).model_dump(
            mode="json"
        )
        plan["_usage"] = {
            "provider": response.provider,
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }
        return plan

    async def _execute_candidate(
        self,
        run_id: str,
        session_id: str,
        state: dict[str, Any],
        candidate: dict[str, Any],
        *,
        decision_id: str | None = None,
    ) -> None:
        action_type = candidate["action_type"]
        locator = candidate.get("locator") or {"kind": "page", "value": ""}
        event_action = candidate.get("operation") or {
            "navigate": "click",
            "search": "press",
            "filter": "click",
            "scroll": "scroll",
            "back": "click",
        }.get(action_type, action_type)
        verified = True
        if action_type not in {"scroll", "back"}:
            verification = await self.browser_runtime.verify_locator(session_id, locator, {"action": event_action})
            verified = bool(verification.get("verified"))
        action_record = {
            "candidate_id": candidate["candidate_id"],
            "from_state_id": state["state_id"],
            "target_id": candidate.get("target_id"),
            "action_type": action_type,
            "target": candidate["target"],
            "expected_effect": candidate["expected_effect"],
            "selected_value": candidate.get("value") if action_type == "select" else None,
            "search_value": candidate.get("value") if action_type == "search" else None,
            "cart_variant_key": candidate.get("cart_variant_key")
            if self._is_cart_mutation_label(candidate["target"])
            else None,
            "jev_choice": candidate["candidate_id"],
            "jev_decision_id": decision_id,
            "status": "STARTED" if verified else "TARGET_NOT_VERIFIED",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._mark_attempted(run_id, state["fingerprint"], candidate["candidate_id"])
        if not verified:
            action_record["status"] = "FAILED"
            action_record["error"] = "Observed target was no longer uniquely visible and enabled."
            await self._append_action(run_id, action_record)
            await self._record_frontier(run_id, state["state_id"], [candidate], "FAILED", action_record["error"])
            await self._event(run_id, "action.failed", f"目标验证失败：{candidate['target']}")
            return
        await self._event(
            run_id,
            "action.started",
            f"正在执行：{candidate['action_type']} {candidate['target']}",
            {"candidate_id": candidate["candidate_id"]},
        )
        try:
            if action_type == "back":
                result = await self.browser_runtime.navigate(session_id, candidate["value"], timeout_ms=10_000)
            elif action_type == "navigate":
                result = await self.browser_runtime.execute_action(
                    session_id, locator, {"type": "click", "timeout_ms": 10_000}
                )
            elif action_type == "fill":
                result = await self.browser_runtime.execute_action(
                    session_id, locator, {"type": "fill", "value": candidate.get("value", ""), "timeout_ms": 10_000}
                )
            elif action_type == "search":
                if candidate.get("operation") == "click":
                    result = await self.browser_runtime.execute_action(
                        session_id, locator, {"type": "click", "timeout_ms": 10_000}
                    )
                else:
                    await self.browser_runtime.execute_action(
                        session_id,
                        locator,
                        {"type": "fill", "value": candidate.get("value", "qa sample"), "timeout_ms": 10_000},
                    )
                    result = await self.browser_runtime.execute_action(
                        session_id, locator, {"type": "press", "value": "Enter", "timeout_ms": 10_000}
                    )
            elif action_type == "select":
                result = await self.browser_runtime.execute_action(
                    session_id, locator, {"type": "select", "value": candidate.get("value", ""), "timeout_ms": 10_000}
                )
            elif action_type == "press":
                result = await self.browser_runtime.execute_action(
                    session_id,
                    locator,
                    {"type": "press", "value": candidate.get("value", "Enter"), "timeout_ms": 10_000},
                )
            else:
                result = await self.browser_runtime.execute_action(
                    session_id, locator, {"type": action_type, "value": candidate.get("value"), "timeout_ms": 10_000}
                )
            action_record["status"] = "EXECUTED"
            action_record["result"] = str(result)[:160] if result is not None else None
            page = await self.browser_runtime.get_page(session_id)
            action_record["url_after"] = self._safe_url(page.url)
            current_run = await self.get(run_id)
            if current_run and not self._host_allowed(page.url, self._allowed_hosts(current_run)):
                action_record["status"] = "BLOCKED_BY_DOMAIN_POLICY"
                action_record["finished_at"] = datetime.now(timezone.utc).isoformat()
                await self._append_action(run_id, action_record)
                raise DiscoveryBlocked("Action navigated outside the start domain and allowed domain list.")
            action_record["finished_at"] = datetime.now(timezone.utc).isoformat()
            await self._append_action(run_id, action_record)
            await self._record_frontier(
                run_id, state["state_id"], [candidate], "EXECUTED", "浏览器动作已执行，等待状态观察。"
            )
            await self._event(run_id, "action.completed", f"已执行：{candidate['target']}")
            # Re-observe without a second screenshot to verify a real state transition.
            after = await self.browser_runtime.snapshot(session_id, include_screenshot=False)
            after_controls = self._safe_controls(after.controls)
            after_scroll = await page.evaluate(
                "() => ({y: Math.round(window.scrollY), height: document.documentElement.scrollHeight, viewport: window.innerHeight})"
            )
            _after_state_id, after_fingerprint = self._state_fingerprint(after, after_controls, after_scroll)
            changed = after_fingerprint != state["fingerprint"]
            action_record["state_changed"] = changed
            action_record["to_fingerprint"] = after_fingerprint
            await self._replace_action(run_id, action_record)
            await self._link_feature_evidence(run_id, state, candidate, changed)
            await self._append_edge(run_id, state["state_id"], after_fingerprint, candidate)
            await self._event(
                run_id,
                "action.verified" if changed else "action.no_state_change",
                "浏览器状态已变化。" if changed else "执行后未观察到页面状态变化。",
                {"candidate_id": candidate["candidate_id"], "state_changed": changed},
            )
        except DiscoveryBlocked:
            raise
        except Exception as error:
            action_record["status"] = "FAILED"
            action_record["error"] = self._safe_error(error, limit=240)
            action_record["finished_at"] = datetime.now(timezone.utc).isoformat()
            await self._append_action(run_id, action_record)
            await self._record_frontier(run_id, state["state_id"], [candidate], "FAILED", action_record["error"])
            await self._event(run_id, "action.failed", f"动作失败：{candidate['target']}")

    def _candidate_actions(
        self,
        state: dict[str, Any],
        allowed_hosts: set[str],
        limit: int,
        *,
        depth_limited: bool = False,
        allow_cart_mutation: bool = False,
        skip_empty_cart_revisit: bool = False,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        state_id = state["state_id"]
        has_search_input = any(
            control.get("tag") == "input"
            and str(control.get("type") or "").lower() in {"search", "text"}
            and re.search(
                r"search|查询|搜索",
                str(control.get("name") or control.get("placeholder") or ""),
                re.I,
            )
            for control in state["controls"]
        )
        cart_view_open = bool(
            re.search(
                r"shopping cart|your cart is empty|购物车为空|购物车.*空",
                f"{state.get('title', '')} {state.get('main_content', '')}",
                re.I,
            )
        )
        for control in state["controls"]:
            if depth_limited:
                break
            if len(output) >= limit:
                break
            name = str(control.get("name") or control.get("placeholder") or control.get("href") or "").strip()
            if not name:
                continue
            if not control.get("enabled", True):
                continue
            tag = str(control.get("tag") or "")
            role = str(control.get("role") or "")
            href = str(control.get("href") or "")
            input_type = str(control.get("type") or "").lower()
            if control.get("has_query") or control.get("has_credentials") or self._url_has_secret_query(href):
                continue
            href_parts = urlsplit(href)
            relative_href = bool(href) and not href_parts.scheme and not href_parts.netloc
            if href and not relative_href and not self._host_allowed(href, allowed_hosts):
                continue
            cart_mutation = self._is_cart_mutation_label(name)
            if cart_mutation and not allow_cart_mutation:
                continue
            if re.search(
                r"checkout|payment|purchase|place.?order|delete|remove|logout|sign.?out|account.?settings|支付|付款|结账|下单|删除|注销|退出登录",
                name,
                re.I,
            ):
                continue
            locator = self._locator_for_control(control)
            if locator is None:
                continue
            action_type = "click"
            safe_kind = classify_browser_action("click", name=name, tag=tag, href=href, input_type=input_type)
            if cart_mutation and allow_cart_mutation:
                safe_kind = "SAFE_INTERACTION"
            if tag == "select" and re.search(r"filter|筛选|sort|排序|color|colour|size|颜色|尺码", name, re.I):
                action_type = "select"
                safe_kind = "SAFE_INTERACTION"
            elif re.search(r"search|查询|搜索", name, re.I) and tag == "input" and input_type in {"search", "text"}:
                action_type = "search"
                safe_kind = "SAFE_INTERACTION"
            elif tag == "a" and re.search(r"search|查询|搜索", name, re.I):
                action_type = "click"
            elif tag == "button" and not has_search_input and re.search(r"search|查询|搜索", name, re.I):
                action_type = "click"
            elif re.search(r"search|查询|搜索|filter|筛选|sort|排序", name, re.I):
                action_type = "search" if re.search(r"search|查询|搜索", name, re.I) else "filter"
                safe_kind = (
                    "SAFE_INTERACTION"
                    if action_type == "search"
                    else classify_browser_action(action_type, name=name, tag=tag, href=href, input_type=input_type)
                )
            if action_type == "search" and tag != "input" and has_search_input:
                continue
            value = self._safe_search_value(state) if action_type == "search" else self._safe_select_value(control)
            if action_type == "select" and not value:
                continue
            cart_view_button = action_type == "click" and bool(
                re.fullmatch(
                    r"(?:shopping\s+)?(?:cart|bag|basket)(?:\s*\(\s*\d+\s*\))?",
                    name,
                    re.I,
                )
            )
            if (cart_view_open or skip_empty_cart_revisit) and cart_view_button:
                continue
            if action_type == "click" and re.search(
                r"back to\s+(?:products|shop|catalog|results)|continue shopping|"
                r"return to\s+(?:products|shop|catalog|results)|继续购物|返回(?:商品|产品|列表|搜索)",
                name,
                re.I,
            ):
                safe_kind = "SAFE_INTERACTION"
            if cart_view_button:
                # Opening the cart view is read-only; add/remove/checkout labels are blocked above.
                safe_kind = "READ_ONLY"
            if safe_kind not in {"READ_ONLY", "SAFE_INTERACTION"}:
                continue
            candidate_id = self._candidate_id(state_id, action_type, str(control.get("id") or control.get("index")))
            output.append(
                {
                    "candidate_id": candidate_id,
                    "action_type": action_type,
                    "target_id": f"el_{control.get('index', 0)}",
                    "target_role": role,
                    "target_tag": tag,
                    "target": name[:140],
                    "expected_effect": self._candidate_expected_effect(action_type, name, control),
                    "locator": locator,
                    "value": value,
                    "operation": "click"
                    if action_type == "search" and not (tag == "input" and input_type in {"search", "text"})
                    else None,
                    "href": href,
                    "risk": safe_kind,
                    "cart_variant_key": self._cart_variant_key(state) if cart_mutation else None,
                }
            )
        if (
            not depth_limited
            and state.get("scroll", {}).get("height", 0) > state.get("scroll", {}).get("viewport", 0)
            and len(output) < limit
        ):
            candidate_id = self._candidate_id(state_id, "scroll", "down")
            output.append(
                {
                    "candidate_id": candidate_id,
                    "action_type": "scroll",
                    "target_id": None,
                    "target": "向下滚动",
                    "expected_effect": "观察当前页面下方的功能和控件。",
                    "locator": {"kind": "page", "value": ""},
                    "value": "down",
                    "risk": "READ_ONLY",
                }
            )
        return output

    @staticmethod
    def _candidate_expected_effect(action_type: str, name: str, control: dict[str, Any]) -> str:
        label = name[:80].strip()
        if QualityDiscoveryService._is_cart_mutation_label(label):
            return "将当前商品和已选规格加入购物车，再检查商品条目、数量与金额是否符合需求。"
        if action_type == "search":
            return "提交安全搜索词，观察匹配商品列表或无匹配空状态。"
        if action_type == "filter":
            return f"应用“{label}”筛选，观察商品列表和筛选状态变化。"
        if action_type == "select":
            return f"选择一个可用的“{label}”选项，核验控件选中状态。"
        if re.search(r"cart|bag|basket|购物车|购物袋", label, re.I):
            return "打开购物车，检查商品条目、数量和金额。"
        if re.search(
            r"back to\s+(?:products|shop|catalog|results)|continue shopping|"
            r"return to\s+(?:products|shop|catalog|results)|继续购物|返回(?:商品|产品|列表|搜索)",
            label,
            re.I,
        ):
            return "返回商品列表，观察商品卡片和搜索控件是否恢复。"
        if re.search(r"view|details|product|商品|详情", label, re.I):
            return f"打开“{label}”对应的商品详情，检查名称、价格和规格控件。"
        if control.get("href") or control.get("tag") == "a":
            return f"打开站内链接“{label}”，检查目标页面标题、内容或状态。"
        return f"触发“{label}”，观察相关区域的内容、提示或控件状态变化。"

    def _blocked_candidates(
        self,
        state: dict[str, Any],
        allowed_hosts: set[str],
        *,
        allow_cart_mutation: bool = False,
    ) -> list[dict[str, Any]]:
        blocked = []
        dangerous = re.compile(
            r"checkout|payment|purchase|place.?order|delete|remove|logout|sign.?out|account.?settings|submit|支付|付款|结账|下单|删除|注销|退出登录|提交",
            re.I,
        )
        for control in state.get("controls", []):
            name = str(control.get("name") or control.get("href") or "").strip()
            href = str(control.get("href") or "")
            outside = bool(control.get("has_query") or control.get("has_credentials"))
            if href:
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc:
                    outside = outside or not self._host_allowed(href, allowed_hosts)
                elif parsed.query or parsed.fragment:
                    outside = True
            cart_blocked = self._is_cart_mutation_label(name) and not allow_cart_mutation
            if not name or not (dangerous.search(name) or cart_blocked or outside):
                continue
            blocked.append(
                {
                    "candidate_id": self._candidate_id(state["state_id"], "blocked", str(control.get("index", 0))),
                    "target": name[:140],
                    "action_type": "click",
                }
            )
        return blocked

    @staticmethod
    def _is_cart_mutation_label(name: str) -> bool:
        return bool(re.search(r"add\s*[- ]?\s*to\s*[- ]?\s*(?:cart|bag)|加入购物车|添加到购物车", name, re.I))

    @staticmethod
    def _requirement_allows_cart_mutation(text: str) -> bool:
        return bool(
            re.search(
                r"add\b.{0,80}\b(?:to|into)\s+(?:the\s+)?(?:shopping\s+)?(?:cart|bag)|加入购物车|添加到购物车",
                text,
                re.I,
            )
        )

    @staticmethod
    def _requirement_allows_repeat_cart_mutation(text: str) -> bool:
        same_variant = re.search(
            r"(?:same|identical|same\s+selected)\b.{0,50}\b(?:variant|item|product|sku)\b|"
            r"\b(?:variant|item|product|sku)\b.{0,50}\b(?:same|identical)\b|"
            r"(?:相同|同一)(?:商品|产品)?(?:规格|款式|sku)|(?:重复|再次).{0,50}(?:加入|添加).{0,50}(?:相同|同一)",
            text,
            re.I,
        )
        quantity_merge = re.search(r"merge|combine|quantity|quantities|count|合并|数量|件数", text, re.I)
        return bool(same_variant and quantity_merge)

    @staticmethod
    def _has_observed_empty_cart(states: list[dict[str, Any]]) -> bool:
        return any(
            state.get("page_type") == "cart-empty"
            or bool(
                re.search(
                    r"your cart is empty|购物车为空|购物车.*空",
                    str(state.get("main_content") or ""),
                    re.I,
                )
            )
            for state in states
        )

    @staticmethod
    def _locator_for_control(control: dict[str, Any]) -> dict[str, Any] | None:
        role, name = control.get("role"), str(control.get("name") or "").strip()
        if role and name:
            return {"kind": "role", "value": role, "name": name, "exact": True}
        if control.get("test_id"):
            return {"kind": "test_id", "value": control["test_id"]}
        if control.get("id"):
            return {"kind": "id", "value": str(control["id"])}
        if control.get("href"):
            return {"kind": "css", "value": f"a[href={json.dumps(str(control['href']))}]"}
        if name and tag_is_text(control.get("tag")):
            return {"kind": "text", "value": name, "exact": True}
        return None

    @staticmethod
    def _safe_controls(controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for control in controls:
            if not control.get("visible"):
                continue
            name = SensitiveRedactor.redact_text(str(control.get("name") or ""))[:160]
            safe_filter = bool(re.search(r"filter|sort|color|colour|size|筛选|排序|颜色|尺码", name, re.I))
            href = str(control.get("href") or "")
            safe_href = QualityDiscoveryService._safe_url(href)
            try:
                href_parts = urlsplit(href)
                has_query = bool(href_parts.query or href_parts.fragment)
                has_credentials = bool(href_parts.username or href_parts.password)
            except ValueError:
                has_query = has_credentials = True
            result.append(
                {
                    "index": int(control.get("index", len(result))),
                    "tag": str(control.get("tag") or "")[:30],
                    "role": str(control.get("role") or "")[:30],
                    "name": name,
                    "type": str(control.get("type") or "")[:30],
                    "href": safe_href[:500],
                    "has_query": has_query,
                    "has_credentials": has_credentials,
                    "test_id": SensitiveRedactor.redact_text(str(control.get("test_id") or ""))[:120],
                    "id": SensitiveRedactor.redact_text(str(control.get("id") or ""))[:120],
                    "visible": True,
                    "enabled": bool(control.get("enabled", True)),
                    "selected": bool(control.get("selected", False)),
                    "checked": bool(control.get("checked", False)),
                    "selection_fingerprint": (
                        hashlib.sha256(str(control.get("value") or "").encode()).hexdigest()[:12]
                        if control.get("tag") == "select" and control.get("value")
                        else ""
                    ),
                    "value": (
                        SensitiveRedactor.redact_text(str(control.get("value") or ""))[:120]
                        if control.get("tag") == "select" and safe_filter
                        else ""
                    ),
                    "options": [
                        {
                            "value": SensitiveRedactor.redact_text(str(item.get("value") or ""))[:120],
                            "enabled": bool(item.get("enabled", True)),
                        }
                        for item in (
                            (control.get("options") or [])[:30]
                            if control.get("tag") == "select" and safe_filter
                            else []
                        )
                        if isinstance(item, dict)
                    ],
                }
            )
        return result

    @staticmethod
    def _safe_select_value(control: dict[str, Any]) -> str:
        current = str(control.get("value") or "")
        return next(
            (
                str(option.get("value") or "")
                for option in (control.get("options") or [])
                if option.get("enabled")
                and str(option.get("value") or "")
                and str(option.get("value") or "") != current
            ),
            "",
        )

    @staticmethod
    def _safe_search_value(state: dict[str, Any]) -> str:
        for control in state.get("controls", []):
            name = str(control.get("name") or "").strip()
            match = re.fullmatch(r"view\s+(.+)", name, re.I)
            if match and match.group(1).strip():
                return match.group(1).strip()[:100]
        return "qa sample"

    @classmethod
    def _search_value_for_goal(
        cls,
        state: dict[str, Any],
        plan: dict[str, Any],
        requirements: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
    ) -> str:
        active_goal = cls._active_goal_context(plan, requirements, actions, states) or {}
        goal_text = " ".join(
            str(active_goal.get(key) or "")
            for key in ("title", "feature", "rationale", "expected_behavior", "acceptance_criteria")
        )
        if re.search(r"no[-\s]+match|no[-\s]+result|empty\s+state|无匹配|无结果|空状态|未找到", goal_text, re.I):
            return "zzqa-no-matching-item"

        current_value = cls._safe_search_value(state)
        if current_value != "qa sample":
            if re.search(r"case\s*[- ]?insensitive|ignore\s+case|忽略大小写|不区分大小写", goal_text, re.I):
                return current_value.casefold()
            return current_value
        for previous_state in states:
            previous_value = cls._safe_search_value(previous_state)
            if previous_value != "qa sample":
                if re.search(r"case\s*[- ]?insensitive|ignore\s+case|忽略大小写|不区分大小写", goal_text, re.I):
                    return previous_value.casefold()
                return previous_value
        return next(
            (
                str(action.get("search_value"))
                for action in reversed(actions)
                if action.get("action_type") == "search"
                and action.get("status") == "EXECUTED"
                and action.get("search_value")
                and action.get("search_value") != "zzqa-no-matching-item"
            ),
            current_value,
        )

    @staticmethod
    def _active_goal_context(
        plan: dict[str, Any],
        requirements: list[dict[str, Any]],
        actions: list[dict[str, Any]] | None = None,
        states: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        goals = plan.get("goals") or []
        if not goals:
            return None
        search_values = {
            str(action.get("search_value") or "").casefold()
            for action in (actions or [])
            if action.get("action_type") == "search" and action.get("status") == "EXECUTED"
        }
        for goal in goals:
            requirement_id = goal.get("requirement_id")
            requirement = next((item for item in requirements if item.get("id") == requirement_id), None)
            context = {
                key: goal.get(key)
                for key in ("title", "feature", "priority", "rationale", "requirement_id")
                if goal.get(key)
            }
            if requirement:
                context["expected_behavior"] = requirement.get("expected_behavior")
                context["acceptance_criteria"] = (requirement.get("acceptance_criteria") or [])[:5]
            goal_text = " ".join(
                str(context.get(key) or "")
                for key in ("title", "feature", "rationale", "expected_behavior", "acceptance_criteria")
            )
            is_no_match_goal = bool(
                re.search(r"no[-\s]+match|no[-\s]+result|empty\s+state|无匹配|无结果|空状态|未找到", goal_text, re.I)
            )
            if not re.search(r"search|搜索", goal_text, re.I) and not is_no_match_goal:
                return context
            if is_no_match_goal and "zzqa-no-matching-item" in search_values:
                continue
            if not is_no_match_goal and any(value and value != "zzqa-no-matching-item" for value in search_values):
                continue
            return context
        return None

    @staticmethod
    def _filter_repeated_search_candidates(
        candidates: list[dict[str, Any]], actions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        executed_searches = [
            action for action in actions if action.get("action_type") == "search" and action.get("status") == "EXECUTED"
        ]
        if not executed_searches:
            return candidates
        searched_values = {str(action.get("search_value") or "").casefold() for action in executed_searches}
        if "" in searched_values:
            return [candidate for candidate in candidates if candidate.get("action_type") != "search"]
        return [
            candidate
            for candidate in candidates
            if candidate.get("action_type") != "search"
            or str(candidate.get("value") or "").casefold() not in searched_values
        ]

    @staticmethod
    def _filter_repeated_select_candidates(
        candidates: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
        state: dict[str, Any],
        *,
        allow_repeat_same_variant: bool = False,
    ) -> list[dict[str, Any]]:
        state_by_id = {item.get("state_id"): item for item in states}
        current_scope = QualityDiscoveryService._product_scope_key(state)
        previous_selections = [
            action
            for action in actions
            if action.get("action_type") == "select"
            and action.get("status") == "EXECUTED"
            and action.get("from_state_id") in state_by_id
            and QualityDiscoveryService._product_scope_key(state_by_id[action["from_state_id"]]) == current_scope
        ]
        selected_targets = {str(action.get("target") or "").casefold() for action in previous_selections}
        repeat_add_count = sum(
            action.get("status") == "EXECUTED"
            and QualityDiscoveryService._is_cart_mutation_label(str(action.get("target") or ""))
            for action in actions
        )
        return [
            candidate
            for candidate in candidates
            if candidate.get("action_type") != "select"
            or str(candidate.get("target") or "").casefold() not in selected_targets
            or (
                allow_repeat_same_variant
                and repeat_add_count == 1
                and any(
                    str(action.get("target") or "").casefold() == str(candidate.get("target") or "").casefold()
                    and str(action.get("selected_value") or "").casefold()
                    == str(candidate.get("value") or "").casefold()
                    for action in previous_selections
                )
            )
        ]

    @staticmethod
    def _product_scope_key(state: dict[str, Any]) -> str:
        url = str(state.get("url") or "").casefold()
        landmarks = str(state.get("landmarks") or "")
        heading = re.search(r'heading\s+"([^"\r\n]+)"\s+\[level=1\]', landmarks, re.I)
        product = heading.group(1).strip().casefold() if heading else ""
        return hashlib.sha256(f"{url}\n{product}".encode()).hexdigest()[:20]

    @classmethod
    def _cart_variant_key(cls, state: dict[str, Any]) -> str:
        variants = [
            (
                str(control.get("name") or "").casefold(),
                str(control.get("selection_fingerprint") or "")
                or hashlib.sha256(str(control.get("value") or "").casefold().encode()).hexdigest()[:12],
            )
            for control in state.get("controls", [])
            if control.get("tag") == "select"
            and re.search(
                r"color|colour|size|variant|option|material|颜色|尺码|规格",
                str(control.get("name") or ""),
                re.I,
            )
        ]
        key = json.dumps([cls._product_scope_key(state), variants], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(key.encode()).hexdigest()[:24]

    @staticmethod
    def _prioritize_variant_actions_before_cart(
        candidates: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        cart_candidates = [
            candidate
            for candidate in candidates
            if QualityDiscoveryService._is_cart_mutation_label(str(candidate.get("target") or ""))
        ]
        if not cart_candidates:
            return candidates

        variant_controls = [
            control
            for control in state.get("controls", [])
            if control.get("tag") == "select"
            and re.search(
                r"color|colour|size|variant|option|material|颜色|尺码|规格",
                str(control.get("name") or ""),
                re.I,
            )
            and QualityDiscoveryService._safe_select_value(control)
        ]
        if not variant_controls:
            return candidates

        state_by_id = {item.get("state_id"): item for item in states}
        current_scope = QualityDiscoveryService._product_scope_key(state)
        selected_targets = {
            str(action.get("target") or "").casefold()
            for action in actions
            if action.get("action_type") == "select"
            and action.get("status") == "EXECUTED"
            and action.get("from_state_id") in state_by_id
            and QualityDiscoveryService._product_scope_key(state_by_id[action["from_state_id"]]) == current_scope
        }
        required_targets = {str(control.get("name") or "").casefold() for control in variant_controls}
        unresolved_targets = [target for target in required_targets if target not in selected_targets]
        if not unresolved_targets:
            return candidates
        next_target = next(
            str(control.get("name") or "").casefold()
            for control in variant_controls
            if str(control.get("name") or "").casefold() in unresolved_targets
        )
        return [
            candidate
            for candidate in candidates
            if candidate.get("action_type") == "select" and str(candidate.get("target") or "").casefold() == next_target
        ]

    @staticmethod
    def _prioritize_cart_verification_after_add(
        candidates: list[dict[str, Any]],
        state: dict[str, Any],
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
        *,
        allow_repeat_same_variant: bool = False,
    ) -> list[dict[str, Any]]:
        successful_adds = [
            action
            for action in actions
            if action.get("status") == "EXECUTED"
            and QualityDiscoveryService._is_cart_mutation_label(str(action.get("target") or ""))
        ]
        if not successful_adds:
            return candidates

        if allow_repeat_same_variant and len(successful_adds) == 1:
            previous_variant_key = successful_adds[0].get("cart_variant_key")
            same_variant_adds = [
                candidate
                for candidate in candidates
                if QualityDiscoveryService._is_cart_mutation_label(str(candidate.get("target") or ""))
                and previous_variant_key
                and candidate.get("cart_variant_key") == previous_variant_key
            ]
            if same_variant_adds:
                return same_variant_adds

        cart_inspected = any(
            (
                str(item.get("page_type") or "").casefold() in {"cart", "shopping_cart", "cart_populated"}
                or re.search(
                    r"shopping cart|购物车",
                    f"{item.get('title') or ''} {item.get('main_content') or ''}",
                    re.I,
                )
            )
            and bool(re.search(r"total\s*:\s*\$\s*\d", str(item.get("main_content") or ""), re.I))
            and not bool(
                re.search(r"your cart is empty|购物车为空|购物车.*空", str(item.get("main_content") or ""), re.I)
            )
            and bool(successful_adds[-1].get("finished_at"))
            and bool(item.get("observed_at"))
            and datetime.fromisoformat(str(item["observed_at"]).replace("Z", "+00:00"))
            >= datetime.fromisoformat(str(successful_adds[-1]["finished_at"]).replace("Z", "+00:00"))
            for item in states
        )
        if not cart_inspected:
            cart_views = [
                candidate
                for candidate in candidates
                if candidate.get("action_type") == "click"
                and re.fullmatch(
                    r"(?:shopping\s+)?(?:cart|bag|basket)(?:\s*\(\s*\d+\s*\))?",
                    str(candidate.get("target") or ""),
                    re.I,
                )
            ]
            if cart_views:
                return cart_views
        return [
            candidate
            for candidate in candidates
            if not QualityDiscoveryService._is_cart_mutation_label(str(candidate.get("target") or ""))
        ]

    @staticmethod
    def _back_candidate(
        result: dict[str, Any], state: dict[str, Any], allowed_hosts: set[str]
    ) -> dict[str, Any] | None:
        state_id = state["state_id"]
        states = {item.get("state_id"): item for item in result.get("states", [])}
        for edge in reversed(result.get("edges", [])):
            if edge.get("to_state_id") != state_id:
                continue
            parent = states.get(edge.get("from_state_id"))
            if not parent or parent.get("url") == state.get("url") or not parent.get("url_navigable"):
                continue
            destination = str(parent.get("url") or "")
            if not QualityDiscoveryService._host_allowed(destination, allowed_hosts):
                continue
            return {
                "candidate_id": QualityDiscoveryService._candidate_id(state_id, "back", "history"),
                "action_type": "back",
                "target_id": None,
                "target": "返回已观察的站内页面",
                "expected_effect": "导航回已观察的站内页面，检查其他未探索路径。",
                "locator": {"kind": "page", "value": ""},
                "value": destination,
                "risk": "READ_ONLY",
            }
        return None

    @staticmethod
    def _url_is_navigable(value: str) -> bool:
        try:
            parts = urlsplit(value)
            return bool(
                parts.scheme in {"http", "https"}
                and parts.hostname
                and not parts.username
                and not parts.password
                and not parts.query
                and not parts.fragment
            )
        except ValueError:
            return False

    @staticmethod
    def _candidate_id(state_id: str, action: str, target: str) -> str:
        digest = hashlib.sha256(f"{state_id}:{action}:{target}".encode()).hexdigest()[:12]
        return f"cand_{digest}"

    @staticmethod
    def _state_fingerprint(snapshot, controls: list[dict[str, Any]], scroll: dict[str, Any]) -> tuple[str, str]:
        normalized_url = QualityDiscoveryService._safe_url(snapshot.url)
        descriptor = {
            "url": normalized_url,
            "title": QualityDiscoveryService._safe_title(snapshot.title)[:180],
            "text": SensitiveRedactor.redact_text(re.sub(r"\s+", " ", snapshot.text or ""))[:1800],
            "scroll": scroll,
            "controls": [
                {
                    key: item.get(key)
                    for key in ("tag", "role", "name", "href", "value", "selected", "checked", "selection_fingerprint")
                }
                for item in controls[:60]
            ],
        }
        fingerprint = hashlib.sha256(json.dumps(descriptor, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[
            :24
        ]
        return f"state_{fingerprint[:16]}", fingerprint

    @staticmethod
    def _state_record(snapshot, controls, scroll, state_id, fingerprint) -> dict[str, Any]:
        text = re.sub(r"\s+", " ", snapshot.text or "").strip()
        evidence_chars = get_config().discovery.max_evidence_chars
        content_limit = evidence_chars // 2
        return {
            "state_id": state_id,
            "fingerprint": fingerprint,
            "url": QualityDiscoveryService._safe_url(snapshot.url)[:2048],
            "url_navigable": QualityDiscoveryService._url_is_navigable(snapshot.url),
            "title": QualityDiscoveryService._safe_title(snapshot.title)[:200],
            "page_type": "unknown",
            "visible_controls": len(controls),
            "controls": controls,
            "main_content": SensitiveRedactor.redact_text(text)[:content_limit],
            "landmarks": SensitiveRedactor.redact_text(snapshot.accessibility_tree or "")[
                : evidence_chars - content_limit
            ],
            "scroll": scroll,
            "network": QualityDiscoveryService._network_summary(snapshot.network),
            "console_errors": [
                {key: SensitiveRedactor.redact_text(str(value))[:500] for key, value in item.items()}
                for item in snapshot.console
                if item.get("type") == "error"
            ][:20],
            "evidence_id": None,
            "depth": 0,
            "attempted_candidate_ids": [],
            "skipped_candidate_ids": [],
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _network_summary(network: list[dict[str, Any]]) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        failures = 0
        for item in network[-50:]:
            status = item.get("status")
            if isinstance(status, int):
                bucket = f"{status // 100}xx"
                statuses[bucket] = statuses.get(bucket, 0) + 1
                if status >= 400:
                    failures += 1
            if item.get("failed"):
                failures += 1
        return {"responses": statuses, "failures": failures, "sample_count": min(len(network), 50)}

    @staticmethod
    def _allowed_hosts(row: QualityDiscoveryRunORM) -> set[str]:
        initial = (urlsplit(row.start_url).hostname or "").lower().rstrip(".")
        configured = get_config().discovery.allowed_domains
        return {initial, *(host.lower().rstrip(".") for host in [*(row.allowed_domains or []), *configured])}

    @classmethod
    def _find_similar_state(
        cls,
        result: dict[str, Any],
        snapshot,
        controls: list[dict[str, Any]],
        threshold: float,
    ) -> dict[str, Any] | None:
        current_selects = {
            item.get("name"): item.get("selection_fingerprint")
            for item in controls
            if item.get("tag") == "select" and item.get("selection_fingerprint")
        }
        best = None
        for state in result.get("states", []):
            old_controls = state.get("controls", [])
            old_selects = {
                item.get("name"): item.get("selection_fingerprint")
                for item in old_controls
                if item.get("tag") == "select" and item.get("selection_fingerprint")
            }
            if current_selects != old_selects:
                continue
            score = cls._state_similarity(
                state,
                {
                    "url": cls._safe_url(snapshot.url),
                    "title": cls._safe_title(snapshot.title),
                    "controls": controls,
                },
            )
            if score >= threshold and (best is None or score > best["score"]):
                best = {"state_id": state["state_id"], "score": round(score, 3)}
        return best

    @classmethod
    def _state_similarity(cls, left: dict[str, Any], right: dict[str, Any]) -> float:
        def template(value: str) -> str:
            path = urlsplit(value).path.casefold()
            path = re.sub(r"(?<![a-z])[0-9a-f]{8}-[0-9a-f-]{20,}(?![a-z])", ":id", path)
            path = re.sub(r"(?<=/)[0-9]+(?=/|$)", ":id", path)
            return path.rstrip("/") or "/"

        left_url, right_url = template(str(left.get("url") or "")), template(str(right.get("url") or ""))
        if left_url != right_url:
            return 0.0
        left_controls = {
            (
                item.get("tag"),
                item.get("role"),
                item.get("type"),
                str(item.get("name") or "").casefold(),
                item.get("checked"),
                item.get("selected"),
            )
            for item in left.get("controls", [])
        }
        right_controls = {
            (
                item.get("tag"),
                item.get("role"),
                item.get("type"),
                str(item.get("name") or "").casefold(),
                item.get("checked"),
                item.get("selected"),
            )
            for item in right.get("controls", [])
        }
        control_score = (
            len(left_controls & right_controls) / len(left_controls | right_controls)
            if left_controls | right_controls
            else 1.0
        )
        title_score = cls._similarity(str(left.get("title") or ""), str(right.get("title") or ""))
        return 0.75 * control_score + 0.20 * title_score + 0.05

    @staticmethod
    def _host_allowed(url: str, hosts: set[str]) -> bool:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname.lower().rstrip(".")
        return host in hosts

    @staticmethod
    def _safe_url(url: str) -> str:
        try:
            parts = urlsplit(url)
            hostname = parts.hostname or ""
            if ":" in hostname and not hostname.startswith("["):
                hostname = f"[{hostname}]"
            port = f":{parts.port}" if parts.port is not None else ""
        except ValueError:
            return ""
        netloc = f"{hostname}{port}" if parts.netloc else ""
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))

    @staticmethod
    def _safe_title(title: str) -> str:
        safe = SensitiveRedactor.redact_text(str(title or ""))
        protocol_relative_url = re.compile(r"(?<![A-Za-z0-9:])//(?P<path>[^\s?#]+)(?:\?[^\s#]*)?(?:#[^\s]*)?")
        safe = protocol_relative_url.sub(lambda match: f"//{match.group('path')}", safe)
        relative_url = re.compile(
            r"(?<![A-Za-z0-9/:])(?P<path>/?[A-Za-z0-9._~!$&'()*+,;=:@%-]+(?:/[A-Za-z0-9._~!$&'()*+,;=:@%-]+)*)(?:\?[^\s#]*|#[^\s#]*)+"
        )
        safe = relative_url.sub(lambda match: match.group("path"), safe)
        safe = re.sub(r"(?<!\S)[?#][^\s]*", "", safe)
        return safe.strip()[:500]

    @staticmethod
    def _url_has_secret_query(url: str) -> bool:
        parsed = urlsplit(url)
        return bool(parsed.query or parsed.fragment)

    @staticmethod
    def _safe_error(error: Exception, limit: int = 500) -> str:
        message = SensitiveRedactor.redact_text(str(error))
        message = re.sub(
            r"https?://[^\s\"'<>]+",
            lambda match: QualityDiscoveryService._safe_url(match.group(0)),
            message,
        )
        return f"{type(error).__name__}: {message[:limit]}"

    @staticmethod
    def _resume_url(result: dict[str, Any], start_url: str) -> str:
        states = result.get("states") or []
        return str(states[-1].get("url") or start_url) if states else start_url

    async def _save_screenshot(self, run_id: str, state_id: str, screenshot: bytes) -> str | None:
        storage = ArtifactStorageService(ArtifactRepository(self.session_factory))
        saved = await storage.save_artifact(
            filename=f"{run_id}_{state_id}.png",
            content=screenshot,
            content_type="image/png",
        )
        return saved.artifact_id

    async def _save_state_evidence(self, run_id: str, state_id: str, state: dict[str, Any]) -> str | None:
        evidence = {
            key: state.get(key)
            for key in (
                "url",
                "title",
                "page_type",
                "visible_controls",
                "controls",
                "main_content",
                "landmarks",
                "scroll",
                "network",
                "console_errors",
            )
        }
        content = json.dumps(evidence, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        storage = ArtifactStorageService(ArtifactRepository(self.session_factory))
        saved = await storage.save_artifact(
            filename=f"{run_id}_{state_id}_evidence.json",
            content=content,
            content_type="application/json",
        )
        return saved.artifact_id

    async def _append_requirements(self, run_id: str, analysis: dict[str, Any]) -> dict[str, Any]:
        await self._change_result(run_id, lambda result: result.update(analysis))
        row = await self.get(run_id)
        return row.result if row else {}

    async def _upsert_state(self, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
        def change(result):
            existing = self._find_state(result, state["fingerprint"])
            if existing:
                state["depth"] = existing.get("depth", 0)
                state["attempted_candidate_ids"] = existing.get("attempted_candidate_ids", [])
                state["skipped_candidate_ids"] = existing.get("skipped_candidate_ids", [])
                state["evidence_id"] = existing.get("evidence_id") or state.get("evidence_id")
                state["screenshot_evidence_id"] = existing.get("screenshot_evidence_id") or state.get(
                    "screenshot_evidence_id"
                )
                state["similar_to_state_id"] = existing.get("similar_to_state_id") or state.get("similar_to_state_id")
                state["similarity"] = existing.get("similarity") or state.get("similarity")
                result["states"] = [
                    state if item["fingerprint"] == state["fingerprint"] else item for item in result["states"]
                ]
            else:
                state["depth"] = min(
                    self._state_depth(result, state["state_id"]),
                    get_config().discovery.max_depth + 1,
                )
                result["states"].append(state)
            self._verify_features_for_state(result, state)

        await self._change_result(run_id, change)
        row = await self.get(run_id)
        return row.result if row else {}

    @staticmethod
    def _find_state(result: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
        return next((item for item in result.get("states", []) if item.get("fingerprint") == fingerprint), None)

    @staticmethod
    def _verify_features_for_state(result: dict[str, Any], state: dict[str, Any]) -> None:
        evidence_id = state.get("evidence_id")
        if not evidence_id:
            return
        actions = [
            action
            for action in result.get("actions", [])
            if action.get("status") == "EXECUTED"
            and action.get("state_changed") is True
            and action.get("to_fingerprint") == state.get("fingerprint")
            and action.get("target_id")
        ]
        for action in actions:
            scoped_target_id = f"{action.get('from_state_id')}:{action['target_id']}"
            for feature in result.get("features", []):
                if scoped_target_id not in feature.get("target_ids", []):
                    continue
                action_ids = feature.setdefault("verification_action_ids", [])
                if action["candidate_id"] not in action_ids:
                    action_ids.append(action["candidate_id"])
                state_ids = feature.setdefault("verification_state_ids", [])
                if state.get("state_id") not in state_ids:
                    state_ids.append(state["state_id"])
                evidence_ids = feature.setdefault("evidence_ids", [])
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
                feature["verified_by_action_id"] = action["candidate_id"]
                feature["status"] = "VERIFIED"
                feature["trust"] = "VERIFIED"

    @staticmethod
    def _state_depth(result: dict[str, Any], state_id: str) -> int:
        states = result.get("states", [])
        if not states:
            return 0
        depths = {states[0]["state_id"]: 0}
        changed = True
        while changed:
            changed = False
            for edge in result.get("edges", []):
                source, target = edge.get("from_state_id"), edge.get("to_state_id")
                if source not in depths or not target:
                    continue
                next_depth = depths[source] + 1
                if next_depth < depths.get(target, next_depth + 1):
                    depths[target] = next_depth
                    changed = True
        return depths.get(state_id, max((item.get("depth", 0) for item in states), default=0) + 1)

    async def _record_features(self, run_id: str, plan: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        controls = {f"el_{control['index']}": control for control in state["controls"]}
        visible_text = str(state.get("main_content") or "").casefold()
        evidence_id = state.get("evidence_id")

        def change(result):
            result.setdefault("features", [])
            for signal in plan.get("features", []):
                target = controls.get(signal.get("target_id"))
                evidence_text = str(signal.get("evidence_text") or "").strip()
                grounded = bool(target or (len(evidence_text) >= 3 and evidence_text.casefold() in visible_text))
                feature_id = self._feature_id(signal["name"])
                feature = next((item for item in result["features"] if item["feature_id"] == feature_id), None)
                if feature is None:
                    feature = {
                        "feature_id": feature_id,
                        "name": signal["name"],
                        "description": signal.get("description", ""),
                        "page": state.get("title") or state.get("url"),
                        "status": "OBSERVED" if grounded else "INFERRED",
                        "evidence_ids": [],
                        "state_ids": [],
                        "inference_state_ids": [],
                        "requirement_ids": [],
                        "target_ids": [],
                        "confidence": signal.get("confidence", 0.5),
                        "mapping_confidence": 0.0,
                        "mapping_status": "UNMAPPED" if grounded else "NEEDS_REVIEW",
                    }
                    result["features"].append(feature)
                feature["confidence"] = max(float(feature.get("confidence", 0)), float(signal.get("confidence", 0.5)))
                if grounded:
                    if feature.get("status") != "VERIFIED":
                        feature["status"] = "OBSERVED"
                    if evidence_id and evidence_id not in feature["evidence_ids"]:
                        feature["evidence_ids"].append(evidence_id)
                    if state["state_id"] not in feature["state_ids"]:
                        feature["state_ids"].append(state["state_id"])
                elif state["state_id"] not in feature.setdefault("inference_state_ids", []):
                    feature["inference_state_ids"].append(state["state_id"])
                scoped_target_id = f"{state['state_id']}:{signal['target_id']}" if signal.get("target_id") else None
                if grounded and scoped_target_id and scoped_target_id not in feature["target_ids"]:
                    feature["target_ids"].append(scoped_target_id)
                feature["description"] = feature.get("description") or signal.get("description", "")
                feature["page_type"] = plan.get("page_type", "unknown")
                feature["trust"] = feature["status"]

            result.setdefault("goals", [])
            known_requirements = {item.get("id") for item in result.get("requirements", [])}
            known_goal_titles = {str(item.get("title", "")).casefold() for item in result["goals"]}
            for goal in plan.get("goals", []):
                title = str(goal.get("title") or "").strip()
                if not title or title.casefold() in known_goal_titles:
                    continue
                requirement_id = goal.get("requirement_id")
                if requirement_id not in known_requirements:
                    requirement_id = None
                result["goals"].append(
                    {
                        **goal,
                        "requirement_id": requirement_id,
                        "state_id": state["state_id"],
                        "status": "INFERRED",
                        "evidence_ids": [evidence_id] if evidence_id else [],
                    }
                )
                known_goal_titles.add(title.casefold())

        await self._change_result(run_id, change)
        row = await self.get(run_id)
        return row.result if row else {}

    @staticmethod
    def _feature_id(name: str) -> str:
        token = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
        digest = hashlib.sha256(name.casefold().encode()).hexdigest()[:6]
        return f"feature-{(token[:40] or 'discovered')}-{digest}"

    async def _mark_attempted(self, run_id: str, fingerprint: str, candidate_id: str) -> None:
        def change(result):
            state = self._find_state(result, fingerprint)
            if state and candidate_id not in state.setdefault("attempted_candidate_ids", []):
                state["attempted_candidate_ids"].append(candidate_id)

        await self._change_result(run_id, change)

    async def _skip_candidates(
        self, run_id: str, fingerprint: str, candidates: list[dict[str, Any]], reason: str
    ) -> None:
        def change(result):
            state = self._find_state(result, fingerprint)
            if state is None:
                return
            skipped_ids = state.setdefault("skipped_candidate_ids", [])
            for candidate in candidates:
                candidate_id = candidate["candidate_id"]
                if candidate_id not in skipped_ids:
                    skipped_ids.append(candidate_id)

        await self._change_result(run_id, change)
        row = await self.get(run_id)
        state = self._find_state(row.result if row else {}, fingerprint)
        if state:
            await self._record_frontier(run_id, state["state_id"], candidates, "SKIPPED", reason)

    async def _record_frontier(
        self,
        run_id: str,
        state_id: str,
        candidates: list[dict[str, Any]],
        status: str,
        reason: str,
    ) -> None:
        if not candidates:
            return

        def change(result):
            frontier = result.setdefault("frontier", [])
            for candidate in candidates:
                candidate_id = candidate["candidate_id"]
                existing = next(
                    (
                        item
                        for item in frontier
                        if item.get("state_id") == state_id and item.get("candidate_id") == candidate_id
                    ),
                    None,
                )
                record = {
                    "state_id": state_id,
                    "candidate_id": candidate_id,
                    "target": candidate.get("target", "")[:140],
                    "status": status,
                    "reason": reason[:300],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if existing:
                    existing.update(record)
                else:
                    frontier.append(record)

        await self._change_result(run_id, change)

    async def _set_state_page_type(self, run_id: str, fingerprint: str, page_type: str) -> None:
        normalized_type = re.sub(r"[^a-z0-9_-]+", "_", str(page_type).casefold()).strip("_")[:80] or "unknown"

        def change(result):
            state = self._find_state(result, fingerprint)
            if state:
                state["page_type"] = normalized_type

        await self._change_result(run_id, change)

    async def _append_action(self, run_id: str, action: dict[str, Any]) -> None:
        await self._change_result(run_id, lambda result: result.setdefault("actions", []).append(action))

    async def _replace_action(self, run_id: str, action: dict[str, Any]) -> None:
        def change(result):
            for index, existing in enumerate(result.get("actions", [])):
                if existing.get("candidate_id") == action.get("candidate_id") and existing.get(
                    "from_state_id"
                ) == action.get("from_state_id"):
                    result["actions"][index] = action
                    break

        await self._change_result(run_id, change)

    async def _append_edge(
        self, run_id: str, from_state_id: str, to_fingerprint: str, candidate: dict[str, Any]
    ) -> None:
        row = await self.get(run_id)
        if row is None:
            return
        to_state = self._find_state(row.result or {}, to_fingerprint)
        edge = {
            "from_state_id": from_state_id,
            "to_state_id": to_state.get("state_id") if to_state else f"state_{to_fingerprint[:16]}",
            "action": candidate["action_type"],
            "label": candidate["target"],
            "candidate_id": candidate["candidate_id"],
        }
        await self._change_result(
            run_id,
            lambda result: (
                result.setdefault("edges", []).append(edge) if edge not in result.setdefault("edges", []) else None
            ),
        )

    async def _link_feature_evidence(
        self, run_id: str, state: dict[str, Any], candidate: dict[str, Any], changed: bool
    ) -> None:
        if not changed:
            return
        scoped_target_id = f"{state['state_id']}:{candidate.get('target_id')}"

        def change(result):
            for feature in result.get("features", []):
                if scoped_target_id in feature.get("target_ids", []):
                    action_ids = feature.setdefault("observed_transition_action_ids", [])
                    if candidate["candidate_id"] not in action_ids:
                        action_ids.append(candidate["candidate_id"])

        await self._change_result(run_id, change)

    async def _record_ai(self, run_id: str, usage: dict[str, Any]) -> None:
        def change(result):
            ai = result.setdefault(
                "ai",
                {
                    "provider": None,
                    "model": None,
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "unknown_token_calls": 0,
                },
            )
            ai["provider"], ai["model"] = usage.get("provider"), usage.get("model")
            ai["calls"] += 1
            for token_name in ("input_tokens", "output_tokens"):
                value = usage.get(token_name)
                if isinstance(value, int):
                    ai[token_name] += value
                else:
                    ai["unknown_token_calls"] += 1

        await self._change_result(run_id, change)

    async def _record_decision(
        self,
        run_id: str,
        decision,
        *,
        decision_id: str,
        candidate_ids: list[str],
        priority_candidate_ids: list[str],
    ) -> None:
        def change(result):
            jev = result.setdefault(
                "jev", {"provider": None, "model": None, "decisions": 0, "fallbacks": 0, "usage": {}}
            )
            if decision.fallback_used:
                if jev.get("provider") is None:
                    jev["provider"] = "fallback"
                    jev["model"] = None
            else:
                jev["provider"] = decision.provider
                jev["model"] = decision.model
                jev["usage"] = decision.usage or {}
            jev["decisions"] += 1
            jev["fallbacks"] += int(bool(decision.fallback_used))
            result.setdefault("decisions", []).append(
                {
                    "decision_id": decision_id,
                    "choice": decision.choice,
                    "selected_candidate_id": (
                        decision.choice if not decision.fallback_used and decision.choice in candidate_ids else None
                    ),
                    "attempted_choice": decision.attempted_choice,
                    "candidate_count": len(candidate_ids),
                    "candidate_ids": candidate_ids,
                    "priority_candidate_ids": priority_candidate_ids,
                    "provider": decision.provider,
                    "model": decision.model,
                    "attempted_provider": decision.attempted_provider,
                    "attempted_model": decision.attempted_model,
                    "confidence": decision.confidence,
                    "minimum_confidence": decision.minimum_confidence,
                    "probabilities": decision.probabilities,
                    "fallback_used": decision.fallback_used,
                    "reason": decision.reason,
                }
            )

        await self._change_result(run_id, change)

    async def _build_quality_map(self, run_id: str) -> None:
        for attempt in range(5):
            try:
                await self._build_quality_map_once(run_id)
                return
            except (StaleDataError, OperationalError) as exc:
                if not self._is_retryable_write_conflict(exc) or attempt == 4:
                    raise
                await asyncio.sleep(0.01 * (attempt + 1))

    async def _build_quality_map_once(self, run_id: str) -> None:
        async with self.session_factory() as session:
            row = await QualityDiscoveryRepository(session).get(run_id)
            if row is None:
                return
            cases = await TestCaseRepository(session).list_by_project(row.project_id)
            runs = await TestRunRepository(session).list_runs(project_id=row.project_id, limit=500)
            config = get_config().discovery
            collected_tests = []
            workspace_test_scan_status = "NOT_CONFIGURED"
            if self.workspace_service is not None:
                workspace_test_scan_status = "AVAILABLE"
                try:
                    collected_tests = (await self.workspace_service.collect_tests(row.project_id)).tests
                except Exception:
                    collected_tests = []
                    workspace_test_scan_status = "UNAVAILABLE"
            collected_by_nodeid = {item.nodeid: item for item in collected_tests}
            cases_by_nodeid = {
                case.binding.nodeid: case for case in cases if case.binding is not None and case.binding.nodeid
            }
            result = json.loads(json.dumps(row.result or {}))
            result["workspace_test_scan"] = {
                "status": workspace_test_scan_status,
                "tests_collected": len(collected_tests) if workspace_test_scan_status == "AVAILABLE" else None,
                "message": (
                    "无法读取项目自动化工作区；自动化覆盖结果未验证。"
                    if workspace_test_scan_status == "UNAVAILABLE"
                    else None
                ),
            }
            requirements = result.get("requirements", [])
            features = result.get("features", [])
            coverage = []
            mapping_threshold = config.feature_mapping_confidence
            derived_gap_types = {
                "TEST_MISSING",
                "AUTOMATION_MISSING",
                "AUTOMATION_FAILING",
                "TEST_INCOMPLETE",
                "NOT_VERIFIED",
                "BLOCKED_BY_POLICY",
                "REQUIREMENT_MISSING",
                "IMPLEMENTATION_MISSING",
                "IMPLEMENTATION_PARTIAL",
                "REQUIRED_NOT_FOUND",
                "IMPLEMENTED_PARTIAL",
                "IMPLEMENTED_BROKEN",
                "UNDOCUMENTED_FEATURE",
                "FUNCTION_BROKEN",
                "REQUIREMENT_AMBIGUOUS",
            }
            gaps = [gap for gap in result.get("gaps", []) if gap.get("category") not in derived_gap_types]
            for requirement in requirements:
                matches = [
                    (feature, self._similarity(requirement.get("feature", ""), feature.get("name", "")))
                    for feature in features
                ]
                matches = [
                    (feature, score)
                    for feature, score in matches
                    if score >= 0.34 and feature.get("status") != "INFERRED"
                ]
                for feature, _score in matches:
                    if requirement["id"] not in feature.setdefault("requirement_ids", []):
                        feature["requirement_ids"].append(requirement["id"])
                top_score = max((score for _feature, score in matches), default=0.0)
                check_status, check_results = self._evaluate_requirement_checks(
                    requirement,
                    result.get("states", []),
                    result.get("edges", []),
                    result.get("actions", []),
                )
                check_evidence_ids = {item["evidence_id"] for item in check_results if item.get("evidence_id")}
                requirement["check_status"] = check_status
                requirement["check_results"] = check_results
                requirement["evidence_ids"] = sorted(
                    {evidence for feature, _ in matches for evidence in feature.get("evidence_ids", [])}
                    | check_evidence_ids
                )
                related_action_failed = any(
                    action.get("status") == "FAILED"
                    and action.get("target")
                    and self._similarity(requirement.get("feature", ""), action.get("target", "")) >= 0.34
                    for action in result.get("actions", [])
                )
                if requirement.get("ambiguous"):
                    status = "REQUIREMENT_AMBIGUOUS"
                elif check_status == "FAIL" or related_action_failed:
                    status = "IMPLEMENTED_BROKEN"
                elif check_status == "PASS":
                    status = "PASS"
                elif requirement.get("draft"):
                    status = "NOT_VERIFIED"
                elif not matches:
                    status = "REQUIRED_NOT_FOUND" if row.status == DiscoveryStatus.COMPLETED.value else "NOT_VERIFIED"
                elif top_score < mapping_threshold:
                    status = "NOT_VERIFIED"
                elif matches:
                    status = "IMPLEMENTED_PARTIAL"
                else:
                    status = "NOT_VERIFIED"
                requirement["status"] = status
                requirement["mapping_confidence"] = round(top_score, 2)
                requirement["mapping_status"] = "MAPPED" if top_score >= mapping_threshold else "NEEDS_REVIEW"
                if status in {
                    "REQUIRED_NOT_FOUND",
                    "IMPLEMENTED_PARTIAL",
                    "IMPLEMENTED_BROKEN",
                    "REQUIREMENT_AMBIGUOUS",
                    "NOT_VERIFIED",
                }:
                    gap_category = {
                        "REQUIRED_NOT_FOUND": "IMPLEMENTATION_MISSING",
                        "IMPLEMENTED_PARTIAL": "IMPLEMENTATION_PARTIAL",
                        "IMPLEMENTED_BROKEN": "FUNCTION_BROKEN",
                    }.get(status, status)
                    gaps.append(
                        self._gap(
                            gap_category,
                            requirement["id"],
                            requirement["feature"],
                            requirement.get("evidence_ids", []),
                            top_score,
                        )
                    )

            for feature in features:
                if feature.get("status") == "INFERRED":
                    feature["mapping_status"] = "NEEDS_REVIEW"
                    feature["test_case_ids"] = []
                    feature["automation"] = []
                    feature["coverage_status"] = "NOT_VERIFIED"
                    coverage.append(
                        {
                            "feature_id": feature["feature_id"],
                            "feature": feature["name"],
                            "requirement_ids": [],
                            "requirement_status": "NOT_VERIFIED",
                            "product_status": "INFERRED",
                            "test_status": "NOT_VERIFIED",
                            "automation_status": "NOT_VERIFIED",
                            "last_run_status": None,
                            "gap_categories": ["NOT_VERIFIED"],
                            "coverage_status": "NOT_VERIFIED",
                        }
                    )
                    gaps.append(
                        self._gap(
                            "NOT_VERIFIED", feature["feature_id"], feature["name"], [], feature.get("confidence", 0.0)
                        )
                    )
                    continue
                linked_reqs = [req for req in requirements if req["id"] in feature.get("requirement_ids", [])]
                feature_mapping_confidence = max(
                    (self._similarity(req.get("feature", ""), feature.get("name", "")) for req in linked_reqs),
                    default=0.0,
                )
                feature["mapping_confidence"] = round(feature_mapping_confidence, 2)
                if requirements and not linked_reqs:
                    feature["mapping_status"] = "UNDOCUMENTED_FEATURE"
                    gaps.append(
                        self._gap(
                            "UNDOCUMENTED_FEATURE",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            0.0,
                        )
                    )
                elif linked_reqs:
                    feature["mapping_status"] = (
                        "MAPPED" if feature_mapping_confidence >= mapping_threshold else "NEEDS_REVIEW"
                    )
                case_matches = []
                case_review_matches = []
                for case in cases:
                    case_requirements = [
                        req
                        for req in linked_reqs
                        if req.get("source_id") == case.requirement_id and req.get("source_id") != "PASTED"
                    ]
                    case_requirement_confidence = min(
                        (
                            self._similarity(req.get("feature", ""), feature.get("name", ""))
                            for req in case_requirements
                        ),
                        default=0.0,
                    )
                    if case_requirements and case_requirement_confidence >= mapping_threshold:
                        case_matches.append((case, 1.0))
                    else:
                        score = self._similarity(feature["name"], " ".join([case.title, *case.tags]))
                        if case_requirements:
                            score = min(score, case_requirement_confidence)
                        if score >= 0.34:
                            (case_matches if score >= mapping_threshold else case_review_matches).append((case, score))
                case_ids = [case.id for case, _ in case_matches]
                feature["test_case_candidates"] = [
                    {
                        "test_case_id": case.id,
                        "title": case.title,
                        "mapping_confidence": round(score, 2),
                        "mapping_status": "NEEDS_REVIEW",
                    }
                    for case, score in case_review_matches
                ]
                feature["test_case_ids"] = case_ids
                automation = []
                for case, score in case_matches:
                    binding = case.binding
                    last_execution = self._latest_execution(binding.nodeid, runs) if binding else None
                    explored_test = collected_by_nodeid.get(binding.nodeid) if binding else None
                    automation.append(
                        {
                            "test_case_id": case.id,
                            "test_case_title": case.title,
                            "mapping_confidence": round(score, 2),
                            "mapping_status": "MAPPED" if score >= mapping_threshold else "NEEDS_REVIEW",
                            "automation_binding_id": binding.id if binding else None,
                            "nodeid": binding.nodeid if binding else None,
                            "file_path": explored_test.file
                            if explored_test
                            else (binding.file_path if binding else None),
                            "test_name": explored_test.test_name
                            if explored_test
                            else (binding.nodeid.split("::")[-1] if binding else None),
                            "markers": explored_test.markers if explored_test else [],
                            "automation_status": binding.status if binding else "MISSING",
                            "last_run_id": last_execution[0].id if last_execution else None,
                            "last_run_status": last_execution[1].status if last_execution else None,
                            "last_run_at": last_execution[0].created_at.isoformat() if last_execution else None,
                            "failure_summary": self._safe_title(last_execution[1].error_message or "")
                            if last_execution and last_execution[1].error_message
                            else None,
                        }
                    )
                feature["automation"] = automation
                feature["automation_candidates"] = [
                    {
                        "nodeid": item.nodeid,
                        "file_path": item.file,
                        "test_name": item.test_name,
                        "markers": item.markers,
                        "linked_test_case_id": cases_by_nodeid[item.nodeid].id
                        if item.nodeid in cases_by_nodeid
                        else None,
                        "linked_requirement_id": cases_by_nodeid[item.nodeid].requirement_id
                        if item.nodeid in cases_by_nodeid
                        else None,
                        "mapping_confidence": round(
                            self._similarity(feature["name"], item.test_name.replace("_", " ")), 2
                        ),
                    }
                    for item in collected_tests
                    if item.nodeid not in {candidate.get("nodeid") for candidate in automation}
                    and self._similarity(feature["name"], item.test_name.replace("_", " ")) >= 0.34
                ][:20]
                active_automation = [
                    item for item in automation if item["automation_status"] == "ACTIVE" and item["nodeid"]
                ]
                has_binding = bool(active_automation)
                failing = any(item["last_run_status"] in {"FAILED", "ERROR"} for item in active_automation)
                passed = any(item["last_run_status"] == "PASSED" for item in active_automation)
                if case_review_matches:
                    gaps.append(
                        self._gap(
                            "TEST_INCOMPLETE",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            max(score for _, score in case_review_matches),
                        )
                    )
                elif not case_matches:
                    coverage_status = "NOT_COVERED"
                    gaps.append(
                        self._gap(
                            "TEST_MISSING",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            feature.get("mapping_confidence", 0),
                        )
                    )
                if not has_binding and workspace_test_scan_status != "UNAVAILABLE":
                    gaps.append(
                        self._gap(
                            "AUTOMATION_MISSING",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            max((score for _, score in case_matches), default=0.0),
                        )
                    )
                if failing:
                    coverage_status = "AUTOMATION_FAILING"
                    gaps.append(
                        self._gap(
                            "AUTOMATION_FAILING",
                            feature["feature_id"],
                            feature["name"],
                            feature.get("evidence_ids", []),
                            1.0,
                        )
                    )
                elif passed:
                    coverage_status = "VERIFIED"
                elif has_binding:
                    coverage_status = "AUTOMATED"
                elif workspace_test_scan_status == "UNAVAILABLE":
                    coverage_status = "NOT_VERIFIED"
                elif case_matches:
                    coverage_status = (
                        "COVERED" if max(score for _, score in case_matches) >= mapping_threshold else "PARTIAL"
                    )
                elif case_review_matches:
                    coverage_status = "PARTIAL"
                else:
                    coverage_status = "NOT_COVERED"
                feature["coverage_status"] = coverage_status
                feature["automation_scan_status"] = workspace_test_scan_status
                requirement_statuses = [req.get("status", "NOT_VERIFIED") for req in linked_reqs]
                latest_run = self._latest_automation_run(automation)
                gap_categories = [
                    gap["category"]
                    for gap in gaps
                    if gap.get("item_id") == feature["feature_id"]
                    or gap.get("item_id") in feature.get("requirement_ids", [])
                ]
                coverage.append(
                    {
                        "feature_id": feature["feature_id"],
                        "feature": feature["name"],
                        "requirement_ids": feature.get("requirement_ids", []),
                        "requirement_status": "PASS"
                        if requirement_statuses and all(item == "PASS" for item in requirement_statuses)
                        else (
                            requirement_statuses[0]
                            if len(requirement_statuses) == 1
                            else "PARTIAL"
                            if requirement_statuses
                            else "UNDOCUMENTED"
                        ),
                        "product_status": feature.get("status", "OBSERVED"),
                        "test_status": "COVERED"
                        if case_matches
                        else "NEEDS_REVIEW"
                        if case_review_matches
                        else "MISSING",
                        "automation_status": coverage_status
                        if coverage_status in {"AUTOMATED", "AUTOMATION_FAILING", "VERIFIED"}
                        else "NOT_VERIFIED"
                        if coverage_status == "NOT_VERIFIED"
                        else "MISSING",
                        "automation_scan_status": workspace_test_scan_status,
                        "last_run_status": latest_run.get("last_run_status") if latest_run else None,
                        "last_run_id": latest_run.get("last_run_id") if latest_run else None,
                        "gap_categories": gap_categories,
                        "functional_status": feature.get("status", "OBSERVED"),
                        "test_case_ids": case_ids,
                        "test_case_candidates": feature["test_case_candidates"],
                        "automation_candidates": feature["automation_candidates"],
                        "automation": automation,
                        "coverage_status": coverage_status,
                    }
                )
            linked_requirement_ids = {item_id for feature in features for item_id in feature.get("requirement_ids", [])}
            for requirement in requirements:
                if requirement.get("id") in linked_requirement_ids:
                    continue
                coverage.append(
                    {
                        "feature_id": None,
                        "feature": requirement.get("feature", "Requirement"),
                        "requirement_ids": [requirement.get("id")],
                        "requirement_status": requirement.get("status", "NOT_VERIFIED"),
                        "product_status": "NOT_FOUND"
                        if requirement.get("status") == "REQUIRED_NOT_FOUND"
                        else "NOT_VERIFIED",
                        "test_status": "NOT_VERIFIED",
                        "automation_status": "NOT_VERIFIED",
                        "last_run_status": None,
                        "gap_categories": ["IMPLEMENTATION_MISSING"]
                        if requirement.get("status") == "REQUIRED_NOT_FOUND"
                        else ["NOT_VERIFIED"],
                        "functional_status": requirement.get("status", "NOT_VERIFIED"),
                        "test_case_ids": [],
                        "automation": [],
                        "coverage_status": "NOT_VERIFIED",
                    }
                )
            states = result.get("states", [])
            edges = result.get("edges", [])
            for frontier_item in result.get("frontier", []):
                if frontier_item.get("status") == "BLOCKED_BY_POLICY":
                    state = next(
                        (item for item in states if item.get("state_id") == frontier_item.get("state_id")), None
                    )
                    gaps.append(
                        self._gap(
                            "BLOCKED_BY_POLICY",
                            frontier_item.get("candidate_id", "blocked"),
                            str(frontier_item.get("target") or "受安全策略阻止的动作"),
                            [state["evidence_id"]] if state and state.get("evidence_id") else [],
                            1.0,
                        )
                    )
            gaps = list({item["id"]: item for item in gaps}.values())
            result["requirements"] = requirements
            result["features"] = features
            result["gaps"] = gaps
            self._enrich_gap_context(result, requirements=requirements, features=features, states=states)
            workspace_tests = [
                {
                    "nodeid": item.nodeid,
                    "test_name": item.test_name,
                    "file": item.file,
                    "class_name": item.class_name,
                    "markers": item.markers,
                    "line": item.line,
                    "test_case_id": cases_by_nodeid[item.nodeid].id if item.nodeid in cases_by_nodeid else None,
                    "requirement_id": cases_by_nodeid[item.nodeid].requirement_id
                    if item.nodeid in cases_by_nodeid
                    else None,
                }
                for item in collected_tests[:500]
            ]
            result["coverage"] = coverage
            result["workspace_tests"] = workspace_tests
            result["journeys"] = self._build_journeys(states, edges)
            result["quality_map"] = {
                "requirements": requirements,
                "features": features,
                "coverage": coverage,
                "gaps": gaps,
                "workspace_test_scan": result["workspace_test_scan"],
            }
            result["functional_spec"] = self._functional_specification(row, requirements, features, coverage, gaps)
            row.result = result
            row.updated_at = utc_now()
            await session.commit()

    @staticmethod
    def _build_journeys(states: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {item.get("state_id"): item for item in states if item.get("state_id")}
        outgoing: dict[str, list[dict[str, Any]]] = {}
        incoming: set[str] = set()
        for edge in edges:
            source, target = edge.get("from_state_id"), edge.get("to_state_id")
            if source in by_id and target in by_id:
                outgoing.setdefault(source, []).append(edge)
                incoming.add(target)
        roots = [item["state_id"] for item in states if item.get("state_id") not in incoming]
        if not roots and states:
            roots = [states[0].get("state_id")]
        journeys = []

        def step(state_id: str, edge: dict[str, Any] | None = None) -> dict[str, Any]:
            state = by_id[state_id]
            return {
                "state_id": state_id,
                "title": state.get("title") or state.get("page_type") or state.get("url"),
                "url": state.get("url"),
                "page_type": state.get("page_type", "unknown"),
                "action": edge.get("label") if edge else None,
                "evidence_ids": [state["evidence_id"]] if state.get("evidence_id") else [],
            }

        def visit(current: str, path: list[dict[str, Any]], seen: set[str]) -> None:
            if len(journeys) >= 30 or len(path) >= 16:
                return
            branches = [edge for edge in outgoing.get(current, []) if edge.get("to_state_id") not in seen]
            if not branches:
                if path:
                    journeys.append({"journey_id": f"journey-{len(journeys) + 1}", "steps": path})
                return
            for edge in branches:
                target = edge["to_state_id"]
                visit(target, [*path, step(target, edge)], {*seen, target})
                if len(journeys) >= 30:
                    return

        for root in roots:
            if root not in by_id:
                continue
            visit(root, [step(root)], {root})
            if len(journeys) >= 30:
                break
        if not journeys and states:
            journeys.append({"journey_id": "journey-1", "steps": [step(states[0]["state_id"])]})
        return journeys

    @staticmethod
    def _functional_specification(
        row: QualityDiscoveryRunORM,
        requirements: list[dict[str, Any]],
        features: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        requirement_by_id = {item.get("id"): item for item in requirements}
        coverage_by_feature = {item.get("feature_id"): item for item in coverage if item.get("feature_id")}
        specs = []
        for feature in features:
            linked = [
                requirement_by_id[item] for item in feature.get("requirement_ids", []) if item in requirement_by_id
            ]
            feature_gap_items = [
                item
                for item in gaps
                if item.get("item_id") == feature.get("feature_id")
                or item.get("item_id") in feature.get("requirement_ids", [])
            ]
            row_coverage = coverage_by_feature.get(feature["feature_id"], {})
            automation = feature.get("automation", [])
            specs.append(
                {
                    "feature_id": feature["feature_id"],
                    "name": feature.get("name"),
                    "description": feature.get("description", ""),
                    "page_type": feature.get("page_type", "unknown"),
                    "trust": feature.get("trust", feature.get("status", "INFERRED")),
                    "observed": feature.get("status") in {"OBSERVED", "VERIFIED"},
                    "executed": bool(feature.get("verified_by_action_id")),
                    "verified": feature.get("status") == "VERIFIED",
                    "requirement_ids": feature.get("requirement_ids", []),
                    "expected_behavior": [
                        item.get("expected_behavior", "") for item in linked if item.get("expected_behavior")
                    ],
                    "requirement_status": row_coverage.get("requirement_status", "UNDOCUMENTED"),
                    "test_case_ids": feature.get("test_case_ids", []),
                    "test_coverage": row_coverage.get("test_status", "MISSING"),
                    "automation": automation,
                    "last_run_status": row_coverage.get("last_run_status"),
                    "gaps": [item["category"] for item in feature_gap_items],
                    "gap_ids": [item["id"] for item in feature_gap_items],
                    "evidence_ids": feature.get("evidence_ids", []),
                }
            )
        return {
            "title": "Functional Specification",
            "generated_at": utc_now().isoformat(),
            "run_id": row.id,
            "source_of_truth": "Quality Discovery run graph, structured requirements, and linked quality records",
            "disclaimer": "Generated from observed evidence. Inferred items are not verified product behavior.",
            "features": specs,
        }

    @classmethod
    def _evaluate_requirement_checks(
        cls,
        requirement: dict[str, Any],
        states: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        checks = requirement.get("checks") or []
        acceptance_criteria = requirement.get("acceptance_criteria", [])
        repeat_cart_criteria = [
            criterion
            for criterion in acceptance_criteria
            if cls._requirement_allows_repeat_cart_mutation(str(criterion))
        ]
        if not checks and not acceptance_criteria:
            return "NOT_RUN", []

        results = []
        all_passed = True
        expected_behavior = str(requirement.get("expected_behavior") or "")

        def normalize(value: Any) -> str:
            return re.sub(r"\s+", " ", str(value)).strip().casefold()

        normalized_criteria = {normalize(item) for item in acceptance_criteria}
        covered_criteria: set[str] = set()
        for check in checks:
            target = str(check.get("target") or "")
            attribute = check.get("attribute")
            expected = bool(check.get("expected"))
            condition = check.get("when", "always")
            criterion = str(check.get("criterion") or "")
            criterion_to_check = criterion or (expected_behavior if not acceptance_criteria else "")
            criterion_is_declared = (
                normalize(criterion) in normalized_criteria
                if acceptance_criteria
                else bool(expected_behavior) and (not criterion or normalize(criterion) == normalize(expected_behavior))
            )
            if not criterion_is_declared or not cls._check_supports_criterion(check, criterion_to_check):
                if not acceptance_criteria:
                    all_passed = False
                results.append(
                    {
                        "target": target,
                        "attribute": attribute,
                        "status": "NOT_VERIFIED",
                        "reason": "The rule does not directly prove its linked requirement criterion.",
                    }
                )
                continue
            observations = []
            for state in states:
                controls = state.get("controls") or []
                if condition == "after_action" and not any(
                    edge.get("to_state_id") == state.get("state_id")
                    and cls._criterion_action_matches_edge(criterion_to_check, target, edge)
                    for edge in edges or []
                ):
                    continue
                if condition in {"size_unselected", "size_selected"}:
                    size_controls = [
                        control for control in controls if re.search(r"size|尺码", str(control.get("name") or ""), re.I)
                    ]
                    if not size_controls:
                        continue
                    size_selected = any(cls._control_is_selected(control) for control in size_controls)
                    if size_selected != (condition == "size_selected"):
                        continue

                if attribute == "visible":
                    text = str(state.get("main_content") or "")
                    if not text:
                        continue
                    actual = target.casefold() in text.casefold()
                    if actual:
                        observations.append((state, True))
                    continue

                scored = [(cls._similarity(target, str(control.get("name") or "")), control) for control in controls]
                scored = [(score, control) for score, control in scored if score >= 0.45]
                if not scored:
                    continue
                best_score = max(score for score, _control in scored)
                best = [control for score, control in scored if score == best_score]
                observed_values = {
                    cls._control_is_selected(control) if attribute == "selected" else bool(control.get(attribute))
                    for control in best
                }
                if len(observed_values) == 1:
                    observations.append((state, observed_values.pop()))

            if not observations:
                if not acceptance_criteria:
                    all_passed = False
                results.append(
                    {
                        "target": target,
                        "attribute": attribute,
                        "expected": expected,
                        "status": "NOT_VERIFIED",
                    }
                )
                continue

            verified_observations = [(state, actual) for state, actual in observations if state.get("evidence_id")]
            if not verified_observations:
                if not acceptance_criteria:
                    all_passed = False
                results.append(
                    {
                        "target": target,
                        "attribute": attribute,
                        "expected": expected,
                        "status": "NOT_VERIFIED",
                        "reason": "The observation has no persisted evidence reference.",
                    }
                )
                continue

            mismatches = [(state, actual) for state, actual in verified_observations if actual != expected]
            state, actual = mismatches[0] if mismatches else verified_observations[0]
            passed = not mismatches
            results.append(
                {
                    "target": target,
                    "attribute": attribute,
                    "expected": expected,
                    "actual": actual,
                    "state_id": state.get("state_id"),
                    "evidence_id": state.get("evidence_id"),
                    "observations": [
                        {
                            "state_id": observed_state.get("state_id"),
                            "actual": value,
                            "evidence_id": observed_state.get("evidence_id"),
                        }
                        for observed_state, value in observations
                    ],
                    "status": "PASS" if passed else "FAIL",
                }
            )
            if not passed:
                return "FAIL", results
            if acceptance_criteria:
                covered_criteria.add(normalize(criterion))

        for criterion in repeat_cart_criteria:
            result = cls._evaluate_repeat_cart_merge_criterion(criterion, actions or [], states)
            results.append(result)
            if result["status"] == "PASS":
                covered_criteria.add(normalize(criterion))
            elif result["status"] == "FAIL":
                return "FAIL", results
            else:
                all_passed = False

        for criterion in acceptance_criteria:
            normalized = normalize(criterion)
            if normalized in covered_criteria:
                continue
            result = cls._evaluate_evidence_criterion(criterion, states, edges or [], actions or [])
            if result is None:
                continue
            results.append(result)
            if result["status"] == "PASS":
                covered_criteria.add(normalized)
            elif result["status"] == "FAIL":
                return "FAIL", results
            else:
                all_passed = False

        uncovered_criteria = [
            criterion for criterion in acceptance_criteria if normalize(criterion) not in covered_criteria
        ]
        if uncovered_criteria:
            results.append({"status": "NOT_VERIFIED", "uncovered_criteria": uncovered_criteria})
        return ("PASS" if all_passed and not uncovered_criteria else "NOT_VERIFIED"), results

    @classmethod
    def _evaluate_evidence_criterion(
        cls,
        criterion: str,
        states: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        text = criterion.casefold()
        is_empty_search = bool(
            re.search(r"no[- ]match|no results?|empty state|无匹配|无结果|空状态", text)
            and re.search(r"product cards?|商品卡片|商品卡", text)
        )
        is_matching_search = bool(
            not is_empty_search and re.search(r"search|搜索", text) and re.search(r"match|匹配", text)
        )
        is_product_detail = bool(
            re.search(r"product detail|商品详情", text)
            and re.search(r"price|价格", text)
            and re.search(r"add.{0,20}cart|加入购物车", text)
        )
        is_variant_retained = bool(
            re.search(r"color|colour|size|颜色|尺码", text)
            and re.search(r"cart|购物车", text)
            and re.search(r"retain|selected|保留|所选规格", text)
        )
        is_cart_arithmetic = bool(
            re.search(r"cart|购物车", text)
            and re.search(r"quantity|数量", text)
            and re.search(r"price|金额|价格", text)
            and re.search(r"\*|乘|multiply|calculated|符合", text)
        )
        if not any((is_empty_search, is_matching_search, is_product_detail, is_variant_retained, is_cart_arithmetic)):
            return None

        def result(check: str, status: str, state=None, expected=None, actual=None, reason=None):
            item = {
                "criterion": criterion,
                "check": check,
                "status": status,
                "state_id": (state or {}).get("state_id"),
                "evidence_id": (state or {}).get("evidence_id"),
            }
            if expected is not None:
                item["expected"] = expected
            if actual is not None:
                item["actual"] = actual
            if reason:
                item["reason"] = reason
            return item

        def after(action, *, include_later_states: bool = False):
            finished_at = action.get("finished_at")
            if not finished_at:
                return []
            edge_state_ids = {
                edge.get("to_state_id")
                for edge in edges
                if edge.get("candidate_id") == action.get("candidate_id")
                and edge.get("from_state_id") == action.get("from_state_id")
                and edge.get("to_state_id")
            }
            fingerprint = action.get("to_fingerprint")
            related = [
                state
                for state in states
                if state.get("state_id") in edge_state_ids or (fingerprint and state.get("fingerprint") == fingerprint)
            ]
            if include_later_states or not related:
                related_ids = {state.get("state_id") for state in related}
                related.extend(
                    state
                    for state in states
                    if state.get("state_id") not in related_ids
                    and cls._timestamp_after(state.get("observed_at"), finished_at)
                )
            return related

        executed_searches = [
            action
            for action in actions
            if action.get("status") == "EXECUTED"
            and action.get("action_type") == "search"
            and str(action.get("search_value") or "").strip()
        ]
        if is_empty_search or is_matching_search:
            searches = [
                action
                for action in executed_searches
                if (str(action.get("search_value") or "").casefold().startswith("zzqa-no-matching-item"))
                == is_empty_search
            ]
            if is_matching_search:
                searches = [
                    action
                    for action in searches
                    if not str(action.get("search_value") or "").casefold().startswith("zzqa-no-matching-item")
                ]
            if not searches:
                return result(
                    "empty_search_state" if is_empty_search else "case_insensitive_product_search",
                    "NOT_VERIFIED",
                    reason="No matching executed search action has persisted evidence yet.",
                )
            search = searches[-1]
            following_states = after(search)
            following_states.sort(
                key=lambda item: (
                    cls._parse_timestamp(item.get("observed_at")) or datetime.max.replace(tzinfo=timezone.utc)
                )
            )
            state = next((item for item in following_states if item.get("evidence_id")), None)
            if state is None:
                return result(
                    "empty_search_state" if is_empty_search else "case_insensitive_product_search",
                    "NOT_VERIFIED",
                    reason="The search result state has no persisted evidence reference.",
                )
            content = str(state.get("main_content") or "")
            product_names = [
                match.group(1).strip()
                for control in state.get("controls") or []
                if (match := re.match(r"view\s+(.+)", str(control.get("name") or ""), re.I))
            ]
            if is_empty_search:
                has_empty_message = bool(re.search(r"no products found|no results?|未找到商品|没有找到", content, re.I))
                passed = has_empty_message and not product_names
                failed = bool(product_names)
                return result(
                    "empty_search_state",
                    "PASS" if passed else "FAIL" if failed else "NOT_VERIFIED",
                    state,
                    {"empty_state": True, "product_cards": 0},
                    {"empty_state": has_empty_message, "product_cards": len(product_names)},
                )
            query = str(search.get("search_value") or "").strip()
            matched = [name for name in product_names if query.casefold() in name.casefold()]
            case_differs = any(
                name.casefold().find(query.casefold()) >= 0
                and name[name.casefold().find(query.casefold()) : name.casefold().find(query.casefold()) + len(query)]
                != query
                for name in matched
            )
            passed = bool(matched) and len(matched) == len(product_names) and case_differs
            failed = bool(product_names) and not passed
            return result(
                "case_insensitive_product_search",
                "PASS" if passed else "FAIL" if failed else "NOT_VERIFIED",
                state,
                {"all_visible_products_match_query": True, "case_insensitive_match": True},
                {"query": query, "visible_products": product_names, "matching_products": matched},
            )

        if is_product_detail:
            detail_states = [
                state
                for state in states
                if state.get("evidence_id")
                and any(
                    cls._is_cart_mutation_label(str(control.get("name") or ""))
                    for control in state.get("controls") or []
                )
                and re.search(r"\$\s*[0-9,]+(?:\.\d{1,2})?", str(state.get("main_content") or ""))
            ]
            if not detail_states:
                return result("product_detail_purchase_controls", "NOT_VERIFIED")
            state = detail_states[-1]
            content = str(state.get("main_content") or "")
            add_control = next(
                control
                for control in state.get("controls") or []
                if cls._is_cart_mutation_label(str(control.get("name") or ""))
            )
            has_name = bool(
                re.search(r"heading\s+\"[^\"]+\"\s+\[level=1\]", str(state.get("landmarks") or ""), re.I)
            ) or bool(re.search(r"[A-Z][A-Za-z0-9' -]{2,}", content))
            has_price = bool(re.search(r"\$\s*[0-9,]+(?:\.\d{1,2})?", content))
            enabled = bool(add_control.get("enabled", True))
            passed = has_name and has_price and enabled
            return result(
                "product_detail_purchase_controls",
                "PASS" if passed else "FAIL",
                state,
                {"product_name": True, "price": True, "add_to_cart_enabled": True},
                {"product_name": has_name, "price": has_price, "add_to_cart_enabled": enabled},
            )

        cart_adds = [
            action
            for action in actions
            if action.get("status") == "EXECUTED" and cls._is_cart_mutation_label(str(action.get("target") or ""))
        ]
        if is_variant_retained:
            state_by_id = {item.get("state_id"): item for item in states}
            selection_values = {}
            selection_scopes = {}
            for action in actions:
                if action.get("status") != "EXECUTED" or action.get("action_type") != "select":
                    continue
                source = state_by_id.get(action.get("from_state_id"), {})
                target = str(action.get("target") or "")
                if re.search(r"color|colour|颜色", target, re.I):
                    selection_values["color"] = str(action.get("selected_value") or "")
                    selection_scopes["color"] = cls._product_scope_key(source)
                elif re.search(r"size|尺码", target, re.I):
                    selection_values["size"] = str(action.get("selected_value") or "")
                    selection_scopes["size"] = cls._product_scope_key(source)
            selected = [value for value in selection_values.values() if value]
            if len(selected) < 2 or len(set(selection_scopes.values())) != 1 or not cart_adds:
                return result(
                    "selected_variant_retained_in_cart",
                    "NOT_VERIFIED",
                    actual={"selected_values": selection_values},
                )
            latest_add = cart_adds[-1]
            candidates = after(latest_add, include_later_states=True)
            candidates.sort(
                key=lambda item: (
                    cls._parse_timestamp(item.get("observed_at")) or datetime.max.replace(tzinfo=timezone.utc)
                )
            )
            state = next(
                (
                    item
                    for item in candidates
                    if item.get("evidence_id")
                    and re.search(
                        r"shopping cart|your selection|quantity\s*:|数量\s*[:：]?|total\s*:",
                        f"{item.get('title') or ''} {item.get('main_content') or ''}",
                        re.I,
                    )
                    and all(value.casefold() in str(item.get("main_content") or "").casefold() for value in selected)
                ),
                None,
            )
            if state is None:
                return result(
                    "selected_variant_retained_in_cart",
                    "NOT_VERIFIED",
                    actual={"selected_values": selection_values, "cart_after_add": False},
                )
            return result(
                "selected_variant_retained_in_cart",
                "PASS",
                state,
                {"selected_values": selected},
                {"selected_values": selected, "cart_content": str(state.get("main_content") or "")[:240]},
            )

        if not cart_adds:
            return result("cart_amount_matches_price_times_quantity", "NOT_VERIFIED")
        latest_add = cart_adds[-1]
        cart_states = [
            state
            for state in after(latest_add, include_later_states=True)
            if state.get("evidence_id")
            and re.search(
                r"(?:total|总计|合计)\s*[:：]?\s*\$\s*[0-9,]+(?:\.\d{1,2})?", str(state.get("main_content") or ""), re.I
            )
        ]
        if not cart_states:
            return result("cart_amount_matches_price_times_quantity", "NOT_VERIFIED")
        state = cart_states[-1]
        content = str(state.get("main_content") or "")
        quantity_matches = re.findall(r"(?:quantity|数量)\s*[:：]?\s*(\d+)", content, re.I)
        total_match = re.search(r"(?:total|总计|合计)\s*[:：]?\s*\$\s*([0-9,]+(?:\.\d{1,2})?)", content, re.I)
        product_state = next(
            (item for item in states if item.get("state_id") == latest_add.get("from_state_id")),
            {},
        )
        unit_match = re.search(r"\$\s*([0-9,]+(?:\.\d{1,2})?)", str(product_state.get("main_content") or ""))
        if len(quantity_matches) != 1 or not total_match or not unit_match:
            return result("cart_amount_matches_price_times_quantity", "NOT_VERIFIED", state)
        quantity = int(quantity_matches[0])
        unit_price = Decimal(unit_match.group(1).replace(",", ""))
        total = Decimal(total_match.group(1).replace(",", ""))
        expected_total = unit_price * quantity
        passed = total == expected_total
        return result(
            "cart_amount_matches_price_times_quantity",
            "PASS" if passed else "FAIL",
            state,
            {"unit_price_times_quantity": str(expected_total)},
            {"unit_price": str(unit_price), "quantity": quantity, "total": str(total)},
        )

    @classmethod
    def _all_acceptance_criteria_passed(
        cls,
        requirements: list[dict[str, Any]],
        states: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> bool:
        declared = [item for item in requirements if item.get("acceptance_criteria")]
        return bool(declared) and all(
            not item.get("ambiguous") and cls._evaluate_requirement_checks(item, states, edges, actions)[0] == "PASS"
            for item in declared
        )

    @classmethod
    def _evaluate_repeat_cart_merge_criterion(
        cls,
        criterion: str,
        actions: list[dict[str, Any]],
        states: list[dict[str, Any]],
    ) -> dict[str, Any]:
        additions = [
            action
            for action in actions
            if action.get("status") == "EXECUTED"
            and cls._is_cart_mutation_label(str(action.get("target") or ""))
            and action.get("cart_variant_key")
        ]
        by_variant: dict[str, list[dict[str, Any]]] = {}
        for action in additions:
            by_variant.setdefault(str(action["cart_variant_key"]), []).append(action)
        repeated_adds = max(by_variant.values(), key=len, default=[])
        if len(repeated_adds) < 2:
            return {
                "criterion": criterion,
                "check": "same_variant_quantity_merge",
                "expected": {"same_variant_adds": 2, "quantity": 2},
                "actual": {"same_variant_adds": len(repeated_adds)},
                "status": "NOT_VERIFIED",
            }

        latest_add = max(
            repeated_adds,
            key=lambda item: cls._parse_timestamp(item.get("finished_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        cart_states = [
            state
            for state in states
            if (
                str(state.get("page_type") or "").casefold() in {"cart", "shopping_cart", "cart_populated"}
                or re.search(
                    r"shopping cart|购物车",
                    f"{state.get('title') or ''} {state.get('main_content') or ''}",
                    re.I,
                )
            )
            and state.get("observed_at")
            and latest_add.get("finished_at")
            and cls._timestamp_after(state["observed_at"], latest_add["finished_at"])
        ]
        if not cart_states:
            return {
                "criterion": criterion,
                "check": "same_variant_quantity_merge",
                "expected": {"same_variant_adds": 2, "quantity": 2},
                "actual": {"same_variant_adds": len(repeated_adds), "cart_after_last_add": False},
                "status": "NOT_VERIFIED",
            }

        cart_state = max(
            cart_states,
            key=lambda item: cls._parse_timestamp(item.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        if not cart_state.get("evidence_id"):
            return {
                "criterion": criterion,
                "check": "same_variant_quantity_merge",
                "expected": {"same_variant_adds": 2, "quantity": 2},
                "actual": {"same_variant_adds": len(repeated_adds), "cart_evidence": False},
                "state_id": cart_state.get("state_id"),
                "status": "NOT_VERIFIED",
            }
        content = str(cart_state.get("main_content") or "")
        quantity_match = re.search(r"(?:quantity|数量)\s*[:：]?\s*(\d+)", content, re.I)
        total_match = re.search(r"(?:total|总计|合计)\s*[:：]?\s*\$\s*([0-9,]+(?:\.\d{1,2})?)", content, re.I)
        state_by_id = {state.get("state_id"): state for state in states}
        product_state = state_by_id.get(repeated_adds[0].get("from_state_id"), {})
        unit_match = re.search(r"\$\s*([0-9,]+(?:\.\d{1,2})?)", str(product_state.get("main_content") or ""))
        if not quantity_match or not total_match or not unit_match:
            return {
                "criterion": criterion,
                "check": "same_variant_quantity_merge",
                "expected": {"same_variant_adds": 2, "quantity": 2},
                "actual": {"same_variant_adds": len(repeated_adds)},
                "state_id": cart_state.get("state_id"),
                "evidence_id": cart_state.get("evidence_id"),
                "status": "NOT_VERIFIED",
            }

        quantity = int(quantity_match.group(1))
        unit_price = Decimal(unit_match.group(1).replace(",", ""))
        total = Decimal(total_match.group(1).replace(",", ""))
        expected_total = unit_price * 2
        passed = quantity == 2 and total == expected_total
        return {
            "criterion": criterion,
            "check": "same_variant_quantity_merge",
            "expected": {"same_variant_adds": 2, "quantity": 2, "total": str(expected_total)},
            "actual": {
                "same_variant_adds": len(repeated_adds),
                "quantity": quantity,
                "unit_price": str(unit_price),
                "total": str(total),
            },
            "state_id": cart_state.get("state_id"),
            "evidence_id": cart_state.get("evidence_id"),
            "status": "PASS" if passed else "FAIL",
        }

    @staticmethod
    def _timestamp_after(left: Any, right: Any) -> bool:
        left_value = QualityDiscoveryService._parse_timestamp(left)
        right_value = QualityDiscoveryService._parse_timestamp(right)
        return left_value is not None and right_value is not None and left_value >= right_value

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _check_supports_criterion(cls, check: dict[str, Any], criterion: str) -> bool:
        target = str(check.get("target") or "")
        attribute = check.get("attribute")
        expected = bool(check.get("expected"))
        condition = check.get("when", "always")
        text = str(criterion or "").casefold()
        if not target or cls._similarity(target, text) < 0.45:
            return False
        if attribute == "visible" and not cls._criterion_quotes_target(target, criterion):
            return False
        if not cls._criterion_only_asserts_target_predicate(target, text, attribute):
            return False
        if cls._criterion_has_unverifiable_relation(text):
            return False

        if attribute == "visible":
            directly_visible = re.search(
                r"\b(displayed|visible|shown|appears?|display)\b|显示|展示|可见|出现|呈现", text
            )
            if not directly_visible or not expected:
                return False
            stop_words = {
                "a",
                "an",
                "the",
                "for",
                "when",
                "after",
                "with",
                "is",
                "are",
                "was",
                "were",
                "to",
                "by",
                "and",
                "or",
                "of",
                "in",
                "on",
                "at",
                "from",
            }
            target_terms = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", target.casefold())
            specific_terms = [term for term in target_terms if term not in stop_words]
            if (
                len(specific_terms) < 3
                and sum(len(term) for term in specific_terms if re.search(r"[\u4e00-\u9fff]", term)) < 6
            ):
                return False
            outcome = re.search(
                r"\b(after|once|when|submitted|returns?|updated|loaded)\b|之后|后|提交|返回|更新|加载", text
            )
            if outcome and condition != "after_action":
                return False
        elif attribute == "enabled":
            affirmative = re.search(r"\b(enabled|active|available|clickable|usable)\b|可用|启用|可点击|可操作", text)
            negative = re.search(
                r"\b(disabled|unavailable|not enabled|not clickable)\b|不可用|禁用|不可点击|无法点击", text
            )
            if expected and (not affirmative or negative) or not expected and not negative:
                return False
        elif attribute == "selected":
            affirmative = re.search(r"\b(selected|checked|chosen)\b|选中|已选|勾选", text)
            negative = re.search(
                r"\b(unselected|unchecked|not selected|not checked|not chosen)\b|未选|未选择|未勾选", text
            )
            if expected and (not affirmative or negative) or not expected and not negative:
                return False
        else:
            return False

        if condition == "size_unselected":
            return bool(
                re.search(r"size|尺码", text)
                and re.search(r"unselected|not selected|no size|until.{0,40}selected|未选|未选择", text)
            )
        if condition == "size_selected":
            return bool(
                re.search(r"size|尺码", text)
                and re.search(r"selected|chosen|已选|选中", text)
                and not re.search(r"unselected|not selected|未选", text)
            )
        if condition == "after_action":
            return attribute == "visible" and bool(
                re.search(r"\b(after|once|when|submit(?:ted|ting)?|loaded)\b|之后|后|提交|查询|搜索|加载", text)
            )
        return condition == "always"

    @staticmethod
    def _criterion_quotes_target(target: str, criterion: str) -> bool:
        text = str(criterion or "").casefold()
        literal = str(target or "").casefold()
        quote_pairs = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』"), ("`", "`"))
        return any(f"{opening}{literal}{closing}" in text for opening, closing in quote_pairs)

    @staticmethod
    def _criterion_only_asserts_target_predicate(target: str, criterion: str, attribute: str) -> bool:
        target_text = target.casefold()
        target_index = criterion.find(target_text)
        if target_index < 0:
            return False
        remainder = f"{criterion[:target_index]} {criterion[target_index + len(target_text) :]}"
        tokens = re.findall(r"[a-z]+(?:'[a-z]+)?|[\u4e00-\u9fff]+|\d+", remainder)
        common = {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "be",
            "being",
            "been",
            "to",
            "in",
            "on",
            "at",
            "by",
            "from",
            "when",
            "after",
            "once",
            "if",
            "until",
            "without",
            "no",
            "not",
            "should",
            "must",
            "can",
            "could",
            "only",
        }
        allowed = {
            "visible": common
            | {
                "displayed",
                "visible",
                "shown",
                "appears",
                "appear",
                "present",
                "returned",
                "returns",
                "result",
                "results",
                "search",
                "query",
                "submit",
                "submitted",
                "submitting",
                "loaded",
                "load",
                "page",
                "for",
                "with",
            },
            "enabled": common
            | {
                "button",
                "enabled",
                "active",
                "available",
                "clickable",
                "usable",
                "disabled",
                "unavailable",
                "size",
                "selected",
            },
            "selected": common
            | {
                "selected",
                "checked",
                "chosen",
                "unselected",
                "unchecked",
                "size",
            },
        }.get(attribute, set())
        english_tokens = [token for token in tokens if not re.search(r"[\u4e00-\u9fff]", token)]
        if not all(token in allowed for token in english_tokens):
            return False
        predicates = {
            "visible": {"displayed", "visible", "shown", "appears", "appear", "display"},
            "enabled": {"enabled", "active", "available", "clickable", "usable", "disabled", "unavailable"},
            "selected": {"selected", "checked", "chosen", "unselected", "unchecked"},
        }.get(attribute, set())
        cjk_tokens = [token for token in tokens if re.search(r"[\u4e00-\u9fff]", token)]
        cjk_remainder = "".join(cjk_tokens)
        cjk_predicates = {
            "visible": ("显示", "展示", "可见", "出现", "呈现"),
            "enabled": ("启用", "可用", "不可用", "禁用", "可点击", "不可点击"),
            "selected": ("选中", "未选中", "选择", "勾选", "未勾选"),
        }.get(attribute, ())
        if not predicates.intersection(english_tokens) and not any(item in cjk_remainder for item in cjk_predicates):
            return False
        if not cjk_tokens:
            return True
        allowed_cjk = {
            "visible": {
                "显示",
                "会显示",
                "将显示",
                "出现",
                "会出现",
                "呈现",
                "展示",
                "可见",
                "返回",
                "显示在页面上",
                "在页面上显示",
                "查询后显示",
                "搜索后显示",
                "提交后显示",
                "查询后出现",
                "搜索后出现",
            },
            "enabled": {
                "启用",
                "已启用",
                "可用",
                "不可用",
                "禁用",
                "不可点击",
                "可点击",
                "选中",
                "未选中",
                "尺码",
                "尺寸",
            },
            "selected": {"选中", "已选中", "未选中", "未选择", "勾选", "已勾选", "未勾选", "尺码", "尺寸"},
        }.get(attribute, set())
        return cjk_remainder in allowed_cjk

    @staticmethod
    def _criterion_has_unverifiable_relation(text: str) -> bool:
        comparative_or_state_change = re.search(
            r"\b(increas(?:e|es|ed|ing)|decreas(?:e|es|ed|ing)|chang(?:e|es|ed|ing)|"
            r"updat(?:e|es|ed|ing)|grow(?:s|n|ing)?|shrink(?:s|ing)?|more|fewer|less|"
            r"higher|lower|greater|smaller|larger|increment(?:s|ed|ing)?|decrement(?:s|ed|ing)?|"
            r"twice|double(?:s|d)?|half|halves|halved|previous|prior|before|compared|comparison|"
            r"same|equal|difference|versus|vs\.?|then|because|therefore|caus(?:e|es|ed|ing)|"
            r"accurate|accuracy|correct(?:ly)?|incorrect|valid|invalid|complete|completed|successful|successfully|"
            r"proper(?:ly)?|expected|intended|reliable|trust(?:worthy|ed|ing)?|credible|relevant|sufficient|"
            r"appropriate|meaningful|useful|effective|efficient|secure|safe|robust|resilient|optimized|"
            r"consistent|stable|supported|compliant|intuitive|accessible|healthy|works?|working|"
            r"exactly|minimum|maximum|min|max|threshold|limit|at least|at most|no more than|no less than|"
            r"no fewer than|fewer than|less than|more than|exceed(?:s|ed|ing)?|above|below|"
            r"\d+(?:\.\d+)?\s*(?:%|x|times?)?)\b"
            r"|增加|减少|变化|更新|增长|下降|更多|更少|变大|变小|提高|降低|翻倍|倍增|一半|之前|此前|原来|相比|比较|相同|一样|等于|差异|然后|导致|因此|至少|至多|恰好|正好|最少|最多|最低|最高|超过|不低于|不超过|少于|高于|低于|阈值|上限|下限|准确|正确|有效|无效|完整|成功|符合预期|正常工作|可信|值得信赖|可信赖|相关|充足|适当|有意义|有用|高效|安全|稳健|可靠|一致|稳定|合规|直观|可访问|易用",
            text,
        )
        compound_claim = re.search(
            r"\b(?:and|or|but|while|whereas|which|that)\b|以及|并且|但是|同时|而且",
            text,
        )
        return bool(comparative_or_state_change or compound_claim)

    @staticmethod
    def _criterion_action_matches_edge(criterion: str, target: str, edge: dict[str, Any]) -> bool:
        text = str(criterion or "").casefold()
        action = str(edge.get("action") or "").casefold()
        label = str(edge.get("label") or "")
        if re.search(r"search|query|submit|搜索|查询|提交", text):
            return action == "search"
        if re.search(r"filter|筛选", text):
            return action in {"filter", "select"}
        if re.search(r"sort|排序", text):
            return action in {"select", "filter"}
        if re.search(r"select|choose|selected|chosen|选择|选中", text):
            return action == "select"
        if re.search(r"cart|bag|add(?:ed|ing)? to|加入购物车|添加到购物车", text):
            return action == "click" and QualityDiscoveryService._similarity(target, label) >= 0.45
        if re.search(r"open(?:ed|ing)?|navigate|visit|打开|进入|导航", text):
            return action in {"click", "navigate"} and QualityDiscoveryService._similarity(target, label) >= 0.45
        return False

    @staticmethod
    def _control_is_selected(control: dict[str, Any]) -> bool:
        if control.get("selected") or control.get("checked"):
            return True
        if control.get("tag") != "select":
            return False
        value = str(control.get("value") or "").strip()
        return bool(value and not re.search(r"^(choose|select|pick|please select|--|none|尺码|请选择)", value, re.I))

    @staticmethod
    def _latest_execution(nodeid: str | None, runs: list[Any]) -> tuple[Any, Any] | None:
        if not nodeid:
            return None
        for run in runs:
            matching = [execution for execution in run.executions if execution.nodeid == nodeid]
            if matching:
                return run, matching[0]
        return None

    @staticmethod
    def _latest_execution_status(nodeid: str | None, runs: list[Any]) -> str | None:
        latest = QualityDiscoveryService._latest_execution(nodeid, runs)
        return latest[1].status if latest else None

    @staticmethod
    def _latest_automation_run(automation: list[dict[str, Any]]) -> dict[str, Any] | None:
        def created_at(item: dict[str, Any]) -> datetime:
            value = item.get("last_run_at")
            if isinstance(value, datetime):
                parsed = value
            elif value:
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError:
                    return datetime.min.replace(tzinfo=timezone.utc)
            else:
                return datetime.min.replace(tzinfo=timezone.utc)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

        return max(automation, key=created_at, default=None)

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        def tokenize(value: str) -> set[str]:
            return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", (value or "").casefold()))

        a, b = tokenize(left), tokenize(right)
        if not a or not b:
            return 1.0 if (left or "").strip().casefold() == (right or "").strip().casefold() else 0.0
        if (left or "").strip().casefold() in (right or "").strip().casefold() or (right or "").strip().casefold() in (
            left or ""
        ).strip().casefold():
            return 0.9
        return len(a & b) / len(a | b)

    @staticmethod
    def _enrich_gap_context(
        result: dict[str, Any],
        *,
        requirements: list[dict[str, Any]] | None = None,
        features: list[dict[str, Any]] | None = None,
        states: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        requirements = requirements if requirements is not None else result.get("requirements") or []
        features = features if features is not None else result.get("features") or []
        states = states if states is not None else result.get("states") or []
        requirements_by_id = {item.get("id"): item for item in requirements if item.get("id")}
        features_by_id = {item.get("feature_id"): item for item in features if item.get("feature_id")}
        states_by_id = {item.get("state_id"): item for item in states if item.get("state_id")}

        for gap in result.get("gaps", []):
            direct_requirement = requirements_by_id.get(gap.get("item_id"))
            feature = features_by_id.get(gap.get("item_id"))
            requirement_ids = (feature.get("requirement_ids") or []) if feature else []
            linked_requirements = [requirements_by_id[item] for item in requirement_ids if item in requirements_by_id]
            if direct_requirement:
                linked_requirements = [direct_requirement]
            labels = list(dict.fromkeys(str(item.get("feature") or "").strip() for item in linked_requirements))
            gap["requirement"] = "; ".join(item for item in labels if item) or None
            expected_items = []
            for item in linked_requirements:
                criteria = item.get("acceptance_criteria") or [item.get("expected_behavior", "")]
                if isinstance(criteria, str):
                    criteria = [criteria]
                expected_items.extend(str(criterion).strip() for criterion in criteria if str(criterion).strip())
            gap["expected"] = list(dict.fromkeys(expected_items))[:8]

            observations: list[str] = []
            if direct_requirement:
                for check in (direct_requirement.get("check_results") or [])[:5]:
                    target = str(check.get("target") or "").strip()
                    actual = check.get("actual")
                    status = str(check.get("status") or "NOT_VERIFIED")
                    if actual is not None:
                        observations.append(
                            f"{target}: observed {actual} ({status})" if target else f"Observed {actual} ({status})"
                        )
                    elif target:
                        observations.append(f"{target}: {status}")
                if not observations and direct_requirement.get("check_status"):
                    observations.append(f"Requirement checks: {direct_requirement['check_status']}")
            if feature:
                observed_states = [
                    states_by_id[item] for item in (feature.get("state_ids") or []) if item in states_by_id
                ]
                page_names = list(
                    dict.fromkeys(
                        str(state.get("title") or state.get("page_type") or "").strip()
                        for state in observed_states
                        if str(state.get("title") or state.get("page_type") or "").strip()
                    )
                )[:3]
                description = str(feature.get("description") or "").strip()
                observations.append(
                    f"Feature {feature.get('name', 'unknown')} is {feature.get('status', 'OBSERVED')}"
                    + (f" on {', '.join(page_names)}" if page_names else "")
                    + (f": {description[:240]}" if description else "")
                )
                if gap.get("category") == "AUTOMATION_MISSING":
                    observations.append(
                        f"Linked test cases: {len(feature.get('test_case_ids') or [])}; no active automation is mapped."
                    )
                elif gap.get("category") == "AUTOMATION_FAILING":
                    failing = [
                        item
                        for item in (feature.get("automation") or [])
                        if item.get("last_run_status") in {"FAILED", "ERROR"}
                    ]
                    if failing:
                        observations.append(
                            "Latest automation result: "
                            + "; ".join(
                                f"{item.get('test_case_title', 'test')}: {item.get('last_run_status')}"
                                for item in failing[:3]
                            )
                        )
            if not feature and not direct_requirement and gap.get("category") == "BLOCKED_BY_POLICY":
                frontier_item = next(
                    (item for item in result.get("frontier", []) if item.get("candidate_id") == gap.get("item_id")),
                    None,
                )
                if frontier_item:
                    observations.append(str(frontier_item.get("reason") or "Action was blocked by the safety policy."))
            gap["observed"] = "; ".join(observations)[:800] or None
        return result

    @staticmethod
    def _gap(category: str, item_id: str, title: str, evidence_ids: list[str], confidence: float) -> dict[str, Any]:
        risk = (
            "HIGH"
            if category in {"IMPLEMENTED_BROKEN", "REQUIRED_NOT_FOUND", "FUNCTION_BROKEN", "IMPLEMENTATION_MISSING"}
            else "MEDIUM"
        )
        return {
            "id": f"gap-{category.lower()}-{hashlib.sha256(item_id.encode()).hexdigest()[:10]}",
            "category": category,
            "item_id": item_id,
            "title": title,
            "risk": risk,
            "confidence": round(confidence, 2),
            "evidence_ids": evidence_ids,
            "suggested_action": {
                "TEST_MISSING": "Generate Tests",
                "AUTOMATION_MISSING": "Generate Automation",
                "AUTOMATION_FAILING": "Open Failure",
                "TEST_INCOMPLETE": "Review Test Mapping",
                "NOT_VERIFIED": "Review Evidence",
                "BLOCKED_BY_POLICY": "Review Safety Policy",
                "UNDOCUMENTED_FEATURE": "Create Requirement Draft",
                "REQUIRED_NOT_FOUND": "Review Evidence",
                "IMPLEMENTED_BROKEN": "Open Failure",
                "FUNCTION_BROKEN": "Open Failure",
                "IMPLEMENTATION_MISSING": "Review Evidence",
                "IMPLEMENTATION_PARTIAL": "Review Evidence",
                "REQUIREMENT_AMBIGUOUS": "Clarify Requirement",
            }.get(category, "Review Evidence"),
        }

    async def _wait_if_paused(self, run_id: str) -> None:
        event = self._resume_events.setdefault(run_id, asyncio.Event())
        await event.wait()
        if self._stop_events.setdefault(run_id, asyncio.Event()).is_set():
            return

    async def _event(self, run_id: str, event_type: str, message: str, metadata: dict[str, Any] | None = None) -> None:
        def change(result):
            events = result.setdefault("events", [])
            events.append(
                {
                    "id": uuid4().hex[:12],
                    "type": event_type,
                    "message": message[:300],
                    "metadata": metadata or {},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            del events[: -get_config().discovery.max_events]

        await self._change_result(run_id, change)

    async def _finish(self, run_id: str, status: str, error: str | None) -> None:
        await self._update(
            run_id, status=status, error=error, finished_at=utc_now() if status in self.TERMINAL else None
        )
        await self._event(run_id, f"run.{status.lower()}", error or f"探索状态：{status}")

    async def _change_result(self, run_id: str, change: Callable[[dict[str, Any]], None]) -> None:
        for attempt in range(5):
            try:
                async with self.session_factory() as session:
                    repo = QualityDiscoveryRepository(session)
                    row = await repo.get(run_id)
                    if row is None:
                        return
                    result = json.loads(json.dumps(row.result or {}))
                    change(result)
                    states, actions, features = (result.get(name, []) for name in ("states", "actions", "features"))
                    await repo.update(
                        run_id,
                        result=result,
                        progress={"states": len(states), "actions": len(actions), "features": len(features)},
                    )
                    await session.commit()
                return
            except (StaleDataError, OperationalError) as exc:
                if not self._is_retryable_write_conflict(exc) or attempt == 4:
                    raise
                await asyncio.sleep(0.01 * (attempt + 1))

    async def _update(self, run_id: str, **values) -> QualityDiscoveryRunORM | None:
        for attempt in range(5):
            try:
                async with self.session_factory() as session:
                    row = await QualityDiscoveryRepository(session).update(run_id, **values)
                    await session.commit()
                    return row
            except (StaleDataError, OperationalError) as exc:
                if not self._is_retryable_write_conflict(exc) or attempt == 4:
                    raise
                await asyncio.sleep(0.01 * (attempt + 1))
        return None

    @staticmethod
    def _is_retryable_write_conflict(error: Exception) -> bool:
        return isinstance(error, StaleDataError) or (
            isinstance(error, OperationalError) and "database is locked" in str(error).lower()
        )


def tag_is_text(value: Any) -> bool:
    return value in {"button", "a", "span", "div", "label"}


def discovery_run_dict(row: QualityDiscoveryRunORM) -> dict[str, Any]:
    result = row.result or {}
    return {
        "id": row.id,
        "project_id": row.project_id,
        "mode": row.mode,
        "start_url": row.start_url,
        "requirement_id": row.requirement_id,
        "status": row.status,
        "error": row.error,
        "progress": row.progress or {},
        "result": result,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "finished_at": row.finished_at,
    }
