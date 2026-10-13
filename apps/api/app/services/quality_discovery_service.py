from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from project_model.lifecycle import StructuredRequirementModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.persistence.models import QualityDiscoveryRunORM, utc_now
from app.ports.browser_runtime import BrowserRuntime
from app.repositories.project_repo import ProjectRepository
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.decision_service import DecisionService
from app.services.quality_discovery_draft import QualityDiscoveryDraftMixin
from app.services.quality_discovery_execution import QualityDiscoveryExecutionMixin, tag_is_text
from app.services.quality_discovery_graph import QualityDiscoveryGraphMixin
from app.services.quality_discovery_models import (
    DiscoveryBlocked,
    DiscoveryGoal,
    DiscoveryMode,
    DiscoveryPlan,
    DiscoveryRunCreate,
    DiscoveryStatus,
    ExpectedState,
    ExpectedTransition,
    FeatureSignal,
    RequirementAnalysis,
    RequirementAnalysisItem,
    RequirementCheck,
    RequirementSignal,
)
from app.services.quality_discovery_projection import QualityDiscoveryProjectionMixin
from app.settings import get_config

if TYPE_CHECKING:
    from app.services.task_command_service import TaskCommandService

__all__ = [
    "DiscoveryBlocked",
    "DiscoveryGoal",
    "DiscoveryMode",
    "DiscoveryPlan",
    "DiscoveryRunCreate",
    "DiscoveryStatus",
    "ExpectedState",
    "ExpectedTransition",
    "FeatureSignal",
    "QualityDiscoveryService",
    "RequirementAnalysis",
    "RequirementAnalysisItem",
    "RequirementCheck",
    "RequirementSignal",
    "discovery_run_dict",
    "tag_is_text",
]


class _GapActionLockEntry:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.users = 0


class QualityDiscoveryService(
    QualityDiscoveryExecutionMixin,
    QualityDiscoveryGraphMixin,
    QualityDiscoveryProjectionMixin,
    QualityDiscoveryDraftMixin,
):
    """Runs bounded, evidence-backed product exploration independently of Browser Agent goals."""

    TERMINAL = {
        DiscoveryStatus.COMPLETED.value,
        DiscoveryStatus.BLOCKED.value,
        DiscoveryStatus.FAILED.value,
        DiscoveryStatus.STOPPED.value,
        DiscoveryStatus.BUDGET_EXHAUSTED.value,
    }

    @staticmethod
    def _get_config():
        return get_config()

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        browser_runtime: BrowserRuntime,
        decisions: DecisionService | None = None,
        provider_factory: Callable | None = None,
        workspace_service=None,
        task_commands: TaskCommandService | None = None,
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
        self.task_commands = task_commands
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
