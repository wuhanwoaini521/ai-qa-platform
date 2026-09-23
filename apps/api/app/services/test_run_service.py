from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from project_model.models import (
    RunStatus,
    TestExecution,
    TestRun,
    TestRunCreate,
)
from qa_core.execution.models import TestExecutionStatus
from qa_core.execution.pytest_runner import PytestRunner
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.persistence.models import TestExecutionORM, TestRunORM, utc_now
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.workspace_service import WorkspaceService


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
    ) -> None:
        self.run_repo = run_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service
        self.orchestrator = orchestrator or ProductionQAOrchestrator()
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

    def _to_run_dto(self, orm: TestRunORM) -> TestRun:
        executions = [self._to_execution_dto(e) for e in (orm.executions or [])]
        return TestRun(
            id=orm.id,
            project_id=orm.project_id,
            workspace_id=orm.workspace_id,
            status=RunStatus(orm.status),
            requested_by=orm.requested_by,
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
            started_at=orm.started_at,
            finished_at=orm.finished_at,
            created_at=orm.created_at,
            executions=executions,
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

        # 2. Trigger asynchronous execution in background task
        asyncio.create_task(self._run_worker_task(run_id, data))

        return self._to_run_dto(orm)

    async def _run_worker_task(self, run_id: str, data: TestRunCreate) -> None:
        ws_dir = self.workspace_service.get_workspace_dir(data.workspace_id)
        start_time = utc_now()

        await self.run_repo.update_run_status(run_id, status=RunStatus.RUNNING, started_at=start_time)
        await event_bus.publish(
            run_id,
            {
                "type": "RUN_STARTED",
                "run_id": run_id,
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

                exec_orm = await self.run_repo.add_execution(
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

                    await self.run_repo.create_failure_record(
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

            await self.run_repo.update_run_status(
                run_id=run_id,
                status=final_status,
                passed=passed_count,
                failed=failed_count,
                skipped=skipped_count,
                duration_ms=suite_result.duration_ms,
                finished_at=finish_time,
            )

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
            await self.run_repo.update_run_status(
                run_id=run_id,
                status=RunStatus.ERROR,
                finished_at=utc_now(),
            )
            await event_bus.publish(
                run_id,
                {
                    "type": "RUN_ERROR",
                    "run_id": run_id,
                    "error": str(e),
                },
            )

    async def event_generator(self, run_id: str) -> AsyncGenerator[str, None]:
        queue = event_bus.subscribe(run_id)
        try:
            # Yield initial keep-alive
            yield f"data: {json.dumps({'type': 'CONNECTED', 'run_id': run_id})}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("RUN_FINISHED", "RUN_ERROR"):
                    break
        finally:
            event_bus.unsubscribe(run_id, queue)
