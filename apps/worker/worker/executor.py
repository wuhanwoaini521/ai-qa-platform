from __future__ import annotations

import logging

from qa_core.contracts import ExecutionRequest
from qa_core.fake_adapters import FakeQAOrchestrator

from worker.jobs import InMemoryJobQueue, Job, JobState, JobType, utc_now

logger = logging.getLogger(__name__)


class JobExecutor:
    def __init__(self, queue: InMemoryJobQueue, orchestrator: FakeQAOrchestrator | None = None) -> None:
        self.queue = queue
        self.orchestrator = orchestrator or FakeQAOrchestrator()
        self._running = False

    async def execute_job(self, job: Job) -> Job:
        job.state = JobState.RUNNING
        job.updated_at = utc_now()

        try:
            if job.job_type == JobType.TEST_RUN:
                req = ExecutionRequest(
                    project_id=job.payload.get("project_id", "default"),
                    workspace_path=job.payload.get("workspace_path", "."),
                    test_paths=job.payload.get("test_paths", []),
                )
                report, analyses = await self.orchestrator.orchestrate_run(req)
                job.result = {
                    "report": report.model_dump(),
                    "analyses": [a.model_dump() for a in analyses],
                }
                job.state = JobState.COMPLETED
            else:
                job.result = {"status": "ok", "message": f"Processed fake job {job.job_type}"}
                job.state = JobState.COMPLETED
        except Exception as e:
            logger.exception("Error executing job %s", job.id)
            job.state = JobState.FAILED
            job.error = str(e)

        job.updated_at = utc_now()
        return job

    async def process_one(self, timeout: float = 0.5) -> Job | None:
        job = await self.queue.dequeue(timeout=timeout)
        if job:
            return await self.execute_job(job)
        return None
