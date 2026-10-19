from __future__ import annotations

from typing import Any

from project_model.task_models import EvidenceType
from qa_core.failure.redactor import SensitiveRedactor

from app.domain.task_records import TaskRecord as TaskExecutionRecord
from app.repositories.task_evidence_repo import TaskEvidenceRepository
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.task_errors import TaskBlocked
from app.services.task_execution_ports import TaskExecutionPorts


class TaskEvidenceService:
    """Own task evidence and artifact creation, persistence, and audit events."""

    def __init__(self, context: TaskExecutionPorts) -> None:
        self.context = context

    async def create_artifact(
        self, task: TaskExecutionRecord, step_key: str, name: str, kind: str, content: bytes, content_type: str
    ) -> dict[str, Any]:
        saved = await ArtifactStorageService().save_artifact(
            name, content, content_type, project_id=task.project_id, created_by=task.owner_id
        )
        return {"artifact_id": saved.artifact_id, "name": name, "kind": kind}

    @staticmethod
    async def build_evidence(
        task: TaskExecutionRecord,
        step_key: str,
        evidence_type: EvidenceType,
        source: str,
        summary: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "type": evidence_type.value,
            "source": source,
            "summary": summary,
            "content": SensitiveRedactor.redact_text(content[:24000]) if content else None,
            "metadata": SensitiveRedactor.redact_value(metadata or {}),
            "artifact_id": artifact_id,
        }

    async def persist_step_outputs(
        self,
        repository: TaskEvidenceRepository,
        task_id: str,
        step_id: str,
        outputs: dict[str, Any],
    ) -> list[str]:
        evidence_ids = []
        for item in outputs.pop("_evidence", []):
            evidence = await repository.add_evidence(
                task_id=task_id,
                step_id=step_id,
                type=item["type"],
                source=item["source"],
                summary=item.get("summary", ""),
                content=item.get("content"),
                artifact_id=item.get("artifact_id"),
                metadata_json=item.get("metadata", {}),
            )
            evidence_ids.append(evidence.id)
            await repository.add_event(
                task_id,
                "evidence.created",
                {"evidence_id": evidence.id, "type": evidence.type, "step_id": step_id},
            )
        for item in outputs.pop("_artifacts", []):
            await repository.add_artifact(task_id=task_id, step_id=step_id, **item)
            await repository.add_event(
                task_id,
                "artifact.created",
                {"artifact_id": item["artifact_id"], "name": item["name"], "step_id": step_id},
            )
        return evidence_ids

    async def persist_artifact(
        self,
        repository: TaskEvidenceRepository,
        task_id: str,
        step_id: str | None,
        artifact: dict[str, Any],
    ) -> None:
        await repository.add_artifact(task_id=task_id, step_id=step_id, **artifact)

    async def emit_browser_event(
        self,
        task_id: str,
        event_type: str,
        title: str,
        summary: str = "",
        *,
        status: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "step_id": self.context.active_runtime_step.get(),
            "title": SensitiveRedactor.redact_text(title)[:200],
            "summary": SensitiveRedactor.redact_text(summary)[:500],
            "status": status,
            "duration_ms": duration_ms,
            **SensitiveRedactor.redact_value(metadata or {}),
        }
        async with self.context.repository_scope() as repositories:
            await repositories.evidence.add_event(task_id, event_type, payload)
            await repositories.commit()

    async def persist_browser_state(
        self,
        task_id: str,
        state: dict[str, Any],
        *,
        title: str,
        summary: str,
        status: str = "RUNNING",
        event_type: str = "browser.agent_progress",
    ) -> None:
        async with self.context.repository_scope() as repositories:
            task_repository = repositories.tasks
            task = await task_repository.update_context(
                task_id,
                browser_agent=SensitiveRedactor.redact_value(state),
            )
            if task is None:
                raise TaskBlocked("Browser task no longer exists.")
            await repositories.evidence.add_event(
                task_id,
                event_type,
                {
                    "step_id": self.context.active_runtime_step.get(),
                    "title": SensitiveRedactor.redact_text(title)[:200],
                    "summary": SensitiveRedactor.redact_text(summary)[:500],
                    "status": status,
                    "current_url": SensitiveRedactor.redact_url(str(state.get("current_url") or ""))[:500],
                    "action_count": len(state.get("history") or []),
                    "goal_completed": bool((state.get("metrics") or {}).get("goal_completion")),
                },
            )
            await repositories.commit()

    async def persist_browser_artifact(self, task_id: str, artifact: dict[str, Any]) -> None:
        step_id = self.context.active_runtime_step.get()
        async with self.context.repository_scope() as repositories:
            repository = repositories.evidence
            await repository.add_artifact(
                task_id=task_id,
                step_id=step_id,
                artifact_id=artifact["artifact_id"],
                name=artifact["name"],
                kind=artifact["kind"],
            )
            await repository.add_event(
                task_id,
                "artifact.created",
                {"step_id": step_id, "artifact_id": artifact["artifact_id"], "name": artifact["name"]},
            )
            await repositories.commit()

    async def persist_browser_evidence(
        self,
        task_id: str,
        evidence_type: EvidenceType,
        source: str,
        summary: str,
        content: str,
        metadata: dict[str, Any],
        artifact_id: str | None = None,
    ) -> None:
        step_id = self.context.active_runtime_step.get()
        async with self.context.repository_scope() as repositories:
            repository = repositories.evidence
            row = await repository.add_evidence(
                task_id=task_id,
                step_id=step_id,
                type=evidence_type.value,
                source=source,
                summary=SensitiveRedactor.redact_text(summary)[:500],
                content=SensitiveRedactor.redact_text(content[:24000]) if content else None,
                metadata_json=SensitiveRedactor.redact_value(metadata),
                artifact_id=artifact_id,
            )
            await repository.add_event(
                task_id,
                "evidence.created",
                {"step_id": step_id, "evidence_id": row.id, "type": evidence_type.value},
            )
            await repositories.commit()

    async def record_ai_trace(self, task_id: str, event: Any) -> None:
        async with self.context.repository_scope() as repositories:
            payload = event.model_dump(mode="json") if callable(getattr(event, "model_dump", None)) else event
            if isinstance(payload, dict):
                payload = {**payload, "step_id": self.context.active_runtime_step.get()}
            await repositories.evidence.add_event(task_id, "ai.trace", SensitiveRedactor.redact_value(payload))
            await repositories.commit()
