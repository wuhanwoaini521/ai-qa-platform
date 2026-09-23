from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobType(str, Enum):
    TEST_RUN = "TEST_RUN"
    LOCATOR_HEALING = "LOCATOR_HEALING"
    AI_TEST_GEN = "AI_TEST_GEN"
    BROWSER_EXPLORATION = "BROWSER_EXPLORATION"


class JobState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(BaseModel):
    id: str
    job_type: JobType
    payload: dict[str, Any] = Field(default_factory=dict)
    state: JobState = JobState.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}

    async def enqueue(self, job: Job) -> Job:
        self._jobs[job.id] = job
        await self._queue.put(job)
        return job

    async def dequeue(self, timeout: float | None = None) -> Job | None:
        try:
            if timeout:
                return await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return await self._queue.get()
        except asyncio.TimeoutError:
            return None

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)
