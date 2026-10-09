from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Any

from project_model.models import RunStatus, TestRunCreate
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.models import (
    ExternalArtifactReferenceORM,
    FailureRecordORM,
    TestExecutionORM,
    TestRunORM,
    utc_now,
)


class TestRunRepository:
    __test__ = False

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def id_for_idempotency(project_id: str, idempotency_key: str) -> str:
        digest = hashlib.sha256(f"{project_id}\0{idempotency_key}".encode()).hexdigest()[:32]
        return f"run_{digest}"

    async def list_runs(self, project_id: str | None = None, limit: int = 50) -> list[TestRunORM]:
        query = (
            select(TestRunORM)
            .options(
                selectinload(TestRunORM.executions),
                selectinload(TestRunORM.external_artifacts),
                selectinload(TestRunORM.browser_sessions),
            )
            .order_by(desc(TestRunORM.created_at))
        )
        if project_id:
            query = query.where(TestRunORM.project_id == project_id)
        result = await self.session.execute(query.limit(limit))
        return list(result.scalars().all())

    async def get_by_id(self, run_id: str) -> TestRunORM | None:
        result = await self.session.execute(
            select(TestRunORM)
            .options(
                selectinload(TestRunORM.executions),
                selectinload(TestRunORM.external_artifacts),
                selectinload(TestRunORM.browser_sessions),
            )
            .where(TestRunORM.id == run_id)
        )
        return result.scalar_one_or_none()

    async def current_status(self, run_id: str) -> str | None:
        result = await self.session.execute(select(TestRunORM.status).where(TestRunORM.id == run_id))
        return result.scalar_one_or_none()

    async def create_run(self, data: TestRunCreate, *, task_id: str | None = None) -> TestRunORM:
        if data.idempotency_key:
            run_id = self.id_for_idempotency(data.project_id, data.idempotency_key)
        else:
            run_id = f"run_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = TestRunORM(
            id=run_id,
            task_id=task_id,
            parent_run_id=data.parent_run_id,
            origin_failure_id=data.origin_failure_id,
            project_id=data.project_id,
            workspace_id=data.workspace_id,
            status=RunStatus.QUEUED.value,
            requested_by=data.requested_by,
            runner_type=data.runner_type,
            runner_profile_id=data.runner_profile_id,
            environment=data.environment,
            browser=data.browser,
            parallel_workers=data.parallel_workers,
            markers=data.markers,
            nodeids=data.nodeids,
            total=len(data.nodeids),
            passed=0,
            failed=0,
            skipped=0,
            cancelled=0,
            duration_ms=0.0,
            created_at=now,
        )
        orm.executions = []
        orm.external_artifacts = []
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        passed: int | None = None,
        failed: int | None = None,
        skipped: int | None = None,
        total: int | None = None,
        duration_ms: float | None = None,
        started_at=None,
        finished_at=None,
        external_job_id: str | None = None,
        external_build_url: str | None = None,
        queue_duration_ms: float | None = None,
        log_output: str | None = None,
    ) -> TestRunORM | None:
        orm = await self.get_by_id(run_id)
        if not orm:
            return None
        orm.status = status.value
        if passed is not None:
            orm.passed = passed
        if failed is not None:
            orm.failed = failed
        if skipped is not None:
            orm.skipped = skipped
        if total is not None:
            orm.total = total
        if duration_ms is not None:
            orm.duration_ms = duration_ms
        if started_at is not None:
            orm.started_at = started_at
        if finished_at is not None:
            orm.finished_at = finished_at
        if external_job_id is not None:
            orm.external_job_id = external_job_id
        if external_build_url is not None:
            orm.external_build_url = external_build_url
        if queue_duration_ms is not None:
            orm.queue_duration_ms = queue_duration_ms
        if log_output is not None:
            orm.log_output = log_output
        await self.session.flush()
        return orm

    async def transition_run_status(
        self,
        run_id: str,
        expected_statuses: list[RunStatus],
        status: RunStatus,
        *,
        passed: int | None = None,
        failed: int | None = None,
        skipped: int | None = None,
        total: int | None = None,
        duration_ms: float | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        external_job_id: str | None = None,
        external_build_url: str | None = None,
        log_output: str | None = None,
    ) -> bool:
        """Atomically change a run only while it is in an expected state."""
        values: dict[str, Any] = {"status": status.value}
        for key, value in (
            ("passed", passed),
            ("failed", failed),
            ("skipped", skipped),
            ("total", total),
            ("duration_ms", duration_ms),
            ("started_at", started_at),
            ("finished_at", finished_at),
            ("external_job_id", external_job_id),
            ("external_build_url", external_build_url),
            ("log_output", log_output),
        ):
            if value is not None:
                values[key] = value
        result = await self.session.execute(
            update(TestRunORM)
            .where(
                TestRunORM.id == run_id,
                TestRunORM.status.in_([item.value for item in expected_statuses]),
            )
            .values(**values)
            .execution_options(synchronize_session="fetch")
        )
        await self.session.flush()
        return result.rowcount == 1

    async def update_run_log_if_active(self, run_id: str, log_output: str) -> bool:
        """Update live logs without allowing a late chunk to revive a terminal run."""
        result = await self.session.execute(
            update(TestRunORM)
            .where(
                TestRunORM.id == run_id,
                TestRunORM.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
            )
            .values(log_output=log_output)
        )
        await self.session.flush()
        return result.rowcount == 1

    async def reserve_active_run_for_result(self, run_id: str) -> bool:
        """Serialize one result write against cancellation by taking the run row's write lock."""
        result = await self.session.execute(
            update(TestRunORM)
            .where(
                TestRunORM.id == run_id,
                TestRunORM.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
            )
            .values(status=TestRunORM.status)
        )
        await self.session.flush()
        return result.rowcount == 1

    async def cancel_active_run(self, run_id: str, finished_at: datetime) -> bool:
        """Lock the run before counting committed executions and transitioning it to cancelled."""
        locked = await self.session.execute(
            select(TestRunORM.id)
            .where(
                TestRunORM.id == run_id,
                TestRunORM.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
            )
            .with_for_update()
        )
        if locked.scalar_one_or_none() is None:
            return False

        async def count(status: RunStatus) -> int:
            result = await self.session.execute(
                select(func.count(TestExecutionORM.id)).where(
                    TestExecutionORM.run_id == run_id,
                    TestExecutionORM.status == status.value,
                )
            )
            return result.scalar_one()

        passed = await count(RunStatus.PASSED)
        failed = await count(RunStatus.FAILED)
        skipped = await count(RunStatus.SKIPPED)
        result = await self.session.execute(
            update(TestRunORM)
            .where(
                TestRunORM.id == run_id,
                TestRunORM.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
            )
            .values(
                status=RunStatus.CANCELLED.value,
                finished_at=finished_at,
                passed=passed,
                failed=failed,
                skipped=skipped,
            )
        )
        await self.session.flush()
        return result.rowcount == 1

    async def add_execution(
        self,
        run_id: str,
        nodeid: str,
        status: RunStatus,
        duration_ms: float = 0.0,
        retry_count: int = 0,
        error_message: str | None = None,
        stack_trace: str | None = None,
        failure_category: str | None = None,
        artifact_paths: list[str] | None = None,
    ) -> TestExecutionORM:
        exec_id = f"exec_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = TestExecutionORM(
            id=exec_id,
            run_id=run_id,
            nodeid=nodeid,
            status=status.value,
            duration_ms=duration_ms,
            retry_count=retry_count,
            error_message=error_message,
            stack_trace=stack_trace,
            failure_category=failure_category,
            artifact_paths=artifact_paths or [],
            started_at=now - timedelta(milliseconds=max(0, duration_ms)),
            finished_at=now,
            timestamp_source="derived",
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def add_external_artifact(
        self,
        run_id: str,
        name: str,
        type: str,
        url: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> ExternalArtifactReferenceORM:
        art_id = f"art_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = ExternalArtifactReferenceORM(
            id=art_id,
            run_id=run_id,
            name=name,
            type=type,
            url=url,
            metadata_json=metadata_json or {},
            created_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def create_failure_record(
        self,
        run_id: str,
        execution_id: str,
        test_nodeid: str,
        test_name: str,
        classification: str,
        exception_type: str,
        error_message: str,
        stack_trace: str,
        failing_locator: str | None = None,
        screenshot_path: str | None = None,
        trace_path: str | None = None,
        dom_snapshot_path: str | None = None,
        console_logs: list[str] | None = None,
        suggested_action: str | None = None,
        repair_proposal: dict | None = None,
    ) -> FailureRecordORM:
        fail_id = f"fail_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = FailureRecordORM(
            id=fail_id,
            run_id=run_id,
            execution_id=execution_id,
            test_nodeid=test_nodeid,
            test_name=test_name,
            classification=classification,
            exception_type=exception_type,
            error_message=error_message,
            stack_trace=stack_trace,
            failing_locator=failing_locator,
            screenshot_path=screenshot_path,
            trace_path=trace_path,
            dom_snapshot_path=dom_snapshot_path,
            console_logs=console_logs or [],
            suggested_action=suggested_action,
            repair_proposal=repair_proposal,
            created_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def list_unfinished_runs(
        self, older_than: datetime, runner_types: list[str] | None = None
    ) -> list[TestRunORM]:
        """Runs that were started but never reached a terminal state before `older_than`.

        Staleness is measured from `started_at` when the run began, falling back to `created_at` for
        runs that never started: a long queue wait is not evidence that a run was abandoned.
        """
        query = select(TestRunORM).where(
            TestRunORM.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
            func.coalesce(TestRunORM.started_at, TestRunORM.created_at) < older_than,
        )
        if runner_types:
            query = query.where(TestRunORM.runner_type.in_(runner_types))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_failures(self, limit: int = 50, project_id: str | None = None) -> list[FailureRecordORM]:
        query = select(FailureRecordORM).order_by(desc(FailureRecordORM.created_at))
        if project_id:
            # Failures carry a run id, so the project filter has to go through the run.
            query = query.join(TestRunORM, FailureRecordORM.run_id == TestRunORM.id).where(
                TestRunORM.project_id == project_id
            )
        result = await self.session.execute(query.limit(limit))
        return list(result.scalars().all())

    async def get_failure_by_id(self, failure_id: str) -> FailureRecordORM | None:
        result = await self.session.execute(select(FailureRecordORM).where(FailureRecordORM.id == failure_id))
        return result.scalar_one_or_none()

    async def get_task(self, task_id: str):
        from app.persistence.models import TaskORM

        return await self.session.get(TaskORM, task_id)

    async def list_failures_by_run(self, run_id: str) -> list[FailureRecordORM]:
        result = await self.session.execute(select(FailureRecordORM).where(FailureRecordORM.run_id == run_id))
        return list(result.scalars().all())

    async def list_executions(self, run_id: str) -> list[TestExecutionORM]:
        result = await self.session.execute(
            select(TestExecutionORM)
            .where(TestExecutionORM.run_id == run_id)
            .order_by(TestExecutionORM.started_at.asc().nulls_first(), TestExecutionORM.id.asc())
        )
        return list(result.scalars().all())
