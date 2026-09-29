from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from project_model.models import ClaimJobRequest, CompleteJobRequest, ExecutionJob, FailJobRequest
from project_model.models import JobStatus, RunStatus
from qa_core.execution.models import SuiteExecutionResult
from pydantic import BaseModel

from app.persistence.database import get_session
from app.persistence.models import utc_now
from app.repositories.job_repo import JobRepository
from app.repositories.test_run_repo import TestRunRepository
from app.api.runs import get_run_service

from app.services.job_queue_service import JobQueueService

router = APIRouter(prefix="/jobs", tags=["jobs"])
job_queue_service = JobQueueService()


class WorkerLogPayload(BaseModel):
    worker_id: str
    log: str


class WorkerResultPayload(BaseModel):
    worker_id: str
    result: SuiteExecutionResult


async def _assigned_job(job_id: str, worker_id: str) -> ExecutionJob:
    job = await JobRepository().get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.assigned_worker_id != worker_id or job.status not in (JobStatus.ASSIGNED, JobStatus.RUNNING):
        raise HTTPException(status_code=409, detail="Job is not assigned to this worker")
    return job


@router.get("", response_model=list[ExecutionJob])
async def list_jobs(
    run_id: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[ExecutionJob]:
    return await job_queue_service.list_jobs(run_id=run_id, project_id=project_id, status=status, limit=limit)


@router.post("/claim", response_model=ExecutionJob | None)
async def claim_next_job(request: ClaimJobRequest) -> ExecutionJob | None:
    return await job_queue_service.dispatch_next_job(worker_id=request.worker_id, browser=request.browser)


@router.post("/{job_id}/log")
async def append_job_log(job_id: str, payload: WorkerLogPayload) -> dict[str, bool]:
    job = await _assigned_job(job_id, payload.worker_id)
    async with get_session() as session:
        run_repo = TestRunRepository(session)
        run = await run_repo.get_by_id(job.run_id)
        if run is None or run.status in ("CANCELLED", "PASSED", "FAILED", "ERROR"):
            raise HTTPException(status_code=409, detail="Run is no longer active")
        await run_repo.update_run_status(
            job.run_id,
            RunStatus.RUNNING,
            started_at=utc_now() if run.started_at is None else None,
            log_output=((run.log_output or "") + payload.log)[-20000:],
        )
        await session.commit()
    await JobRepository().update_job_status(job_id, JobStatus.RUNNING)
    return {"saved": True}


@router.post("/{job_id}/result", response_model=ExecutionJob)
async def submit_job_result(job_id: str, payload: WorkerResultPayload) -> ExecutionJob:
    job = await _assigned_job(job_id, payload.worker_id)
    async with get_session() as session:
        await get_run_service(session).persist_suite_result(job.run_id, payload.result)
    result = await job_queue_service.complete_job(job_id, duration_ms=payload.result.duration_ms)
    assert result is not None
    return result


@router.post("/{job_id}/complete", response_model=ExecutionJob)
async def complete_job(job_id: str, request: CompleteJobRequest) -> ExecutionJob:
    job = await job_queue_service.complete_job(job_id, duration_ms=request.duration_ms)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/{job_id}/fail", response_model=ExecutionJob)
async def fail_job(job_id: str, request: FailJobRequest) -> ExecutionJob:
    job = await job_queue_service.fail_job(job_id, error_message=request.error_message)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    async with get_session() as session:
        run_repo = TestRunRepository(session)
        run = await run_repo.get_by_id(job.run_id)
        if run is not None and run.status in ("QUEUED", "RUNNING"):
            await run_repo.update_run_status(
                job.run_id,
                RunStatus.ERROR,
                finished_at=utc_now(),
                log_output=((run.log_output or "") + "\nWorker error: " + request.error_message)[-20000:],
            )
            await session.commit()
    return job


@router.post("/{job_id}/cancel", response_model=ExecutionJob)
async def cancel_job(job_id: str) -> ExecutionJob:
    job = await job_queue_service.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
