from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.persistence.models import TaskArtifactORM, TaskEventORM, TaskEvidenceORM, TaskStepORM
from app.repositories.task_repo import TaskRepository


class TaskEvidenceRepository:
    """Persistence boundary for task evidence, artifacts and their events."""

    def __init__(self, session, tasks: TaskRepository | None = None) -> None:
        self.session = session
        self.tasks = tasks or TaskRepository(session)

    async def add_event(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> TaskEventORM:
        await self.tasks._assert_current_lease(task_id)
        payload = payload or {}
        step_id = payload.get("step_id")
        if isinstance(step_id, str):
            step = await self.session.get(TaskStepORM, step_id)
            if step is None or step.task_id != task_id:
                step_id = None
        event = TaskEventORM(task_id=task_id, step_id=step_id, type=event_type, payload=payload)
        self.session.add(event)
        await self.session.flush()
        return event

    async def add_evidence(self, **values: Any) -> TaskEvidenceORM:
        await self.tasks._assert_current_lease(values["task_id"])
        row = TaskEvidenceORM(id=uuid4().hex, **values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_artifact(self, **values: Any) -> TaskArtifactORM:
        await self.tasks._assert_current_lease(values["task_id"])
        row = TaskArtifactORM(id=uuid4().hex, **values)
        self.session.add(row)
        await self.session.flush()
        return row
