from __future__ import annotations

from project_model.models import ExecutionJob, ExecutionJobCreate, JobStatus, RunStatus

from app.persistence.models import utc_now
from app.ports.repository_scope import RepositoryScopeFactory
from app.repositories.job_repo import JobRepository
from app.services.workspace_service import WorkspaceService


class JobNotFoundError(LookupError):
    pass


class JobAssignmentConflict(RuntimeError):
    pass


class JobQueueService:
    def __init__(self, repository_scope: RepositoryScopeFactory, job_repo: JobRepository | None = None) -> None:
        self.repository_scope = repository_scope
        self.job_repo = job_repo or JobRepository()

    async def enqueue_job(
        self,
        run_id: str,
        project_id: str,
        workspace_id: str,
        nodeids: list[str],
        runner_type: str = "WORKER",
        browser: str = "chromium",
        priority: int = 10,
    ) -> ExecutionJob:
        create_req = ExecutionJobCreate(
            run_id=run_id,
            project_id=project_id,
            workspace_id=workspace_id,
            nodeids=nodeids,
            runner_type=runner_type,
            browser=browser,
            priority=priority,
            status=JobStatus.QUEUED,
        )
        return await self.job_repo.create_job(create_req)

    async def dispatch_next_job(
        self,
        worker_id: str,
        browser: str = "chromium",
        browsers: list[str] | None = None,
        project_ids: list[str] | None = None,
    ) -> ExecutionJob | None:
        return await self.job_repo.claim_next_job(
            worker_id=worker_id, browser=browser, browsers=browsers, project_ids=project_ids
        )

    async def get_job(self, job_id: str) -> ExecutionJob:
        job = await self.job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    async def get_assigned_job(self, job_id: str, worker_id: str) -> ExecutionJob:
        job = await self.get_job(job_id)
        if job.assigned_worker_id != worker_id or job.status not in (JobStatus.ASSIGNED, JobStatus.RUNNING):
            raise JobAssignmentConflict(job_id)
        return job

    async def append_worker_log(self, job_id: str, worker_id: str, safe_log: str) -> None:
        job = await self.get_assigned_job(job_id, worker_id)
        async with self.repository_scope() as repositories:
            run_repo = repositories.test_runs
            run = await run_repo.get_by_id(job.run_id)
            if run is None or run.status in {"CANCELLED", "PASSED", "FAILED", "ERROR"}:
                raise JobAssignmentConflict(job_id)
            changed = await run_repo.transition_run_status(
                job.run_id,
                [RunStatus.QUEUED, RunStatus.RUNNING],
                RunStatus.RUNNING,
                started_at=utc_now() if run.started_at is None else None,
                log_output=((run.log_output or "") + safe_log)[-20000:],
            )
            if not changed:
                raise JobAssignmentConflict(job_id)
            await repositories.commit()
        await self.job_repo.update_job_status(job_id, JobStatus.RUNNING)

    async def mark_run_error(self, run_id: str, safe_error: str) -> None:
        async with self.repository_scope() as repositories:
            run_repo = repositories.test_runs
            run = await run_repo.get_by_id(run_id)
            if run is not None and run.status in {"QUEUED", "RUNNING"}:
                await run_repo.transition_run_status(
                    run_id,
                    [RunStatus.QUEUED, RunStatus.RUNNING],
                    RunStatus.ERROR,
                    finished_at=utc_now(),
                    log_output=((run.log_output or "") + "\nWorker error: " + safe_error)[-20000:],
                )
                await repositories.commit()

    async def complete_job(self, job_id: str, duration_ms: float = 0.0) -> ExecutionJob | None:
        return await self.job_repo.update_job_status(job_id=job_id, status=JobStatus.COMPLETED, duration_ms=duration_ms)

    async def submit_worker_result(self, job_id: str, worker_id: str, result) -> ExecutionJob:
        job = await self.get_assigned_job(job_id, worker_id)
        from app.services.test_run_service import TestRunService

        async with self.repository_scope() as repositories:
            service = TestRunService(
                repositories.test_runs,
                repositories.workspaces,
                WorkspaceService(),
                repository_scope=self.repository_scope,
                repositories=repositories,
            )
            await service.persist_suite_result(job.run_id, result)
        completed = await self.complete_job(job_id, duration_ms=result.duration_ms)
        if completed is None:
            raise JobNotFoundError(job_id)
        return completed

    async def fail_job(self, job_id: str, error_message: str, worker_id: str | None = None) -> ExecutionJob | None:
        job = await self.get_job(job_id)
        if job.status in (JobStatus.ASSIGNED, JobStatus.RUNNING):
            if not worker_id or job.assigned_worker_id != worker_id:
                raise JobAssignmentConflict(job_id)
        elif worker_id is not None and job.assigned_worker_id != worker_id:
            raise JobAssignmentConflict(job_id)
        return await self.job_repo.update_job_status(
            job_id=job_id, status=JobStatus.FAILED, error_message=error_message
        )

    async def cancel_job(self, job_id: str) -> ExecutionJob | None:
        job = await self.job_repo.get_by_id(job_id)
        if job is None:
            return None
        cancelled = await self.job_repo.update_job_status(job_id=job_id, status=JobStatus.CANCELLED)
        # Cancelling only the job left the run RUNNING in the UI and in every pass-rate figure,
        # so the run (and its worker-side execution) is cancelled through the same service the
        # runs API uses.
        if job.status in (JobStatus.QUEUED, JobStatus.ASSIGNED, JobStatus.RUNNING):
            from app.services.test_run_service import TestRunService

            async with self.repository_scope() as repositories:
                service = TestRunService(
                    repositories.test_runs,
                    repositories.workspaces,
                    WorkspaceService(),
                    repository_scope=self.repository_scope,
                    repositories=repositories,
                )
                await service.cancel_run(job.run_id)
        return cancelled

    async def list_jobs(
        self,
        run_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExecutionJob]:
        return await self.job_repo.list_jobs(run_id=run_id, project_id=project_id, status=status, limit=limit)
