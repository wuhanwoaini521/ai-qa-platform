from __future__ import annotations

import uuid
from typing import Any

from project_model.task_models import (
    TaskArtifact,
    TaskDecision,
    TaskDetail,
    TaskEvent,
    TaskEvidence,
    TaskStep,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import (
    TaskArtifactORM,
    TaskDecisionORM,
    TaskEventORM,
    TaskEvidenceORM,
    TaskORM,
    TaskStepORM,
    utc_now,
)


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, values: dict[str, Any], steps: list[dict[str, Any]]) -> TaskORM:
        task = TaskORM(id=uuid.uuid4().hex, **values)
        self.session.add(task)
        await self.session.flush()
        for position, spec in enumerate(steps):
            self.session.add(TaskStepORM(id=uuid.uuid4().hex, task_id=task.id, position=position, **spec))
        await self.session.flush()
        await self.add_event(task.id, "task.created", {"type": task.type, "goal": task.goal})
        return task

    async def get(self, task_id: str, owner_id: str | None = None) -> TaskORM | None:
        stmt = select(TaskORM).where(TaskORM.id == task_id)
        if owner_id:
            stmt = stmt.where(TaskORM.owner_id == owner_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_steps(self, task_id: str) -> list[TaskStepORM]:
        stmt = select(TaskStepORM).where(TaskStepORM.task_id == task_id).order_by(TaskStepORM.position)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_detail(self, task: TaskORM) -> TaskDetail:
        steps = await self.get_steps(task.id)
        evidence_rows = list(
            (
                await self.session.execute(
                    select(TaskEvidenceORM)
                    .where(TaskEvidenceORM.task_id == task.id)
                    .order_by(TaskEvidenceORM.created_at)
                )
            )
            .scalars()
            .all()
        )
        artifact_rows = list(
            (
                await self.session.execute(
                    select(TaskArtifactORM)
                    .where(TaskArtifactORM.task_id == task.id)
                    .order_by(TaskArtifactORM.created_at)
                )
            )
            .scalars()
            .all()
        )
        decision_rows = list(
            (
                await self.session.execute(
                    select(TaskDecisionORM)
                    .where(TaskDecisionORM.task_id == task.id)
                    .order_by(TaskDecisionORM.created_at)
                )
            )
            .scalars()
            .all()
        )
        event_rows = list(
            (
                await self.session.execute(
                    select(TaskEventORM).where(TaskEventORM.task_id == task.id).order_by(TaskEventORM.id)
                )
            )
            .scalars()
            .all()
        )
        step_models = [TaskStep.model_validate(row, from_attributes=True) for row in steps]
        return TaskDetail(
            **self.task_values(task),
            plan=step_models,
            steps=step_models,
            evidence=[
                TaskEvidence(
                    id=row.id,
                    task_id=row.task_id,
                    step_id=row.step_id,
                    type=row.type,
                    source=row.source,
                    summary=row.summary,
                    content=row.content,
                    artifact_id=row.artifact_id,
                    metadata=row.metadata_json,
                    created_at=row.created_at,
                )
                for row in evidence_rows
            ],
            artifacts=[TaskArtifact.model_validate(row, from_attributes=True) for row in artifact_rows],
            decisions=[TaskDecision.model_validate(row, from_attributes=True) for row in decision_rows],
            events=[TaskEvent.model_validate(row, from_attributes=True) for row in event_rows],
        )

    async def list(self, owner_id: str, project_id: str | None = None, limit: int = 50) -> list[TaskORM]:
        stmt = select(TaskORM).where(TaskORM.owner_id == owner_id)
        if project_id:
            stmt = stmt.where(TaskORM.project_id == project_id)
        stmt = stmt.order_by(TaskORM.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    @staticmethod
    def task_values(row: TaskORM) -> dict[str, Any]:
        return {
            "id": row.id,
            "type": row.type,
            "goal": row.goal,
            "status": row.status,
            "project_id": row.project_id,
            "workspace_id": row.workspace_id,
            "inputs": row.inputs,
            "context": row.context,
            "verification": row.verification,
            "retry_count": row.retry_count,
            "replan_count": row.replan_count,
            "max_steps": row.max_steps,
            "max_retries": row.max_retries,
            "max_replans": row.max_replans,
            "max_ai_calls": row.max_ai_calls,
            "max_duration_seconds": row.max_duration_seconds,
            "current_step_id": row.current_step_id,
            "failure_reason": row.failure_reason,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "updated_at": row.updated_at,
        }

    async def update_task(self, task_id: str, **values: Any) -> TaskORM | None:
        task = await self.get(task_id)
        if not task:
            return None
        for key, value in values.items():
            setattr(task, key, value)
        task.updated_at = utc_now()
        await self.session.flush()
        return task

    async def update_step(self, step_id: str, **values: Any) -> TaskStepORM | None:
        step = await self.session.get(TaskStepORM, step_id)
        if not step:
            return None
        for key, value in values.items():
            setattr(step, key, value)
        await self.session.flush()
        return step

    async def add_event(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> TaskEventORM:
        event = TaskEventORM(task_id=task_id, type=event_type, payload=payload or {})
        self.session.add(event)
        await self.session.flush()
        return event

    async def add_evidence(self, **values: Any) -> TaskEvidenceORM:
        row = TaskEvidenceORM(id=uuid.uuid4().hex, **values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_artifact(self, **values: Any) -> TaskArtifactORM:
        row = TaskArtifactORM(id=uuid.uuid4().hex, **values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_decision(self, **values: Any) -> TaskDecisionORM:
        row = TaskDecisionORM(id=uuid.uuid4().hex, **values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def events_after(self, task_id: str, event_id: int, limit: int = 250) -> list[TaskEventORM]:
        stmt = (
            select(TaskEventORM)
            .where(TaskEventORM.task_id == task_id, TaskEventORM.id > event_id)
            .order_by(TaskEventORM.id)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def unfinished(self) -> list[TaskORM]:
        stmt = select(TaskORM).where(TaskORM.status.in_(["PLANNING", "RUNNING", "VERIFYING", "RETRYING", "REPLANNING"]))
        return list((await self.session.execute(stmt)).scalars().all())

    async def pending(self, limit: int = 100) -> list[TaskORM]:
        stmt = (
            select(TaskORM)
            .where(TaskORM.status.in_(["PENDING", "REPLANNING"]))
            .order_by(TaskORM.created_at)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def steps_for_task(self, task_id: str) -> list[TaskStepORM]:
        stmt = select(TaskStepORM).where(TaskStepORM.task_id == task_id)
        return list((await self.session.execute(stmt)).scalars().all())
