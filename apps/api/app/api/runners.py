from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from project_model.models import (
    RunnerHealthStatus,
    RunnerProfile,
    RunnerProfileCreate,
    RunnerProfileUpdate,
)

from app.services.runner_service import RunnerService

router = APIRouter(prefix="/runners", tags=["Runner Platform"])


def get_runner_service() -> RunnerService:
    return RunnerService()


@router.get("", response_model=list[RunnerProfile])
async def list_runners(
    project_id: str | None = Query(default=None),
    service: RunnerService = Depends(get_runner_service),
):
    """List configured test runners (Local, Jenkins, etc.)."""
    return await service.list_runners(project_id=project_id)


@router.post("", response_model=RunnerProfile)
async def create_runner(
    data: RunnerProfileCreate,
    service: RunnerService = Depends(get_runner_service),
):
    """Create a new runner profile configuration."""
    return await service.create_runner(data)


@router.get("/{runner_id}", response_model=RunnerProfile)
async def get_runner(
    runner_id: str,
    service: RunnerService = Depends(get_runner_service),
):
    runner = await service.get_runner(runner_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Runner profile not found")
    return runner


@router.patch("/{runner_id}", response_model=RunnerProfile)
async def update_runner(
    runner_id: str,
    data: RunnerProfileUpdate,
    service: RunnerService = Depends(get_runner_service),
):
    runner = await service.update_runner(runner_id, data)
    if not runner:
        raise HTTPException(status_code=404, detail="Runner profile not found")
    return runner


@router.delete("/{runner_id}")
async def delete_runner(
    runner_id: str,
    service: RunnerService = Depends(get_runner_service),
):
    deleted = await service.delete_runner(runner_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Runner profile not found")
    return {"status": "deleted", "id": runner_id}


@router.get("/{runner_id}/health", response_model=RunnerHealthStatus)
async def check_runner_health(
    runner_id: str,
    service: RunnerService = Depends(get_runner_service),
):
    """Check connectivity and credentials for a specific runner profile."""
    try:
        return await service.check_health(runner_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")
