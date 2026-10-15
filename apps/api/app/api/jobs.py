from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from project_model.models import ClaimJobRequest, CompleteJobRequest, ExecutionJob, FailJobRequest, JobStatus
from pydantic import BaseModel
from qa_core.execution.models import SuiteExecutionResult
from qa_core.failure.redactor import SensitiveRedactor

from app.container import get_job_queue_service
from app.services.job_queue_service import (
    JobAssignmentConflict,
    JobNotFoundError,
    JobQueueService,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class WorkerLogPayload(BaseModel):
    worker_id: str
    log: str


class WorkerResultPayload(BaseModel):
    worker_id: str
    result: SuiteExecutionResult


async def _assigned_job(job_id: str, worker_id: str, service: JobQueueService) -> ExecutionJob:
    try:
        return await service.get_assigned_job(job_id, worker_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    except JobAssignmentConflict:
        raise HTTPException(status_code=409, detail="Job is not assigned to this worker")


@router.get("", response_model=list[ExecutionJob])
async def list_jobs(
    run_id: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    service: JobQueueService = Depends(get_job_queue_service),
) -> list[ExecutionJob]:
    return await service.list_jobs(run_id=run_id, project_id=project_id, status=status, limit=limit)


@router.get("/{job_id}", response_model=ExecutionJob)
async def get_job(job_id: str, service: JobQueueService = Depends(get_job_queue_service)) -> ExecutionJob:
    try:
        return await service.get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@router.post("/claim", response_model=ExecutionJob | None)
async def claim_next_job(
    request: ClaimJobRequest, service: JobQueueService = Depends(get_job_queue_service)
) -> ExecutionJob | None:
    return await service.dispatch_next_job(
        worker_id=request.worker_id,
        browser=request.browser,
        browsers=request.browsers or None,
        project_ids=request.project_ids,
    )


@router.post("/{job_id}/log")
async def append_job_log(
    job_id: str, payload: WorkerLogPayload, service: JobQueueService = Depends(get_job_queue_service)
) -> dict[str, bool]:
    safe_log = SensitiveRedactor.redact_text(payload.log)
    try:
        await service.append_worker_log(job_id, payload.worker_id, safe_log)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    except JobAssignmentConflict:
        raise HTTPException(status_code=409, detail="Run is no longer active or job is not assigned to this worker")
    return {"saved": True}


@router.post("/{job_id}/result", response_model=ExecutionJob)
async def submit_job_result(
    job_id: str, payload: WorkerResultPayload, service: JobQueueService = Depends(get_job_queue_service)
) -> ExecutionJob:
    try:
        return await service.submit_worker_result(job_id, payload.worker_id, payload.result)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    except JobAssignmentConflict:
        raise HTTPException(status_code=409, detail="Job is not assigned to this worker")


@router.post("/{job_id}/complete", response_model=ExecutionJob)
async def complete_job(
    job_id: str, request: CompleteJobRequest, service: JobQueueService = Depends(get_job_queue_service)
) -> ExecutionJob:
    try:
        job = await service.get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Submit an execution result before completing the job")
    return job


@router.post("/{job_id}/fail", response_model=ExecutionJob)
async def fail_job(
    job_id: str, request: FailJobRequest, service: JobQueueService = Depends(get_job_queue_service)
) -> ExecutionJob:
    safe_error = SensitiveRedactor.redact_text(request.error_message)
    try:
        current = await service.get_job(job_id)
        terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
        if current.status not in terminal and not request.worker_id:
            raise JobAssignmentConflict(job_id)
        job = await service.fail_job(job_id, error_message=safe_error, worker_id=request.worker_id)
    except JobAssignmentConflict:
        raise HTTPException(status_code=409, detail="Job is not assigned to this worker")
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    await service.mark_run_error(job.run_id, safe_error)
    return job


@router.post("/{job_id}/cancel", response_model=ExecutionJob)
async def cancel_job(job_id: str, service: JobQueueService = Depends(get_job_queue_service)) -> ExecutionJob:
    job = await service.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
