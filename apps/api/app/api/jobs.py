from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from project_model.models import ExecutionJob
from pydantic import BaseModel

from app.services.job_queue_service import JobQueueService

router = APIRouter(prefix="/jobs", tags=["jobs"])
job_queue_service = JobQueueService()


class ClaimJobRequest(BaseModel):
    worker_id: str
    browser: str = "chromium"


class CompleteJobRequest(BaseModel):
    duration_ms: float = 0.0


class FailJobRequest(BaseModel):
    error_message: str


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
    return job


@router.post("/{job_id}/cancel", response_model=ExecutionJob)
async def cancel_job(job_id: str) -> ExecutionJob:
    job = await job_queue_service.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
