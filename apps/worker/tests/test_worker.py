import pytest
from worker.daemon import WorkerDaemon


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
