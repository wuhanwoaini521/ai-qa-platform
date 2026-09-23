from __future__ import annotations

from project_model.models import ClusterStatusSummary, Worker, WorkerCreate, WorkerHeartbeatRequest, WorkerStatus

from app.repositories.job_repo import JobRepository
from app.repositories.worker_repo import WorkerRepository


class WorkerService:
    def __init__(
        self,
        worker_repo: WorkerRepository | None = None,
        job_repo: JobRepository | None = None,
    ) -> None:
        self.worker_repo = worker_repo or WorkerRepository()
        self.job_repo = job_repo or JobRepository()

    async def register_worker(self, data: WorkerCreate, worker_id: str | None = None) -> Worker:
        return await self.worker_repo.register_or_update(data, worker_id)

    async def heartbeat(self, worker_id: str, request: WorkerHeartbeatRequest) -> Worker | None:
        return await self.worker_repo.heartbeat(
            worker_id=worker_id,
            status=request.status,
            current_load=request.current_load,
        )

    async def list_workers(self) -> list[Worker]:
        return await self.worker_repo.list_all()

    async def get_worker(self, worker_id: str) -> Worker | None:
        return await self.worker_repo.get_by_id(worker_id)

    async def delete_worker(self, worker_id: str) -> bool:
        return await self.worker_repo.delete(worker_id)

    async def get_cluster_summary(self) -> ClusterStatusSummary:
        workers = await self.worker_repo.list_all()
        queued_jobs = await self.job_repo.list_jobs(status="QUEUED", limit=200)
        running_jobs = await self.job_repo.list_jobs(status="RUNNING", limit=200)

        online_count = sum(1 for w in workers if w.status == WorkerStatus.ONLINE)
        busy_count = sum(1 for w in workers if w.status == WorkerStatus.BUSY)
        offline_count = sum(1 for w in workers if w.status in (WorkerStatus.OFFLINE, WorkerStatus.LOST))

        total_cap = sum(w.max_concurrency for w in workers if w.status in (WorkerStatus.ONLINE, WorkerStatus.BUSY))
        used_cap = sum(w.current_load for w in workers if w.status in (WorkerStatus.ONLINE, WorkerStatus.BUSY))

        return ClusterStatusSummary(
            total_workers=len(workers),
            online_workers=online_count,
            busy_workers=busy_count,
            offline_workers=offline_count,
            total_concurrency_capacity=total_cap,
            used_concurrency=used_cap,
            queued_jobs_count=len(queued_jobs),
            running_jobs_count=len(running_jobs),
            workers=workers,
        )
