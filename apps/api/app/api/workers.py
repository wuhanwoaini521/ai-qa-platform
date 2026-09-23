from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from project_model.models import ClusterStatusSummary, Worker, WorkerCreate, WorkerHeartbeatRequest

from app.services.worker_service import WorkerService

router = APIRouter(prefix="/workers", tags=["workers"])
worker_service = WorkerService()


@router.get("", response_model=list[Worker])
async def list_workers() -> list[Worker]:
    return await worker_service.list_workers()


@router.get("/cluster-status", response_model=ClusterStatusSummary)
async def get_cluster_status() -> ClusterStatusSummary:
    return await worker_service.get_cluster_summary()


@router.post("", response_model=Worker, status_code=status.HTTP_201_CREATED)
async def register_worker(request: WorkerCreate) -> Worker:
    return await worker_service.register_worker(request)


@router.get("/{worker_id}", response_model=Worker)
async def get_worker(worker_id: str) -> Worker:
    worker = await worker_service.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")
    return worker


@router.post("/{worker_id}/heartbeat", response_model=Worker)
async def worker_heartbeat(worker_id: str, request: WorkerHeartbeatRequest) -> Worker:
    worker = await worker_service.heartbeat(worker_id, request)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")
    return worker


@router.delete("/{worker_id}")
async def delete_worker(worker_id: str) -> dict[str, bool]:
    success = await worker_service.delete_worker(worker_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")
    return {"success": True}
