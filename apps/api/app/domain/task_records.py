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
    cancel_requested_at: datetime | None = None
    cancel_requested_by: str | None = None
    workflow_execution_id: str | None = None
    workflow_definition_id: str | None = None
    workflow_version_id: str | None = None
    workflow_version: int | None = None
    workflow_checksum: str | None = None
    workflow_idempotency_key: str | None = None
    workflow_request_fingerprint: str | None = None

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
            cancel_requested_at=getattr(record, "cancel_requested_at", None),
            cancel_requested_by=getattr(record, "cancel_requested_by", None),
            workflow_execution_id=getattr(record, "workflow_execution_id", None),
            workflow_definition_id=getattr(record, "workflow_definition_id", None),
            workflow_version_id=getattr(record, "workflow_version_id", None),
            workflow_version=getattr(record, "workflow_version", None),
            workflow_checksum=getattr(record, "workflow_checksum", None),
            workflow_idempotency_key=getattr(record, "workflow_idempotency_key", None),
            workflow_request_fingerprint=getattr(record, "workflow_request_fingerprint", None),
        )
