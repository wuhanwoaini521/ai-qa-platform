from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Read-only task state exchanged between repositories and application services."""

    id: str
    type: str
    goal: str
    status: str
    owner_id: str
    project_id: str | None
    workspace_id: str | None
    inputs: dict[str, Any]
    context: dict[str, Any]
    verification: dict[str, Any]
    retry_count: int
    replan_count: int
    max_steps: int
    max_retries: int
    max_replans: int
    max_ai_calls: int
    max_duration_seconds: int
    current_step_id: str | None
    failure_reason: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> TaskRecord:
        return cls(
            id=record.id,
            type=record.type,
            goal=record.goal,
            status=record.status,
            owner_id=record.owner_id,
            project_id=record.project_id,
            workspace_id=record.workspace_id,
            inputs=dict(record.inputs or {}),
            context=dict(record.context or {}),
            verification=dict(record.verification or {}),
            retry_count=record.retry_count,
            replan_count=record.replan_count,
            max_steps=record.max_steps,
            max_retries=record.max_retries,
            max_replans=record.max_replans,
            max_ai_calls=record.max_ai_calls,
            max_duration_seconds=record.max_duration_seconds,
            current_step_id=record.current_step_id,
            failure_reason=record.failure_reason,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            updated_at=record.updated_at,
        )
