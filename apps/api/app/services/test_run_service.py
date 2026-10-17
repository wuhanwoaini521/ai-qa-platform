from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator

from integrations.jenkins_runner import JenkinsConfig, JenkinsRunnerBackend
from project_model.models import (
    ExternalArtifactReference,
    RunnerType,
    RunStatus,
    TestBrowserSession,
    TestExecution,
    TestRun,
    TestRunCreate,
)
from qa_core.execution.failure_snapshot import capture_failure_snapshot_event
from qa_core.execution.live_browser_plugin import write_live_browser_plugin
from qa_core.execution.models import SuiteExecutionResult, TestExecutionStatus
from qa_core.execution.pytest_runner import PytestRunner, validate_pytest_nodeids
from qa_core.execution.runner_backend import RunnerTriggerRequest
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.failure.snapshot_crypto import FailureSnapshotCipher
from qa_core.failure.traceback_frames import last_user_code_frame
from qa_core.onboarding.contract import venv_interpreter
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator
from sqlalchemy.exc import IntegrityError

from app.persistence.models import (
    BrowserSessionORM,
    ExternalArtifactReferenceORM,
    TestExecutionORM,
    TestRunORM,
    utc_now,
)
from app.ports.repository_scope import RepositoryScopeFactory
from app.repositories.runner_profile_repo import RunnerProfileRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.ai_runtime import build_ai_orchestrator
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.job_queue_service import JobQueueService
from app.services.workspace_service import WorkspaceService
from app.settings import get_config

DEFAULT_STALE_RUN_SECONDS = 7200.0

#: A distributed job is only recovered once its worker has been silent this long; a worker that
#: is merely slow still sends heartbeats.
DEFAULT_WORKER_OFFLINE_SECONDS = 600.0

logger = logging.getLogger("app.services.test_run")


@dataclass(frozen=True)
class LocalPytestExecutionOptions:
    """Project-specific options for a run that still uses the canonical local pytest runner."""

    interpreter: str | None = None
    environment: tuple[tuple[str, str], ...] = ()
    extra_pytest_args: tuple[str, ...] = ()
    timeout_sec: float = 900.0


class TestRunEventBus:
    """In-memory Pub/Sub event bus for live Server-Sent Events (SSE)."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._last_frames: OrderedDict[tuple[str, str], dict] = OrderedDict()

    def subscribe(self, run_id: str) -> asyncio.Queue:
        if run_id not in self._subscribers:
            self._subscribers[run_id] = []
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        for (frame_run_id, _), frame in self._last_frames.items():
            if frame_run_id == run_id:
                q.put_nowait(frame)
        self._subscribers[run_id].append(q)
        return q

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        if run_id in self._subscribers:
            self._subscribers[run_id] = [q for q in self._subscribers[run_id] if q != queue]
            if not self._subscribers[run_id]:
                del self._subscribers[run_id]

    async def publish(self, run_id: str, event: dict) -> None:
        if event.get("type") == "BROWSER_FRAME" and event.get("session_id"):
            key = (run_id, event["session_id"])
            if isinstance(event.get("frame"), str) and len(event["frame"]) <= 2 * 1024 * 1024:
                self._last_frames[key] = event
                self._last_frames.move_to_end(key)
                while len(self._last_frames) > 32:
                    self._last_frames.popitem(last=False)
        elif event.get("type") in {"RUN_FINISHED", "RUN_ERROR", "RUN_CANCELLED"}:
            for key in [key for key in self._last_frames if key[0] == run_id]:
                del self._last_frames[key]
        if run_id in self._subscribers:
            for q in self._subscribers[run_id]:
                if q.full():
                    # Frames and logs are transient. Preserve lifecycle events (especially the
                    # worker/session mapping and terminal run status) when a tab is slow.
                    queued: list[dict] = []
                    while not q.empty():
                        queued.append(q.get_nowait())
                    drop_index = next(
                        (i for i, item in enumerate(queued) if item.get("type") == "BROWSER_FRAME"),
                        None,
                    )
                    if drop_index is None:
                        drop_index = next(
                            (i for i, item in enumerate(queued) if item.get("type") == "LOG_STREAM"),
                            None,
                        )
                    if drop_index is None and event.get("type") in {"BROWSER_FRAME", "LOG_STREAM"}:
                        for item in queued:
                            q.put_nowait(item)
                        continue
                    if drop_index is None:
                        drop_index = 0
                    queued.pop(drop_index)
                    for item in queued:
                        q.put_nowait(item)
                q.put_nowait(event)


event_bus = TestRunEventBus()
_RUN_WORKER_TASKS: dict[str, asyncio.Task] = {}
_AUTO_FAILURE_REPAIR_TASKS: set[asyncio.Task] = set()
_AUTO_REPAIR_WORKSPACE_LOCKS: dict[str, asyncio.Lock] = {}
_RUN_JENKINS_BACKENDS: dict[str, JenkinsRunnerBackend] = {}


def _jenkins_config_for_profile(profile) -> JenkinsConfig:
    cfg = profile.config if profile else {}
    integration = get_config().integrations.jenkins
    global_config = integration if integration.enabled else None
    return JenkinsConfig(
        base_url=cfg.get("base_url") or (global_config.base_url if global_config else ""),
        job_name=cfg.get("job_name", "qa-automation-suite"),
        user=cfg.get("user") or (global_config.username if global_config else None),
        api_token=cfg.get("api_token") or (global_config.token.get_secret_value() if global_config else None),
        default_parameters=cfg.get("default_parameters", {}),
        parameter_mapping=cfg.get("parameter_mapping", {}),
    )


class TestRunService:
    def __init__(
        self,
        run_repo: TestRunRepository,
        workspace_repo: WorkspaceRepository,
        workspace_service: WorkspaceService,
        orchestrator: ProductionQAOrchestrator | None = None,
        runner_repo: RunnerProfileRepository | None = None,
        repository_scope: RepositoryScopeFactory | None = None,
        repositories=None,
    ) -> None:
        self.run_repo = run_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service
        self.orchestrator = orchestrator or build_ai_orchestrator()
        self.runner_repo = runner_repo or RunnerProfileRepository()
        self.repository_scope = repository_scope
        self.repositories = repositories
        self.pytest_runner = PytestRunner()

    def _repositories(self):
        if self.repositories is None:
            raise RuntimeError("TestRunService requires a repository scope for request transactions")
        return self.repositories

    def _open_repository_scope(self):
        if self.repository_scope is None:
            raise RuntimeError("TestRunService requires a repository scope factory for background operations")
        return self.repository_scope()

    def _to_execution_dto(self, orm: TestExecutionORM) -> TestExecution:
        return TestExecution(
            id=orm.id,
            run_id=orm.run_id,
            nodeid=orm.nodeid,
            status=RunStatus(orm.status),
            duration_ms=orm.duration_ms,
            error_message=SensitiveRedactor.redact_text(orm.error_message) if orm.error_message else None,
            stack_trace=SensitiveRedactor.redact_text(orm.stack_trace) if orm.stack_trace else None,
            failure_category=orm.failure_category,
            artifact_paths=orm.artifact_paths or [],
            started_at=orm.started_at,
            finished_at=orm.finished_at,
        )

    def _to_artifact_dto(self, orm: ExternalArtifactReferenceORM) -> ExternalArtifactReference:
        return ExternalArtifactReference(
            id=orm.id,
            run_id=orm.run_id,
            name=orm.name,
            type=orm.type,
            url=SensitiveRedactor.redact_url(orm.url),
            metadata_json=orm.metadata_json or {},
            created_at=orm.created_at,
        )

    def _to_run_dto(self, orm: TestRunORM) -> TestRun:
        executions = [self._to_execution_dto(e) for e in (orm.executions or [])]
        # Freshly inserted run rows do not have this selectin relationship loaded yet. Do not
        # trigger implicit async I/O while building the response DTO.
        loaded_browser_sessions = orm.__dict__.get("browser_sessions", [])
        browser_sessions = [self._to_browser_session_dto(item) for item in loaded_browser_sessions]
        artifacts = [self._to_artifact_dto(a) for a in (getattr(orm, "external_artifacts", []) or [])]
        return TestRun(
            id=orm.id,
            task_id=orm.task_id,
            parent_run_id=orm.parent_run_id,
            origin_failure_id=orm.origin_failure_id,
            project_id=orm.project_id,
            workspace_id=orm.workspace_id,
            status=RunStatus(orm.status),
            requested_by=orm.requested_by,
            runner_type=getattr(orm, "runner_type", "LOCAL"),
            runner_profile_id=getattr(orm, "runner_profile_id", None),
            external_job_id=getattr(orm, "external_job_id", None),
            external_build_url=(
                SensitiveRedactor.redact_url(orm.external_build_url)
                if getattr(orm, "external_build_url", None)
                else None
            ),
            queue_duration_ms=getattr(orm, "queue_duration_ms", 0.0),
            environment=orm.environment or {},
            browser=orm.browser,
            parallel_workers=getattr(orm, "parallel_workers", 1),
            markers=orm.markers or [],
            nodeids=orm.nodeids or [],
            total=orm.total,
            passed=orm.passed,
            failed=orm.failed,
            skipped=orm.skipped,
            cancelled=orm.cancelled,
            duration_ms=orm.duration_ms,
            log_output=(SensitiveRedactor.redact_text(orm.log_output) if getattr(orm, "log_output", None) else None),
            started_at=orm.started_at,
            finished_at=orm.finished_at,
            created_at=orm.created_at,
            executions=executions,
            browser_sessions=browser_sessions,
            external_artifacts=artifacts,
        )

    @staticmethod
    def _to_browser_session_dto(orm: BrowserSessionORM) -> TestBrowserSession:
        elapsed_end = orm.finished_at or utc_now()
        elapsed_ms = max(0.0, (elapsed_end - orm.started_at).total_seconds() * 1000)
        return TestBrowserSession(
            page_evidence=SensitiveRedactor.redact_value(json.loads(orm.page_evidence_json or "{}")),
            id=orm.id,
            run_id=orm.run_id,
            case_execution_id=orm.case_execution_id,
            worker_id=orm.worker_id,
            browser_session_id=orm.browser_session_id,
            page_id=orm.page_id,
            nodeid=orm.nodeid,
            case_name=orm.case_name,
            current_url=SensitiveRedactor.redact_url(orm.current_url),
            status=orm.status,
            elapsed_ms=elapsed_ms,
            started_at=orm.started_at,
            finished_at=orm.finished_at,
        )

    async def list_runs(self, project_id: str | None = None) -> list[TestRun]:
        orms = await self.run_repo.list_runs(project_id=project_id)
        return [self._to_run_dto(orm) for orm in orms]

    async def get_run(self, run_id: str) -> TestRun | None:
        orm = await self.run_repo.get_by_id(run_id)
        if not orm:
            return None
        return self._to_run_dto(orm)

    async def create_and_execute_run(
        self,
        data: TestRunCreate,
        *,
        task_id: str | None = None,
        execution_deadline: float | None = None,
        local_pytest_options: LocalPytestExecutionOptions | None = None,
    ) -> TestRun:
        if local_pytest_options and data.runner_type.upper() != RunnerType.LOCAL.value:
            raise ValueError("Project-specific pytest options require the local runner")
        if local_pytest_options and data.idempotency_key:
            raise ValueError("Project-specific pytest options cannot be used with run idempotency")
        from app.services.golden_demo_service import DEMO_ID, demo_lock

        if data.project_id == DEMO_ID:
            async with demo_lock:
                project = await self._repositories().projects.get_by_id_for_update(DEMO_ID)
                if not project:
                    raise ValueError("Demo is being reset or no longer exists")
                return await self._create_and_execute_run(
                    data,
                    task_id=task_id,
                    execution_deadline=execution_deadline,
                    local_pytest_options=local_pytest_options,
                )
        return await self._create_and_execute_run(
            data,
            task_id=task_id,
            execution_deadline=execution_deadline,
            local_pytest_options=local_pytest_options,
        )

    async def _create_and_execute_run(
        self,
        data: TestRunCreate,
        *,
        task_id: str | None = None,
        execution_deadline: float | None = None,
        local_pytest_options: LocalPytestExecutionOptions | None = None,
    ) -> TestRun:
        workspace = await self.workspace_repo.get_by_id(data.workspace_id)
        if workspace is None:
            workspace = await self.workspace_repo.get_by_project_id(data.workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")
        if workspace.project_id != data.project_id:
            raise ValueError("Workspace does not belong to the selected project")
        # Workspace row IDs and project IDs address the same project-owned filesystem directory.
        data = data.model_copy(
            update={
                "workspace_id": workspace.project_id,
                "nodeids": validate_pytest_nodeids(
                    self.workspace_service.get_workspace_dir(workspace.project_id), data.nodeids
                ),
            }
        )
        config = get_config()
        default_workers = min(config.pytest.workers, config.run.max_parallel_runs)
        data = data.model_copy(
            update={
                "parallel_workers": min(data.parallel_workers, config.run.max_parallel_runs)
                if "parallel_workers" in data.model_fields_set
                else default_workers
            }
        )
        if task_id:
            task = await self._repositories().tasks.get_by_id(task_id)
            if not task or task.project_id != data.project_id or task.owner_id != data.requested_by:
                raise ValueError("Task/Run identity mismatch")
        if data.parent_run_id:
            parent = await self.run_repo.get_by_id(data.parent_run_id)
            if not parent or parent.project_id != data.project_id or parent.workspace_id != data.workspace_id:
                raise ValueError("Retry parent must belong to the same project and workspace")
        if data.origin_failure_id:
            failure = await self.run_repo.get_failure_by_id(data.origin_failure_id)
            if not failure or failure.run_id != data.parent_run_id:
                raise ValueError("Origin failure must belong to the retry parent")
        if data.idempotency_key:
            existing = await self.run_repo.get_by_id(
                TestRunRepository.id_for_idempotency(data.project_id, data.idempotency_key)
            )
            if existing:
                self._ensure_same_run_request(existing, data, task_id)
                self._schedule_run_if_queued(
                    existing.id, existing.status, data, execution_deadline, local_pytest_options
                )
                return self._to_run_dto(existing)

        # 1. Create Run in DB
        try:
            orm = await self.run_repo.create_run(data, task_id=task_id)
        except IntegrityError:
            if not data.idempotency_key:
                raise
            await self._repositories().rollback()
            existing = await self.run_repo.get_by_id(
                TestRunRepository.id_for_idempotency(data.project_id, data.idempotency_key)
            )
            if not existing:
                raise
            self._ensure_same_run_request(existing, data, task_id)
            self._schedule_run_if_queued(existing.id, existing.status, data, execution_deadline, local_pytest_options)
            return self._to_run_dto(existing)
        run_id = orm.id
        is_jenkins = data.runner_type == RunnerType.JENKINS.value or (
            data.runner_profile_id and "jenkins" in str(data.runner_profile_id).lower()
        )
        if data.runner_type == RunnerType.WORKER.value and not is_jenkins:
            # The queue repository shares this transaction, so a Run cannot survive without its Job.
            await JobQueueService(
                repository_scope=self.repository_scope,
                job_repo=self._repositories().jobs,
            ).enqueue_job(
                run_id=run_id,
                project_id=data.project_id,
                workspace_id=data.workspace_id,
                nodeids=data.nodeids,
                browser=data.browser,
            )
        # Background execution opens its own session and must only see committed Runs.
        await self._repositories().commit()
        self._schedule_run_if_queued(run_id, orm.status, data, execution_deadline, local_pytest_options)

        return self._to_run_dto(orm)

    @staticmethod
    def _ensure_same_run_request(existing: TestRunORM, data: TestRunCreate, task_id: str | None) -> None:
        fields = (
            ("task_id", existing.task_id, task_id),
            ("project_id", existing.project_id, data.project_id),
            ("workspace_id", existing.workspace_id, data.workspace_id),
            ("parent_run_id", existing.parent_run_id, data.parent_run_id),
            ("origin_failure_id", existing.origin_failure_id, data.origin_failure_id),
            ("requested_by", existing.requested_by, data.requested_by),
            ("runner_type", existing.runner_type, data.runner_type),
            ("runner_profile_id", existing.runner_profile_id, data.runner_profile_id),
            ("nodeids", existing.nodeids or [], data.nodeids),
            ("markers", existing.markers or [], data.markers),
            ("environment", existing.environment or {}, data.environment),
            ("browser", existing.browser, data.browser),
            ("parallel_workers", existing.parallel_workers, data.parallel_workers),
        )
        if any(stored != requested for _, stored, requested in fields):
            raise ValueError("Idempotency key is already used for a different Run request")

    def _schedule_local_run(
        self,
        run_id: str,
        data: TestRunCreate,
        execution_deadline: float | None,
        local_pytest_options: LocalPytestExecutionOptions | None = None,
    ) -> None:
        worker = asyncio.create_task(
            self._run_worker_task(
                run_id,
                data,
                execution_deadline=execution_deadline,
                local_pytest_options=local_pytest_options,
            ),
            name=f"test-run-{run_id}",
        )
        _RUN_WORKER_TASKS[run_id] = worker

        def clear_worker(done: asyncio.Task, *, scheduled_run_id: str = run_id) -> None:
            if _RUN_WORKER_TASKS.get(scheduled_run_id) is done:
                _RUN_WORKER_TASKS.pop(scheduled_run_id, None)

        worker.add_done_callback(clear_worker)

    def _schedule_run_if_queued(
        self,
        run_id: str,
        status: str,
        data: TestRunCreate,
        execution_deadline: float | None,
        local_pytest_options: LocalPytestExecutionOptions | None = None,
    ) -> None:
        if status != RunStatus.QUEUED.value:
            return
        is_jenkins = data.runner_type == RunnerType.JENKINS.value or (
            data.runner_profile_id and "jenkins" in str(data.runner_profile_id).lower()
        )
        if data.runner_type == RunnerType.WORKER.value and not is_jenkins:
            return
        worker = _RUN_WORKER_TASKS.get(run_id)
        if worker is None or worker.done():
            if is_jenkins:
                worker = asyncio.create_task(self._run_jenkins_worker_task(run_id, data), name=f"test-run-{run_id}")
                _RUN_WORKER_TASKS[run_id] = worker

                def clear_worker(done: asyncio.Task, *, scheduled_run_id: str = run_id) -> None:
                    if _RUN_WORKER_TASKS.get(scheduled_run_id) is done:
                        _RUN_WORKER_TASKS.pop(scheduled_run_id, None)

                worker.add_done_callback(clear_worker)
            else:
                self._schedule_local_run(run_id, data, execution_deadline, local_pytest_options)

    async def _run_worker_task(
        self,
        run_id: str,
        data: TestRunCreate,
        *,
        execution_deadline: float | None = None,
        local_pytest_options: LocalPytestExecutionOptions | None = None,
    ) -> None:
        async with self._open_repository_scope() as repositories:
            run_repo = repositories.test_runs
            task_repo = repositories.tasks
            existing = await run_repo.get_by_id(run_id)
            if existing is None or existing.status in ("CANCELLED", "PASSED", "FAILED", "ERROR"):
                return
            ws_dir = self.workspace_service.get_workspace_dir(data.workspace_id)
            execution_timeout = min(get_config().run.default_timeout_seconds, get_config().pytest.timeout_seconds)
            if local_pytest_options:
                execution_timeout = min(execution_timeout, local_pytest_options.timeout_sec)
            if existing.task_id:
                task = await task_repo.get_by_id(existing.task_id)
                if task:
                    task_timeout = (
                        max(0.01, execution_deadline - time.monotonic())
                        if execution_deadline is not None
                        else float(task.max_duration_seconds)
                    )
                    execution_timeout = (
                        min(task_timeout, local_pytest_options.timeout_sec) if local_pytest_options else task_timeout
                    )
            start_time = utc_now()

            started = await run_repo.transition_run_status(
                run_id,
                [RunStatus.QUEUED],
                RunStatus.RUNNING,
                started_at=start_time,
            )
            await repositories.commit()
            if not started:
                return

            await event_bus.publish(
                run_id,
                {
                    "type": "RUN_STARTED",
                    "run_id": run_id,
                    "runner": "LOCAL",
                    "status": "RUNNING",
                    "total": len(data.nodeids),
                },
            )

            try:
                live_log = ""
                artifact_dir = get_config().app.artifact_storage_dir.resolve() / run_id
                artifact_dir.mkdir(parents=True, exist_ok=True)

                async def on_log(chunk: str) -> None:
                    nonlocal live_log
                    safe_chunk = SensitiveRedactor.redact_text(chunk)
                    live_log = (live_log + safe_chunk)[-20000:]
                    active = await run_repo.update_run_log_if_active(run_id, live_log)
                    await repositories.commit()
                    if not active:
                        return
                    await event_bus.publish(run_id, {"type": "LOG_STREAM", "run_id": run_id, "log": safe_chunk})

                # Execute PytestRunner. An imported project must run in its own virtualenv: using
                # the API's interpreter makes its tests fail on their own dependencies.
                browser_proxy_env = {}
                browser_config = get_config().browser
                if browser_config.proxy_url.get_secret_value():
                    browser_proxy_env["BROWSER_PROXY_URL"] = browser_config.proxy_url.get_secret_value()
                if browser_config.proxy_bypass:
                    browser_proxy_env["BROWSER_PROXY_BYPASS"] = browser_config.proxy_bypass

                failure_snapshot_key = FailureSnapshotCipher.generate_ephemeral_key()
                failure_snapshots = []

                async def on_browser_event(event: dict) -> None:
                    await self._record_browser_event(run_id, event)
                    capture = capture_failure_snapshot_event(
                        event,
                        ephemeral_key=failure_snapshot_key,
                        master_key=get_config().app.secret_key.get_secret_value(),
                    )
                    if capture is not None:
                        failure_snapshots.append(capture)

                project_environment = dict(local_pytest_options.environment) if local_pytest_options else {}

                # Capture is controlled by AppConfig and passed as child-process context only.
                with tempfile.TemporaryDirectory(prefix=".qa-live-", dir=artifact_dir) as live_dir_value:
                    live_dir = Path(live_dir_value)
                    live_browser_log = live_dir / "browser-live"
                    live_browser_enabled = get_config().features.live_browser
                    live_plugin = write_live_browser_plugin(live_dir) if live_browser_enabled else None
                    plugin_pythonpath = os.pathsep.join(
                        value
                        for value in ((str(live_dir) if live_browser_enabled else ""), os.environ.get("PYTHONPATH", ""))
                        if value
                    )
                    failure_policy = get_config().failure
                    evidence_policy = get_config().evidence
                    evidence_environment = {
                        "QA_CAPTURE_SCREENSHOT": str(int(failure_policy.capture_screenshot)),
                        "QA_CAPTURE_DOM": str(int(failure_policy.capture_dom)),
                        "QA_CAPTURE_CONSOLE": str(int(failure_policy.capture_console)),
                        "QA_CAPTURE_NETWORK": str(int(failure_policy.capture_network)),
                        "QA_EVIDENCE_MAX_CONSOLE_ENTRIES": str(evidence_policy.max_console_entries),
                        "QA_EVIDENCE_MAX_NETWORK_ENTRIES": str(evidence_policy.max_network_entries),
                        "QA_EVIDENCE_MAX_DOM_CHARS": str(evidence_policy.max_dom_chars),
                    }
                    suite_result = await self.pytest_runner.run_suite(
                        workspace_dir=ws_dir,
                        nodeids=data.nodeids,
                        markers=data.markers,
                        environment={
                            **data.environment,
                            **project_environment,
                            "QA_BROWSER": data.browser,
                            **browser_proxy_env,
                            **evidence_environment,
                            "QA_ARTIFACT_DIR": str(artifact_dir),
                            "QA_FAILURE_SNAPSHOT_ENCRYPTION_KEY": failure_snapshot_key,
                            "QA_FAILURE_SNAPSHOT_TTL_SECONDS": str(failure_policy.storage_state_ttl_seconds),
                            **({"QA_PLATFORM_LIVE_BROWSER_LOG": str(live_browser_log)} if live_browser_enabled else {}),
                            "PYTHONPATH": plugin_pythonpath,
                        },
                        interpreter=(
                            local_pytest_options.interpreter
                            if local_pytest_options and local_pytest_options.interpreter
                            else self._project_interpreter(ws_dir)
                        ),
                        on_log=on_log,
                        browser_event_path=live_browser_log if live_browser_enabled else None,
                        on_browser_event=on_browser_event if live_browser_enabled else None,
                        parallel_workers=data.parallel_workers,
                        extra_pytest_args=[
                            *get_config().pytest.default_args,
                            *(["-p", live_plugin] if live_plugin else []),
                            *(local_pytest_options.extra_pytest_args if local_pytest_options else ()),
                        ],
                        timeout_sec=execution_timeout,
                    )
                suite_result.artifact_paths = [str(path) for path in artifact_dir.rglob("*") if path.is_file()]
                suite_result.failure_snapshots = failure_snapshots

                await self.persist_suite_result(
                    run_id, suite_result, workspace_id=data.workspace_id, workspace_dir=ws_dir
                )

            except Exception as e:
                safe_error = SensitiveRedactor.redact_text(str(e))
                await run_repo.transition_run_status(
                    run_id,
                    [RunStatus.QUEUED, RunStatus.RUNNING],
                    RunStatus.ERROR,
                    finished_at=utc_now(),
                    log_output=safe_error,
                )
                await repositories.commit()
                await event_bus.publish(
                    run_id,
                    {
                        "type": "RUN_ERROR",
                        "run_id": run_id,
                        "error": safe_error,
                    },
                )

    async def persist_suite_result(
        self,
        run_id: str,
        suite_result: SuiteExecutionResult,
        *,
        workspace_id: str | None = None,
        workspace_dir: Path | None = None,
    ) -> None:
        async with self._open_repository_scope() as repositories:
            run_repo = repositories.test_runs
            browser_repo = repositories.browser_sessions
            existing = await run_repo.get_by_id(run_id)
            if existing is None or existing.status in ("CANCELLED", "PASSED", "FAILED", "ERROR"):
                return
            run_workspace_id = existing.workspace_id
            origin_failure_id = existing.origin_failure_id
            # Artifact uploads happen outside the database lock; start the guarded write transaction
            # only after external I/O so a cancellation can win cleanly while uploads are pending.
            await repositories.rollback()
            artifact_urls: list[str] = []
            artifact_records: list[tuple[str, str, str, str, str]] = []
            artifact_root = (get_config().app.artifact_storage_dir.resolve() / run_id).resolve()
            storage = ArtifactStorageService()
            for artifact_name in suite_result.artifact_paths:
                artifact = Path(artifact_name).resolve()
                if not artifact.is_relative_to(artifact_root) or not artifact.is_file():
                    logger.warning("Ignoring artifact outside run directory: %s", artifact_name)
                    continue
                if artifact.stat().st_size > 20 * 1024 * 1024:
                    logger.warning("Ignoring artifact larger than 20 MiB: %s", artifact_name)
                    continue
                content_type = mimetypes.guess_type(artifact.name)[0] or "application/octet-stream"
                uploaded = await storage.save_artifact(artifact.name, artifact.read_bytes(), content_type)
                kind = (
                    "SCREENSHOT"
                    if content_type.startswith("image/")
                    else ("TRACE" if artifact.suffix.lower() == ".zip" else "REPORT")
                )
                artifact_records.append((artifact.name, kind, uploaded.storage_url, uploaded.artifact_id, content_type))
                artifact_urls.append(uploaded.storage_url)
            if artifact_records and not await run_repo.reserve_active_run_for_result(run_id):
                return
            for name, kind, url, artifact_id, content_type in artifact_records:
                metadata = {"artifact_id": artifact_id, "content_type": content_type}
                snapshot = re.fullmatch(r"browser-([0-9a-f]{32})-last\.jpg", name)
                if snapshot and content_type == "image/jpeg":
                    browser_session = await browser_repo.attach_last_frame_artifact(
                        snapshot.group(1), run_id, artifact_id
                    )
                    if browser_session:
                        metadata["browser_session_id"] = browser_session.browser_session_id
                        metadata["frame_kind"] = "last"
                await run_repo.add_external_artifact(
                    run_id,
                    name,
                    kind,
                    url,
                    metadata_json=metadata,
                )
            await repositories.commit()
            passed_count = 0
            failed_count = 0
            skipped_count = 0
            failure_ids: list[str] = []
            executions_by_nodeid: dict[str, TestExecutionORM] = {}

            for res in suite_result.results:
                safe_error_message = SensitiveRedactor.redact_text(res.error_message or "")
                safe_stack_trace = SensitiveRedactor.redact_text(res.stack_trace or "")
                if not await run_repo.reserve_active_run_for_result(run_id):
                    return
                status = (
                    RunStatus.PASSED
                    if res.status == TestExecutionStatus.PASSED
                    else (RunStatus.SKIPPED if res.status == TestExecutionStatus.SKIPPED else RunStatus.FAILED)
                )

                if status == RunStatus.PASSED:
                    passed_count += 1
                elif status == RunStatus.FAILED:
                    failed_count += 1
                else:
                    skipped_count += 1

                failure_cat = None
                if status == RunStatus.FAILED:
                    diag = self.orchestrator.diagnose_failure(
                        error_message=safe_error_message or "Test failed",
                        stack_trace=safe_stack_trace,
                        test_nodeid=res.nodeid,
                    )
                    failure_cat = diag.classification.value

                exec_orm = await run_repo.add_execution(
                    run_id=run_id,
                    nodeid=res.nodeid,
                    status=status,
                    duration_ms=res.duration_ms,
                    error_message=safe_error_message or None,
                    stack_trace=safe_stack_trace or None,
                    failure_category=failure_cat,
                    artifact_paths=artifact_urls if len(suite_result.results) == 1 else None,
                )
                executions_by_nodeid[res.nodeid] = exec_orm
                await browser_repo.attach_execution(run_id, res.nodeid, exec_orm.id)

                # If failed, create FailureRecord
                if status == RunStatus.FAILED and get_config().failure.auto_create:
                    diag = self.orchestrator.diagnose_failure(
                        error_message=safe_error_message or "Test failed",
                        stack_trace=safe_stack_trace,
                        test_nodeid=res.nodeid,
                    )
                    proposal = None
                    # A traceback is failure evidence, not proof of a replacement locator.
                    # Proposals are generated separately from observed browser/DOM candidates.

                    failure_record = await run_repo.create_failure_record(
                        run_id=run_id,
                        execution_id=exec_orm.id,
                        test_nodeid=res.nodeid,
                        test_name=res.nodeid.split("::")[-1],
                        classification=diag.classification.value,
                        exception_type=diag.exception_type,
                        error_message=diag.error_message,
                        stack_trace=diag.stack_trace,
                        failing_locator=diag.failing_locator,
                        suggested_action=diag.suggested_action,
                        repair_proposal=proposal,
                    )
                    failure_ids.append(failure_record.id)
                    if workspace_id and workspace_dir:
                        frame = last_user_code_frame(safe_stack_trace, workspace_dir)
                        if frame:
                            file_path, line_number = frame
                            await repositories.breakpoints.upsert_failure(workspace_id, file_path, line_number, run_id)

                await repositories.commit()

                await event_bus.publish(
                    run_id,
                    {
                        "type": "TEST_FINISHED",
                        "run_id": run_id,
                        "nodeid": res.nodeid,
                        "status": status.value,
                        "duration_ms": res.duration_ms,
                    },
                )

            for capture in suite_result.failure_snapshots:
                execution = executions_by_nodeid.get(capture.nodeid)
                if execution is None or execution.status != RunStatus.FAILED.value:
                    continue
                await browser_repo.save_failure_snapshot(
                    run_id=run_id,
                    execution_id=execution.id,
                    capture=capture,
                    storage_state_ttl_seconds=get_config().failure.storage_state_ttl_seconds,
                )
            await repositories.commit()

            finish_time = utc_now()
            final_status = self._verdict(suite_result.exit_code, len(suite_result.results), failed_count)

            # A worker can be cancelled or terminated before the pytest plugin emits its normal
            # session.finished event. Close any such records before publishing the terminal run.
            await browser_repo.close_running_sessions(run_id, executions_by_nodeid, finish_time)

            transitioned = await run_repo.transition_run_status(
                run_id,
                [RunStatus.QUEUED, RunStatus.RUNNING],
                final_status,
                passed=passed_count,
                failed=failed_count,
                skipped=skipped_count,
                total=suite_result.total,
                duration_ms=suite_result.duration_ms,
                finished_at=finish_time,
                log_output=SensitiveRedactor.redact_text("\n".join(suite_result.raw_logs))[-20000:] or None,
            )
            await repositories.commit()

            if not transitioned:
                return

            await event_bus.publish(
                run_id,
                {
                    "type": "RUN_FINISHED",
                    "run_id": run_id,
                    "status": final_status.value,
                    "passed": passed_count,
                    "failed": failed_count,
                    "duration_ms": suite_result.duration_ms,
                },
            )
            config = get_config()
            mode = config.repair.mode if config.repair.enabled and config.features.auto_repair else "OFF"
            if (
                final_status == RunStatus.FAILED
                and failure_ids
                and mode != "OFF"
                and config.repair.auto_start_on_failure
                and origin_failure_id is None
            ):
                self._schedule_auto_failure_repair(
                    failure_ids,
                    workspace_id=run_workspace_id,
                    mode=mode,
                )

    @staticmethod
    def _schedule_auto_failure_repair(failure_ids: list[str], *, workspace_id: str | None, mode: str) -> None:
        if not workspace_id or not failure_ids:
            logger.warning("Automatic failure repair was not scheduled: workspace or failure is missing")
            return
        task = asyncio.create_task(
            TestRunService._run_auto_failure_repairs(failure_ids, workspace_id=workspace_id, mode=mode),
            name=f"auto-failure-repair-{failure_ids[0]}",
        )
        _AUTO_FAILURE_REPAIR_TASKS.add(task)

        def finished(done: asyncio.Task) -> None:
            _AUTO_FAILURE_REPAIR_TASKS.discard(done)
            if not done.cancelled() and done.exception() is not None:
                logger.error("Automatic failure repair task ended with an error: %s", type(done.exception()).__name__)

        task.add_done_callback(finished)

    @staticmethod
    async def _run_auto_failure_repairs(failure_ids: list[str], *, workspace_id: str, mode: str) -> None:
        from app.container import get_failure_service, get_failure_workflow_service
        from app.persistence.database import async_session_factory

        lock = _AUTO_REPAIR_WORKSPACE_LOCKS.setdefault(workspace_id, asyncio.Lock())
        async with lock:
            for failure_id in failure_ids:
                try:
                    async with async_session_factory() as session:
                        failure_service = get_failure_service(session)
                        workflow = get_failure_workflow_service(failure_service, session)
                        workflow.auto_repair_mode = mode
                        async for _ in workflow.stream(
                            failure_id,
                            response_language="zh-CN",
                            auto_triggered=True,
                        ):
                            pass
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logger.exception(
                        "Automatic repair could not start for failure %s (%s)",
                        failure_id,
                        type(error).__name__,
                    )

    async def _run_jenkins_worker_task(self, run_id: str, data: TestRunCreate) -> None:
        async with self._open_repository_scope() as repositories:
            run_repo = repositories.test_runs
            runner_repo = repositories.runner_profiles
            start_time = utc_now()
            started = await run_repo.transition_run_status(
                run_id,
                [RunStatus.QUEUED],
                RunStatus.RUNNING,
                started_at=start_time,
            )
            await repositories.commit()
            if not started:
                return

            # Resolve runner profile config
            runner_profile = None
            if data.runner_profile_id:
                runner_profile = await runner_repo.get_by_id(data.runner_profile_id)

            jenkins_cfg = _jenkins_config_for_profile(runner_profile)
            backend = JenkinsRunnerBackend(config=jenkins_cfg)
            _RUN_JENKINS_BACKENDS[run_id] = backend

            try:
                await event_bus.publish(
                    run_id,
                    {
                        "type": "RUN_STARTED",
                        "run_id": run_id,
                        "runner": "JENKINS",
                        "status": "QUEUED",
                        "job_name": jenkins_cfg.job_name,
                    },
                )

                # Trigger Jenkins Job
                trigger_req = RunnerTriggerRequest(
                    run_id=run_id,
                    project_id=data.project_id,
                    nodeids=data.nodeids,
                    markers=data.markers,
                    environment=data.environment,
                    parameters=data.parameters,
                )
                trig_res = await backend.trigger(trigger_req)
                external_job_id = trig_res.external_job_id

                attached = await run_repo.transition_run_status(
                    run_id,
                    [RunStatus.RUNNING],
                    RunStatus.RUNNING,
                    external_job_id=external_job_id,
                )
                await repositories.commit()
                if not attached:
                    await backend.stop(run_id, external_job_id=external_job_id)
                    return

                build_url = None
                resolved_id = external_job_id or "1"
                poll_interval = max(0.1, float(getattr(jenkins_cfg, "poll_interval_seconds", 1.0)))
                while True:
                    if await run_repo.current_status(run_id) != RunStatus.RUNNING.value:
                        return

                    final_status_res = await backend.get_status(run_id, external_job_id=resolved_id)
                    if final_status_res.external_job_id and final_status_res.external_job_id != resolved_id:
                        resolved_id = final_status_res.external_job_id
                        build_url = final_status_res.external_build_url
                        attached = await run_repo.transition_run_status(
                            run_id,
                            [RunStatus.RUNNING],
                            RunStatus.RUNNING,
                            external_job_id=resolved_id,
                            external_build_url=SensitiveRedactor.redact_url(build_url) if build_url else None,
                        )
                        await repositories.commit()
                        if not attached:
                            await backend.stop(run_id, external_job_id=resolved_id)
                            return
                    elif final_status_res.external_build_url:
                        build_url = final_status_res.external_build_url

                    if not resolved_id.startswith("queue:"):
                        async for log_chunk in backend.stream_logs(run_id, external_job_id=resolved_id):
                            await event_bus.publish(
                                run_id,
                                {
                                    "type": "LOG_STREAM",
                                    "run_id": run_id,
                                    "runner": "JENKINS",
                                    "log": SensitiveRedactor.redact_text(log_chunk),
                                },
                            )

                    if final_status_res.status != RunStatus.RUNNING:
                        break
                    await asyncio.sleep(poll_interval)

                finish_time = utc_now()

                # Record external artifacts (Allure, HTML Report)
                for art in final_status_res.artifacts:
                    await run_repo.add_external_artifact(
                        run_id=run_id,
                        name=art["name"],
                        type=art["type"],
                        url=SensitiveRedactor.redact_url(art["url"]),
                    )

                transitioned = await run_repo.transition_run_status(
                    run_id,
                    [RunStatus.RUNNING],
                    final_status_res.status,
                    duration_ms=final_status_res.duration_ms,
                    finished_at=finish_time,
                    external_job_id=resolved_id,
                    external_build_url=SensitiveRedactor.redact_url(final_status_res.external_build_url or build_url)
                    if final_status_res.external_build_url or build_url
                    else None,
                )
                await repositories.commit()

                if not transitioned:
                    return

                await event_bus.publish(
                    run_id,
                    {
                        "type": "RUN_FINISHED",
                        "run_id": run_id,
                        "runner": "JENKINS",
                        "status": final_status_res.status.value,
                        "build_url": SensitiveRedactor.redact_url(final_status_res.external_build_url or build_url)
                        if final_status_res.external_build_url or build_url
                        else None,
                        "duration_ms": final_status_res.duration_ms,
                    },
                )

            except Exception as e:
                safe_error = SensitiveRedactor.redact_text(str(e))
                logger.error("Jenkins run execution encountered error: %s", safe_error)
                transitioned = await run_repo.transition_run_status(
                    run_id,
                    [RunStatus.RUNNING],
                    RunStatus.ERROR,
                    finished_at=utc_now(),
                    log_output=safe_error,
                )
                await repositories.commit()
                if not transitioned:
                    return
                await event_bus.publish(
                    run_id,
                    {
                        "type": "RUN_ERROR",
                        "run_id": run_id,
                        "runner": "JENKINS",
                        "error": safe_error,
                    },
                )
            finally:
                _RUN_JENKINS_BACKENDS.pop(run_id, None)

    async def recover_stale_runs(self, stale_after_seconds: float = DEFAULT_STALE_RUN_SECONDS) -> list[str]:
        """Close runs that can never finish.

        A process crash mid-run leaves a run in RUNNING forever, which the UI shows as in-progress
        and which makes every pass-rate and coverage figure wrong. Unfinished runs older than the
        threshold are closed as CANCELLED rather than FAILED: the platform does not know their
        outcome, and must never invent a verdict.

        This assumes a single API instance. Local runs are recovered from their own age; a
        distributed job is recovered only when the owning worker stopped heartbeating, because a
        slow worker is not a dead one.
        """
        now = utc_now()
        cutoff = now - timedelta(seconds=stale_after_seconds)
        # Only local child processes are owned by this API. Distributed jobs are recovered from
        # their worker's heartbeat, and Jenkins runs stay with the remote controller.
        stale = await self.run_repo.list_unfinished_runs(older_than=cutoff, runner_types=["LOCAL"])
        stale_run_ids = [orm.id for orm in stale]
        worker_offline_before = now - timedelta(seconds=max(stale_after_seconds, DEFAULT_WORKER_OFFLINE_SECONDS))
        abandoned = await self._repositories().jobs.list_abandoned_run_ids(
            older_than=cutoff, worker_offline_before=worker_offline_before
        )
        recovered: list[str] = []
        for run_id in dict.fromkeys([*stale_run_ids, *abandoned]):
            changed = await self.run_repo.cancel_active_run(run_id, finished_at=utc_now())
            if not changed:
                continue
            recovered.append(run_id)
            await self._repositories().jobs.cancel_active_jobs_for_run(run_id)

        if recovered:
            await self._repositories().commit()
        for run_id in recovered:
            await event_bus.publish(
                run_id,
                {
                    "type": "RUN_CANCELLED",
                    "run_id": run_id,
                    "reason": "recovered as stale: the run never reached a terminal state",
                },
            )
        return recovered

    def _project_interpreter(self, workspace_dir: Path) -> str | None:
        """The project's provisioned interpreter, when the workspace has one."""
        candidate = venv_interpreter(Path(workspace_dir) / ".qa-platform-runtime")
        if candidate.exists():
            return str(candidate)
        return None

    def _verdict(self, exit_code: int | None, result_count: int, failed_count: int) -> RunStatus:
        """Decide the run verdict from the runner's exit code, never from an absence of failures.

        pytest exit codes: 0 all passed, 1 failures, 2 interrupted, 3 internal error, 4 usage error,
        5 no tests collected. A non-zero exit with no parsed result means the suite never ran
        (a broken conftest, a missing dependency): reporting that as PASSED is the one thing the
        platform must never do.
        """
        if exit_code is None:
            return RunStatus.ERROR
        if result_count == 0:
            return RunStatus.ERROR
        if exit_code == 0:
            return RunStatus.PASSED if failed_count == 0 else RunStatus.FAILED
        return RunStatus.FAILED

    async def cancel_run(self, run_id: str) -> TestRun | None:
        orm = await self.run_repo.get_by_id(run_id)
        if not orm:
            return None
        if orm.status not in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
            return self._to_run_dto(orm)

        changed = await self.run_repo.cancel_active_run(run_id, finished_at=utc_now())
        await self._repositories().commit()
        if not changed:
            return await self.get_run(run_id)

        await self._repositories().jobs.cancel_active_jobs_for_run(run_id)
        if orm.runner_type == "JENKINS" and orm.external_job_id:
            try:
                backend = _RUN_JENKINS_BACKENDS.get(run_id)
                if backend is None and orm.runner_profile_id:
                    profile = await self.runner_repo.get_by_id(orm.runner_profile_id)
                    if profile:
                        backend = JenkinsRunnerBackend(config=_jenkins_config_for_profile(profile))
                elif backend is None:
                    backend = JenkinsRunnerBackend()
                stopped = await backend.stop(run_id, external_job_id=orm.external_job_id) if backend else False
                if not stopped:
                    logger.warning("Jenkins cancellation was not confirmed for run %s", run_id)
            except Exception as error:
                logger.error(
                    "Failed to stop Jenkins run %s after marking it cancelled: %s",
                    run_id,
                    SensitiveRedactor.redact_text(str(error)),
                )

        worker = _RUN_WORKER_TASKS.get(run_id)
        if worker and worker is not asyncio.current_task():
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        await event_bus.publish(
            run_id,
            {
                "type": "RUN_CANCELLED",
                "run_id": run_id,
            },
        )
        return await self.get_run(run_id)

    async def event_generator(self, run_id: str) -> AsyncGenerator[dict, None]:
        # Poll persisted state so reconnects and events from another process are visible.
        # In-memory Pub/Sub alone loses events during refresh and cannot cross worker processes.
        queue = event_bus.subscribe(run_id)
        sent_log = ""
        seen_executions: set[str] = set()
        seen_browser_sessions: dict[str, dict] = {}
        last_status: RunStatus | None = None
        try:
            yield {"type": "CONNECTED", "run_id": run_id}
            while True:
                while not queue.empty():
                    event = queue.get_nowait()
                    if event.get("type") in {"BROWSER_SESSION", "BROWSER_FRAME"}:
                        yield event

                async with self._open_repository_scope() as repositories:
                    orm = await repositories.test_runs.get_by_id(run_id)
                    if orm is None:
                        return
                    run = self._to_run_dto(orm)

                # Replay durable session metadata after refresh/reconnect, including events
                # written by another process. Elapsed time alone must not trigger a replay.
                for browser_session in run.browser_sessions:
                    snapshot = browser_session.model_dump(mode="json", exclude={"elapsed_ms"})
                    session_id = browser_session.browser_session_id
                    if seen_browser_sessions.get(session_id) != snapshot:
                        seen_browser_sessions[session_id] = snapshot
                        yield {
                            "type": "BROWSER_SESSION",
                            "run_id": run_id,
                            "session": browser_session.model_dump(mode="json"),
                        }

                if run.status == RunStatus.RUNNING and last_status != RunStatus.RUNNING:
                    yield {"type": "RUN_STARTED", "run_id": run_id, "status": "RUNNING", "total": run.total}
                log = run.log_output or ""
                if log != sent_log:
                    sent_log = log
                    # The durable log is a bounded ring, so its length stops growing.
                    # Replacing that observation also makes reconnect replay idempotent.
                    yield {"type": "LOG_STREAM", "run_id": run_id, "log": log, "replace": True}
                for execution in run.executions:
                    if execution.id not in seen_executions:
                        seen_executions.add(execution.id)
                        yield {
                            "type": "TEST_FINISHED",
                            "run_id": run_id,
                            "nodeid": execution.nodeid,
                            "status": execution.status.value,
                            "duration_ms": execution.duration_ms,
                        }
                if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                    event_type = (
                        "RUN_CANCELLED"
                        if run.status == RunStatus.CANCELLED
                        else ("RUN_ERROR" if run.status == RunStatus.ERROR else "RUN_FINISHED")
                    )
                    yield {
                        "type": event_type,
                        "run_id": run_id,
                        "status": run.status.value,
                        "passed": run.passed,
                        "failed": run.failed,
                        "duration_ms": run.duration_ms,
                    }
                    return
                last_status = run.status
                await asyncio.sleep(0.2)
        finally:
            event_bus.unsubscribe(run_id, queue)

    async def _record_browser_event(self, run_id: str, event: dict) -> None:
        """Persist session lifecycle metadata and publish ephemeral real page frames to SSE."""
        event_type = event.get("type")
        session_id = event.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return
        worker_id = str(event.get("worker_id") or "main")[:100]
        nodeid = str(event.get("nodeid") or "")[:500]
        case_name = str(event.get("case_name") or nodeid.split("::")[-1])[:250]
        page_id = str(event.get("page_id") or session_id)[:36]
        url = SensitiveRedactor.redact_url(str(event.get("url") or ""))[:2048]
        status = str(event.get("status") or "running")[:30]
        occurred_at = None
        try:
            value = datetime.fromisoformat(str(event.get("timestamp") or "").replace("Z", "+00:00"))
            if value.tzinfo is not None:
                occurred_at = value.astimezone(timezone.utc)
        except ValueError:
            pass

        if event_type in {"session.started", "navigation", "session.finished"}:
            async with self._open_repository_scope() as repositories:
                page_evidence = event.get("page_evidence")
                safe_evidence = (
                    SensitiveRedactor.redact_value(page_evidence) if isinstance(page_evidence, dict) else None
                )
                if safe_evidence is not None:
                    safe_evidence.pop("failure_snapshot", None)
                row = await repositories.browser_sessions.record_lifecycle_event(
                    run_id=run_id,
                    session_id=session_id,
                    event_type=event_type,
                    page_id=page_id,
                    worker_id=worker_id,
                    nodeid=nodeid,
                    case_name=case_name,
                    url=url,
                    status=status,
                    occurred_at=occurred_at,
                    page_evidence=safe_evidence,
                )
                if row is not None:
                    await repositories.commit()
                    session_dto = self._to_browser_session_dto(row).model_dump(mode="json")
                    await event_bus.publish(
                        run_id,
                        {"type": "BROWSER_SESSION", "run_id": run_id, "session": session_dto},
                    )
        elif event_type in {"console", "network", "step"}:
            entry = SensitiveRedactor.redact_value(event.get("entry") or {})
            if event_type == "network" and entry.get("url"):
                entry["url"] = SensitiveRedactor.redact_url(entry["url"])
            async with self._open_repository_scope() as repositories:
                key = {"console": "console_logs", "network": "network_logs", "step": "recent_steps"}[event_type]
                if not await repositories.browser_sessions.append_evidence(
                    session_id, key, entry, run_id=run_id, nodeid=nodeid
                ):
                    return
                await repositories.commit()
            if event_type == "step" and entry.get("locator"):
                from app.services.locator_history_service import LocatorHistoryService

                await LocatorHistoryService(self.repository_scope).record(
                    url, entry["locator"], entry.get("status") == "PASSED"
                )
            await event_bus.publish(
                run_id,
                {
                    "type": "BROWSER_TELEMETRY",
                    "run_id": run_id,
                    "session_id": session_id,
                    "channel": event_type,
                    "entry": entry,
                    "timestamp": event.get("timestamp"),
                },
            )
        elif event_type == "frame" and isinstance(event.get("frame"), str):
            async with self._open_repository_scope() as repositories:
                owner = await repositories.browser_sessions.get_by_id(session_id)
                if owner is None or owner.run_id != run_id or (nodeid and owner.nodeid != nodeid):
                    return
            await event_bus.publish(
                run_id,
                {
                    "type": "BROWSER_FRAME",
                    "run_id": run_id,
                    "session_id": session_id,
                    "page_id": page_id,
                    "worker_id": worker_id,
                    "nodeid": nodeid,
                    "case_name": case_name,
                    "url": url,
                    "status": status,
                    "mime_type": event.get("mime_type") or "image/jpeg",
                    "frame": event["frame"],
                },
            )
