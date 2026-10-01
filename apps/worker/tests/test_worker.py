import pytest
from worker.daemon import WorkerDaemon
from worker.executor import JobExecutor
from worker.jobs import InMemoryJobQueue, Job, JobState, JobType


@pytest.mark.asyncio
async def test_worker_job_execution():
    queue = InMemoryJobQueue()
    executor = JobExecutor(queue)

    job = Job(
        id="job_test_1",
        job_type=JobType.TEST_RUN,
        payload={"project_id": "p1", "workspace_path": "/tmp"},
    )
    await queue.enqueue(job)

    processed = await executor.process_one(timeout=1.0)
    assert processed is not None
    assert processed.state == JobState.COMPLETED
    assert processed.result is not None
    assert "report" in processed.result
    assert processed.result["report"]["total"] == 2


@pytest.mark.asyncio
async def test_worker_observes_durable_job_cancellation():
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "CANCELLED"}

    class Client:
        @staticmethod
        async def get(_url: str):
            return Response()

    daemon = WorkerDaemon()
    daemon._http_client = Client()  # type: ignore[assignment]

    assert await daemon._watch_job_cancellation("job-cancelled") is True
