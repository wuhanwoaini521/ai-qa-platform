from __future__ import annotations

from project_model.models import ExecutionJob, ExecutionJobCreate, JobStatus

from app.repositories.job_repo import JobRepository


class JobQueueService:
    def __init__(self, job_repo: JobRepository | None = None) -> None:
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

    async def dispatch_next_job(self, worker_id: str, browser: str = "chromium") -> ExecutionJob | None:
        return await self.job_repo.claim_next_job(worker_id=worker_id, browser=browser)

    async def complete_job(self, job_id: str, duration_ms: float = 0.0) -> ExecutionJob | None:
        return await self.job_repo.update_job_status(job_id=job_id, status=JobStatus.COMPLETED, duration_ms=duration_ms)

    async def fail_job(self, job_id: str, error_message: str) -> ExecutionJob | None:
        return await self.job_repo.update_job_status(
            job_id=job_id, status=JobStatus.FAILED, error_message=error_message
        )

    async def cancel_job(self, job_id: str) -> ExecutionJob | None:
        return await self.job_repo.update_job_status(job_id=job_id, status=JobStatus.CANCELLED)

    async def list_jobs(
        self,
        run_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExecutionJob]:
        return await self.job_repo.list_jobs(run_id=run_id, project_id=project_id, status=status, limit=limit)
