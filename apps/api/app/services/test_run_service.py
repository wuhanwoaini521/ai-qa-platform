from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import AsyncGenerator

from integrations.jenkins_runner import JenkinsConfig, JenkinsRunnerBackend
from project_model.models import (
    ExternalArtifactReference,
    RunnerType,
    RunStatus,
    TestExecution,
    TestRun,
    TestRunCreate,
)
from qa_core.execution.models import TestExecutionStatus
from qa_core.execution.pytest_runner import PytestRunner
from qa_core.execution.runner_backend import RunnerTriggerRequest
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.persistence.models import (
    ExternalArtifactReferenceORM,
    TestExecutionORM,
    TestRunORM,
    utc_now,
)
from app.repositories.runner_profile_repo import RunnerProfileRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.workspace_service import WorkspaceService

DEFAULT_STALE_RUN_SECONDS = 7200.0

logger = logging.getLogger("app.services.test_run")


class TestRunEventBus:
    """In-memory Pub/Sub event bus for live Server-Sent Events (SSE)."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue:
        if run_id not in self._subscribers:
            self._subscribers[run_id] = []
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[run_id].append(q)
        return q

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        if run_id in self._subscribers:
            self._subscribers[run_id] = [q for q in self._subscribers[run_id] if q != queue]
            if not self._subscribers[run_id]:
                del self._subscribers[run_id]

    async def publish(self, run_id: str, event: dict) -> None:
        if run_id in self._subscribers:
            for q in self._subscribers[run_id]:
                await q.put(event)


event_bus = TestRunEventBus()


class TestRunService:
    def __init__(
        self,
        run_repo: TestRunRepository,
        workspace_repo: WorkspaceRepository,
        workspace_service: WorkspaceService,
        orchestrator: ProductionQAOrchestrator | None = None,
        runner_repo: RunnerProfileRepository | None = None,
    ) -> None:
        self.run_repo = run_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service
        self.orchestrator = orchestrator or ProductionQAOrchestrator()
        self.runner_repo = runner_repo or RunnerProfileRepository()
        self.pytest_runner = PytestRunner()

    def _to_execution_dto(self, orm: TestExecutionORM) -> TestExecution:
        return TestExecution(
            id=orm.id,
            run_id=orm.run_id,
            nodeid=orm.nodeid,
            status=RunStatus(orm.status),
            duration_ms=orm.duration_ms,
            error_message=orm.error_message,
            stack_trace=orm.stack_trace,
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
            url=orm.url,
            metadata_json=orm.metadata_json or {},
            created_at=orm.created_at,
        )

    def _to_run_dto(self, orm: TestRunORM) -> TestRun:
        executions = [self._to_execution_dto(e) for e in (orm.executions or [])]
        artifacts = [self._to_artifact_dto(a) for a in (getattr(orm, "external_artifacts", []) or [])]
        return TestRun(
            id=orm.id,
            project_id=orm.project_id,
            workspace_id=orm.workspace_id,
            status=RunStatus(orm.status),
            requested_by=orm.requested_by,
            runner_type=getattr(orm, "runner_type", "LOCAL"),
            runner_profile_id=getattr(orm, "runner_profile_id", None),
            external_job_id=getattr(orm, "external_job_id", None),
            external_build_url=getattr(orm, "external_build_url", None),
            queue_duration_ms=getattr(orm, "queue_duration_ms", 0.0),
            environment=orm.environment or {},
            browser=orm.browser,
            markers=orm.markers or [],
            nodeids=orm.nodeids or [],
            total=orm.total,
            passed=orm.passed,
            failed=orm.failed,
            skipped=orm.skipped,
            cancelled=orm.cancelled,
            duration_ms=orm.duration_ms,
            log_output=getattr(orm, "log_output", None),
            started_at=orm.started_at,
            finished_at=orm.finished_at,
            created_at=orm.created_at,
            executions=executions,
            external_artifacts=artifacts,
        )

    async def list_runs(self, project_id: str | None = None) -> list[TestRun]:
        orms = await self.run_repo.list_runs(project_id=project_id)
        return [self._to_run_dto(orm) for orm in orms]

    async def get_run(self, run_id: str) -> TestRun | None:
        orm = await self.run_repo.get_by_id(run_id)
        if not orm:
            return None
        return self._to_run_dto(orm)

    async def create_and_execute_run(self, data: TestRunCreate) -> TestRun:
        # 1. Create Run in DB
        orm = await self.run_repo.create_run(data)
        run_id = orm.id

        # 2. Trigger asynchronous execution in background task depending on runner
        is_jenkins = data.runner_type == RunnerType.JENKINS.value or (
            data.runner_profile_id and "jenkins" in str(data.runner_profile_id).lower()
        )

        if is_jenkins:
            asyncio.create_task(self._run_jenkins_worker_task(run_id, data))
        else:
            asyncio.create_task(self._run_worker_task(run_id, data))

        return self._to_run_dto(orm)

    async def _run_worker_task(self, run_id: str, data: TestRunCreate) -> None:
        from app.persistence.database import get_session

        async with get_session() as session:
            run_repo = TestRunRepository(session)
            ws_dir = self.workspace_service.get_workspace_dir(data.workspace_id)
            start_time = utc_now()

            await run_repo.update_run_status(run_id, status=RunStatus.RUNNING, started_at=start_time)
            await session.commit()

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
                # Execute PytestRunner
                suite_result = await self.pytest_runner.run_suite(
                    workspace_dir=ws_dir,
                    nodeids=data.nodeids,
                    markers=data.markers,
                    environment=data.environment,
                )

                passed_count = 0
                failed_count = 0
                skipped_count = 0

                for res in suite_result.results:
                    status = (
                        RunStatus.PASSED
                        if res.status == TestExecutionStatus.PASSED
                        else (RunStatus.FAILED if res.status == TestExecutionStatus.FAILED else RunStatus.SKIPPED)
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
                            error_message=res.error_message or "Test failed",
                            stack_trace=res.stack_trace or "",
                            test_nodeid=res.nodeid,
                        )
                        failure_cat = diag.classification.value

                    exec_orm = await run_repo.add_execution(
                        run_id=run_id,
                        nodeid=res.nodeid,
                        status=status,
                        duration_ms=res.duration_ms,
                        error_message=res.error_message,
                        stack_trace=res.stack_trace,
                        failure_category=failure_cat,
                    )

                    # If failed, create FailureRecord
                    if status == RunStatus.FAILED:
                        diag = self.orchestrator.diagnose_failure(
                            error_message=res.error_message or "Test failed",
                            stack_trace=res.stack_trace or "",
                            test_nodeid=res.nodeid,
                        )
                        proposal = None
                        if diag.failing_locator:
                            p = self.orchestrator.propose_locator_repair(
                                failing_locator=diag.failing_locator,
                                error_message=res.error_message or "",
                                file_path=res.nodeid.split("::")[0],
                            )
                            proposal = p.model_dump()

                        await run_repo.create_failure_record(
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

                    await session.commit()

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

                finish_time = utc_now()
                final_status = RunStatus.PASSED if failed_count == 0 else RunStatus.FAILED

                await run_repo.update_run_status(
                    run_id=run_id,
                    status=final_status,
                    passed=passed_count,
                    failed=failed_count,
                    skipped=skipped_count,
                    duration_ms=suite_result.duration_ms,
                    finished_at=finish_time,
                    log_output="\n".join(suite_result.raw_logs)[-20000:] or None,
                )
                await session.commit()

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

            except Exception as e:
                await run_repo.update_run_status(
                    run_id=run_id,
                    status=RunStatus.ERROR,
                    finished_at=utc_now(),
                )
                await session.commit()
                await event_bus.publish(
                    run_id,
                    {
                        "type": "RUN_ERROR",
                        "run_id": run_id,
                        "error": str(e),
                    },
                )

    async def _run_jenkins_worker_task(self, run_id: str, data: TestRunCreate) -> None:
        from app.persistence.database import get_session

        async with get_session() as session:
            run_repo = TestRunRepository(session)
            runner_repo = RunnerProfileRepository(lambda: session)
            start_time = utc_now()
            await run_repo.update_run_status(run_id, status=RunStatus.RUNNING, started_at=start_time)
            await session.commit()

            # Resolve runner profile config
            runner_profile = None
            if data.runner_profile_id:
                runner_profile = await runner_repo.get_by_id(data.runner_profile_id)

            cfg = runner_profile.config if runner_profile else {}
            jenkins_cfg = JenkinsConfig(
                base_url=cfg.get("base_url", "http://localhost:8080"),
                job_name=cfg.get("job_name", "qa-automation-suite"),
                user=cfg.get("user"),
                api_token=cfg.get("api_token"),
                default_parameters=cfg.get("default_parameters", {}),
                parameter_mapping=cfg.get("parameter_mapping", {}),
            )

            backend = JenkinsRunnerBackend(config=jenkins_cfg)

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

                await run_repo.update_run_status(
                    run_id=run_id,
                    status=RunStatus.RUNNING,
                    external_job_id=external_job_id,
                )
                await session.commit()

                # Resolve build number
                build_num = None
                build_url = None
                if external_job_id and external_job_id.startswith("queue:"):
                    qid = external_job_id.replace("queue:", "")
                    build_num, build_url = await backend.resolve_build_number(qid, max_wait=20.0)

                resolved_id = str(build_num) if build_num else (external_job_id or "1")

                # Stream logs to SSE
                async for log_chunk in backend.stream_logs(run_id, external_job_id=resolved_id):
                    await event_bus.publish(
                        run_id,
                        {
                            "type": "LOG_STREAM",
                            "run_id": run_id,
                            "runner": "JENKINS",
                            "log": log_chunk,
                        },
                    )

                # Poll status
                final_status_res = await backend.get_status(run_id, external_job_id=resolved_id)
                finish_time = utc_now()

                # Record external artifacts (Allure, HTML Report)
                for art in final_status_res.artifacts:
                    await run_repo.add_external_artifact(
                        run_id=run_id,
                        name=art["name"],
                        type=art["type"],
                        url=art["url"],
                    )

                await run_repo.update_run_status(
                    run_id=run_id,
                    status=final_status_res.status,
                    duration_ms=final_status_res.duration_ms,
                    finished_at=finish_time,
                    external_job_id=resolved_id,
                    external_build_url=final_status_res.external_build_url or build_url,
                )
                await session.commit()

                await event_bus.publish(
                    run_id,
                    {
                        "type": "RUN_FINISHED",
                        "run_id": run_id,
                        "runner": "JENKINS",
                        "status": final_status_res.status.value,
                        "build_url": final_status_res.external_build_url or build_url,
                        "duration_ms": final_status_res.duration_ms,
                    },
                )

            except Exception as e:
                logger.error("Jenkins run execution encountered error: %s", e)
                await run_repo.update_run_status(
                    run_id=run_id,
                    status=RunStatus.ERROR,
                    finished_at=utc_now(),
                )
                await session.commit()
                await event_bus.publish(
                    run_id,
                    {
                        "type": "RUN_ERROR",
                        "run_id": run_id,
                        "runner": "JENKINS",
                        "error": str(e),
                    },
                )

    async def recover_stale_runs(self, stale_after_seconds: float = DEFAULT_STALE_RUN_SECONDS) -> list[str]:
        """Close runs that can never finish.

        A process crash mid-run leaves a run in RUNNING forever, which the UI shows as in-progress
        and which makes every pass-rate and coverage figure wrong. Unfinished runs older than the
        threshold are closed as CANCELLED rather than FAILED: the platform does not know their
        outcome, and must never invent a verdict.

        This assumes a single API instance. Distributed execution belongs to the job queue, where
        workers heartbeat, so an abandoned job is detected there instead.
        """
        cutoff = utc_now() - timedelta(seconds=stale_after_seconds)
        # Jenkins runs are left alone: the platform cannot stop the external build here, so marking
        # the row CANCELLED would desync it from the CI job that is still running.
        stale = await self.run_repo.list_unfinished_runs(older_than=cutoff, exclude_runner_types=["JENKINS"])
        recovered: list[str] = []
        for orm in stale:
            await self.run_repo.update_run_status(run_id=orm.id, status=RunStatus.CANCELLED, finished_at=utc_now())
            await event_bus.publish(
                orm.id,
                {
                    "type": "RUN_CANCELLED",
                    "run_id": orm.id,
                    "reason": "recovered as stale: the run never reached a terminal state",
                },
            )
            recovered.append(orm.id)
        return recovered

    async def cancel_run(self, run_id: str) -> TestRun | None:
        orm = await self.run_repo.get_by_id(run_id)
        if not orm:
            return None

        if orm.runner_type == "JENKINS" and orm.external_job_id:
            backend = JenkinsRunnerBackend()
            await backend.stop(run_id, external_job_id=orm.external_job_id)

        await self.run_repo.update_run_status(
            run_id=run_id,
            status=RunStatus.CANCELLED,
            finished_at=utc_now(),
        )
        await event_bus.publish(
            run_id,
            {
                "type": "RUN_CANCELLED",
                "run_id": run_id,
            },
        )
        return await self.get_run(run_id)

    async def event_generator(self, run_id: str) -> AsyncGenerator[str, None]:
        queue = event_bus.subscribe(run_id)
        try:
            yield f"data: {json.dumps({'type': 'CONNECTED', 'run_id': run_id})}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("RUN_FINISHED", "RUN_ERROR", "RUN_CANCELLED"):
                    break
        finally:
            event_bus.unsubscribe(run_id, queue)
