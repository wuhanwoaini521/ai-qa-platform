from __future__ import annotations

import uuid
from typing import Any

from project_model.models import RunStatus, TestRunCreate
from sqlalchemy import desc, select
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

    async def list_runs(self, project_id: str | None = None, limit: int = 50) -> list[TestRunORM]:
        query = (
            select(TestRunORM)
            .options(selectinload(TestRunORM.executions), selectinload(TestRunORM.external_artifacts))
            .order_by(desc(TestRunORM.created_at))
        )
        if project_id:
            query = query.where(TestRunORM.project_id == project_id)
        result = await self.session.execute(query.limit(limit))
        return list(result.scalars().all())

    async def get_by_id(self, run_id: str) -> TestRunORM | None:
        result = await self.session.execute(
            select(TestRunORM)
            .options(selectinload(TestRunORM.executions), selectinload(TestRunORM.external_artifacts))
            .where(TestRunORM.id == run_id)
        )
        return result.scalar_one_or_none()

    async def create_run(self, data: TestRunCreate) -> TestRunORM:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = TestRunORM(
            id=run_id,
            project_id=data.project_id,
            workspace_id=data.workspace_id,
            status=RunStatus.QUEUED.value,
            requested_by=data.requested_by,
            runner_type=data.runner_type,
            runner_profile_id=data.runner_profile_id,
            environment=data.environment,
            browser=data.browser,
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
        duration_ms: float | None = None,
        started_at=None,
        finished_at=None,
        external_job_id: str | None = None,
        external_build_url: str | None = None,
        queue_duration_ms: float | None = None,
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
        await self.session.flush()
        return orm

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
            started_at=now,
            finished_at=now,
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

    async def list_failures(self, limit: int = 50) -> list[FailureRecordORM]:
        result = await self.session.execute(
            select(FailureRecordORM).order_by(desc(FailureRecordORM.created_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def get_failure_by_id(self, failure_id: str) -> FailureRecordORM | None:
        result = await self.session.execute(select(FailureRecordORM).where(FailureRecordORM.id == failure_id))
        return result.scalar_one_or_none()

    async def list_executions(self, run_id: str) -> list[TestExecutionORM]:
        result = await self.session.execute(
            select(TestExecutionORM).where(TestExecutionORM.run_id == run_id).order_by(TestExecutionORM.started_at)
        )
        return list(result.scalars().all())
