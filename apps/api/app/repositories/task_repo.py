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
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.task_records import TaskRecord
from app.persistence.models import (
    AIInvocationORM,
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

    async def create(self, values: dict[str, Any], steps: list[dict[str, Any]]) -> TaskRecord:
        task = TaskORM(id=uuid.uuid4().hex, **values)
        self.session.add(task)
        await self.session.flush()
        for position, spec in enumerate(steps):
            self.session.add(TaskStepORM(id=uuid.uuid4().hex, task_id=task.id, position=position, **spec))
        await self.session.flush()
        await self.add_event(task.id, "task.created", {"type": task.type, "goal": task.goal})
        return TaskRecord.from_record(task)

    async def get(self, task_id: str, owner_id: str | None = None) -> TaskRecord | None:
        stmt = select(TaskORM).where(TaskORM.id == task_id)
        if owner_id:
            stmt = stmt.where(TaskORM.owner_id == owner_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return TaskRecord.from_record(row) if row else None

    async def get_steps(self, task_id: str) -> list[TaskStep]:
        stmt = select(TaskStepORM).where(TaskStepORM.task_id == task_id).order_by(TaskStepORM.position)
        return [
            TaskStep.model_validate(row, from_attributes=True) for row in (await self.session.execute(stmt)).scalars()
        ]

    async def get_step(self, step_id: str) -> TaskStep | None:
        row = await self.session.get(TaskStepORM, step_id)
        return TaskStep.model_validate(row, from_attributes=True) if row else None

    async def get_by_id(self, task_id: str) -> TaskRecord | None:
        row = await self.session.get(TaskORM, task_id)
        return TaskRecord.from_record(row) if row else None

    async def add_step(self, **values: Any) -> TaskStep:
        row = TaskStepORM(id=uuid.uuid4().hex, **values)
        self.session.add(row)
        await self.session.flush()
        return TaskStep.model_validate(row, from_attributes=True)

    async def claim_resume(self, task_id: str, owner_id: str) -> bool:
        result = await self.session.execute(
            update(TaskORM)
            .where(TaskORM.id == task_id, TaskORM.owner_id == owner_id, TaskORM.status == "PAUSED")
            .values(status="RESUMING", updated_at=utc_now())
        )
        return result.rowcount == 1

    async def restore_paused_after_resume_failure(self, task_id: str, owner_id: str) -> bool:
        result = await self.session.execute(
            update(TaskORM)
            .where(TaskORM.id == task_id, TaskORM.owner_id == owner_id, TaskORM.status == "RESUMING")
            .values(status="PAUSED", updated_at=utc_now())
        )
        return result.rowcount == 1

    async def claim_approval(self, task_id: str, owner_id: str, step_id: str) -> bool:
        result = await self.session.execute(
            update(TaskORM)
            .where(
                TaskORM.id == task_id,
                TaskORM.owner_id == owner_id,
                TaskORM.status == "WAITING",
                TaskORM.current_step_id == step_id,
            )
            .values(updated_at=utc_now())
        )
        return result.rowcount == 1

    async def finish_resume(self, task_id: str, owner_id: str, status: str, context: dict[str, Any]) -> bool:
        result = await self.session.execute(
            update(TaskORM)
            .where(TaskORM.id == task_id, TaskORM.owner_id == owner_id, TaskORM.status == "RESUMING")
            .values(
                status=status,
                context=context,
                failure_reason=None,
                finished_at=None,
                updated_at=utc_now(),
            )
        )
        return result.rowcount == 1

    async def claim_replan(
        self, task_id: str, owner_id: str, replan_count: int, instructions: str, inputs: dict[str, Any]
    ) -> bool:
        result = await self.session.execute(
            update(TaskORM)
            .where(
                TaskORM.id == task_id,
                TaskORM.owner_id == owner_id,
                TaskORM.status.in_(["BLOCKED", "FAILED"]),
                TaskORM.replan_count == replan_count,
                TaskORM.replan_count < TaskORM.max_replans,
            )
            .values(
                status="REPLANNING",
                replan_count=TaskORM.replan_count + 1,
                retry_count=TaskORM.retry_count + 1,
                inputs={**inputs, "replan_instructions": instructions[:4000]},
                failure_reason=None,
                finished_at=None,
                current_step_id=None,
                updated_at=utc_now(),
            )
        )
        return result.rowcount == 1

    async def claim_for_execution(self, task_id: str) -> bool:
        result = await self.session.execute(
            update(TaskORM)
            .where(TaskORM.id == task_id, TaskORM.status.in_(["PENDING", "REPLANNING"]))
            .values(status="PLANNING", updated_at=utc_now())
        )
        return result.rowcount == 1

    async def claim_running_step(self, task_id: str, step_id: str, task_status: str) -> TaskStep | None:
        task = await self.session.get(TaskORM, task_id)
        step = await self.session.get(TaskStepORM, step_id)
        if task is None or step is None or task.status in {"CANCELLED", "PAUSING"}:
            return None
        step.status = "RUNNING"
        step.started_at = step.started_at or utc_now()
        task.current_step_id = step.id
        task.status = task_status
        context = task.context or {}
        task.context = {**context, "tool_calls": int(context.get("tool_calls", 0)) + 1}
        await self.session.flush()
        return TaskStep.model_validate(step, from_attributes=True)

    async def await_step_approval(
        self, task_id: str, owner_id: str, current_status: str, step_id: str, next_status: str
    ) -> bool:
        task_claim = await self.session.execute(
            update(TaskORM)
            .where(
                TaskORM.id == task_id,
                TaskORM.owner_id == owner_id,
                TaskORM.status == current_status,
                TaskORM.current_step_id == step_id,
            )
            .values(status=next_status, current_step_id=step_id, updated_at=utc_now())
        )
        if task_claim.rowcount != 1:
            return False
        step_claim = await self.session.execute(
            update(TaskStepORM)
            .where(TaskStepORM.id == step_id, TaskStepORM.status == "RUNNING")
            .values(status="WAITING_FOR_APPROVAL")
        )
        return step_claim.rowcount == 1

    async def update_context(self, task_id: str, **values: Any) -> TaskRecord | None:
        task = await self.session.get(TaskORM, task_id)
        if task is None:
            return None
        task.context = {**(task.context or {}), **values}
        task.updated_at = utc_now()
        await self.session.flush()
        return TaskRecord.from_record(task)

    async def reserve_ai_call(self, task_id: str) -> bool:
        task = await self.session.get(TaskORM, task_id, with_for_update=True)
        if task is None:
            return False
        context = task.context or {}
        used = int(context.get("ai_calls", 0))
        if used >= task.max_ai_calls:
            return False
        task.context = {**context, "ai_calls": used + 1}
        task.updated_at = utc_now()
        await self.session.flush()
        return True

    async def update_inputs(self, task_id: str, **values: Any) -> TaskRecord | None:
        task = await self.session.get(TaskORM, task_id)
        if task is None:
            return None
        task.inputs = {**(task.inputs or {}), **values}
        task.updated_at = utc_now()
        await self.session.flush()
        return TaskRecord.from_record(task)

    async def completed_steps(self, task_id: str) -> list[TaskStep]:
        stmt = (
            select(TaskStepORM)
            .where(TaskStepORM.task_id == task_id, TaskStepORM.status == "COMPLETED")
            .order_by(TaskStepORM.position)
        )
        return [
            TaskStep.model_validate(row, from_attributes=True) for row in (await self.session.execute(stmt)).scalars()
        ]

    async def artifacts_for_task(self, task_id: str) -> list[TaskArtifactORM]:
        stmt = select(TaskArtifactORM).where(TaskArtifactORM.task_id == task_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def ai_invocations_for_task(self, task_id: str) -> list[AIInvocationORM]:
        stmt = select(AIInvocationORM).where(AIInvocationORM.task_id == task_id).order_by(AIInvocationORM.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_steps_for_tasks(self, task_ids: list[str]) -> dict[str, list[TaskStep]]:
        if not task_ids:
            return {}
        stmt = (
            select(TaskStepORM)
            .where(TaskStepORM.task_id.in_(task_ids))
            .order_by(TaskStepORM.task_id, TaskStepORM.position)
        )
        grouped: dict[str, list[TaskStep]] = {}
        for row in (await self.session.execute(stmt)).scalars():
            step = TaskStep.model_validate(row, from_attributes=True)
            grouped.setdefault(step.task_id, []).append(step)
        return grouped

    async def get_detail(self, task: TaskRecord) -> TaskDetail:
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
                    select(TaskEventORM)
                    .where(TaskEventORM.task_id == task.id)
                    .order_by(TaskEventORM.id.desc())
                    .limit(501)
                )
            )
            .scalars()
            .all()
        )
        step_models = steps
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
            decisions=[
                TaskDecision(
                    id=row.id,
                    task_id=row.task_id,
                    step_id=row.step_id,
                    name=row.name,
                    provider=row.provider,
                    choice=row.choice,
                    confidence=row.confidence if row.confidence else None,
                    rationale=row.rationale,
                    escalated=row.escalated,
                    created_at=row.created_at,
                )
                for row in decision_rows
            ],
            events=[TaskEvent.model_validate(row, from_attributes=True) for row in reversed(event_rows[:500])],
            events_truncated=len(event_rows) > 500,
            event_cursor=event_rows[0].id if event_rows else 0,
        )

    async def list(self, owner_id: str, project_id: str | None = None, limit: int = 50) -> list[TaskRecord]:
        stmt = select(TaskORM).where(TaskORM.owner_id == owner_id)
        if project_id:
            stmt = stmt.where(TaskORM.project_id == project_id)
        stmt = stmt.order_by(TaskORM.created_at.desc()).limit(limit)
        return [TaskRecord.from_record(row) for row in (await self.session.execute(stmt)).scalars()]

    async def recent_qa_goals(self, owner_id: str, project_id: str, limit: int = 100) -> list[TaskRecord]:
        stmt = (
            select(TaskORM)
            .where(
                TaskORM.owner_id == owner_id,
                TaskORM.project_id == project_id,
                TaskORM.type == "QA_GOAL",
            )
            .order_by(TaskORM.created_at.desc())
            .limit(limit)
        )
        return [TaskRecord.from_record(row) for row in (await self.session.execute(stmt)).scalars()]

    @staticmethod
    def task_values(row: TaskRecord | TaskORM) -> dict[str, Any]:
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

    async def update_task(self, task_id: str, **values: Any) -> TaskRecord | None:
        task = await self.session.get(TaskORM, task_id)
        if not task:
            return None
        for key, value in values.items():
            setattr(task, key, value)
        task.updated_at = utc_now()
        await self.session.flush()
        return TaskRecord.from_record(task)

    async def update_step(self, step_id: str, **values: Any) -> TaskStep | None:
        step = await self.session.get(TaskStepORM, step_id)
        if not step:
            return None
        for key, value in values.items():
            setattr(step, key, value)
        await self.session.flush()
        return TaskStep.model_validate(step, from_attributes=True)

    async def add_event(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> TaskEventORM:
        payload = payload or {}
        step_id = payload.get("step_id")
        if isinstance(step_id, str):
            step = await self.session.get(TaskStepORM, step_id)
            if step is None or step.task_id != task_id:
                step_id = None
        else:
            step_id = None
        event = TaskEventORM(task_id=task_id, step_id=step_id, type=event_type, payload=payload)
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

    async def unfinished(self) -> list[TaskRecord]:
        stmt = select(TaskORM).where(
            TaskORM.status.in_(["PLANNING", "RUNNING", "VERIFYING", "RETRYING", "REPLANNING", "PAUSING", "RESUMING"])
        )
        return [TaskRecord.from_record(row) for row in (await self.session.execute(stmt)).scalars()]

    async def pending(self, limit: int = 100) -> list[TaskRecord]:
        stmt = (
            select(TaskORM)
            .where(TaskORM.status.in_(["PENDING", "REPLANNING"]))
            .order_by(TaskORM.created_at)
            .limit(limit)
        )
        return [TaskRecord.from_record(row) for row in (await self.session.execute(stmt)).scalars()]

    async def steps_for_task(self, task_id: str) -> list[TaskStep]:
        stmt = select(TaskStepORM).where(TaskStepORM.task_id == task_id)
        return [
            TaskStep.model_validate(row, from_attributes=True) for row in (await self.session.execute(stmt)).scalars()
        ]
