from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_model.models import IntegrationAuditEntry, User, UserRole
from project_model.task_models import TaskStatus

from app.repositories.api_key_repo import ApiKeyRepository
from app.repositories.integration_audit_repo import IntegrationAuditRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.security_audit_repo import SecurityAuditRepository
from app.repositories.task_repo import TaskRepository


class AuditQueryService:
    def __init__(self, integration_repo: IntegrationAuditRepository, security_repo: SecurityAuditRepository):
        self.integration_repo = integration_repo
        self.security_repo = security_repo

    async def list_integrations(self, *, system: str | None, limit: int) -> list[IntegrationAuditEntry]:
        rows = await self.integration_repo.list_recent(system=system, limit=limit)
        return [
            IntegrationAuditEntry(
                id=row.id,
                system=row.system,
                action=row.action,
                target_id=row.target_id,
                user_id=row.user_id,
                status=row.status,
                details=row.details or {},
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def list_security(self, *, actor_id: str | None, action: str | None, limit: int) -> list[dict[str, Any]]:
        return await self.security_repo.list_logs(actor_id=actor_id, action=action, limit=limit)


class FlakyQueryService:
    def __init__(self, history_repo: RunHistoryRepository):
        self.history_repo = history_repo

    async def list_flaky_tests(self, *, project_id, min_score, classification):
        return await self.history_repo.list_flaky_tests(
            project_id=project_id, min_score=min_score, classification=classification
        )

    async def get_test_history(self, *, nodeid, project_id, limit):
        return await self.history_repo.get_test_history_detail(nodeid=nodeid, project_id=project_id, limit=limit)


class ApiKeyService:
    def __init__(self, repository: ApiKeyRepository | None = None):
        self.repository = repository or ApiKeyRepository()

    async def create(self, request):
        return await self.repository.create(request)

    async def list_by_user(self, user_id: str):
        return await self.repository.list_by_user(user_id)

    async def delete(self, key_id: str) -> bool:
        return await self.repository.delete(key_id)


class StreamResourceService:
    def __init__(
        self,
        run_repo,
        task_repo,
        project_repo,
        recorder_service,
        debug_session_service,
        discovery_repo=None,
        project_access_repo=None,
    ):
        self.run_repo = run_repo
        self.task_repo = task_repo
        self.project_repo = project_repo
        self.discovery_repo = discovery_repo
        self.project_access_repo = project_access_repo
        self.recorder_service = recorder_service
        self.debug_session_service = debug_session_service

    async def exists(self, kind: str, resource_id: str, owner_id: str, user: User | None = None) -> bool:
        if kind == "run":
            return await self.run_repo.get_by_id(resource_id) is not None
        if kind == "task":
            return await self.task_repo.get(resource_id, owner_id) is not None
        if kind == "lsp":
            return await self.project_repo.get_by_id(resource_id) is not None
        if kind == "recorder":
            return await self.recorder_service.get(resource_id, owner_id) is not None
        if kind == "debug":
            return await self.debug_session_service.get(resource_id, owner_id) is not None
        if kind == "discovery":
            # Project-scoped like the other kinds: a bare existence check would let any caller probe
            # which discovery run ids exist in projects it cannot open.
            if self.discovery_repo is None:
                return False
            row = await self.discovery_repo.get(resource_id)
            if row is None:
                return False
            if user is not None and user.role is UserRole.ADMIN:
                return True
            if self.project_access_repo is None:
                return False
            return row.project_id in await self.project_access_repo.owned_or_shared_project_ids(owner_id)
        return False


@dataclass(frozen=True)
class TaskEventBatch:
    status: str
    events: list[dict[str, Any]]


class TaskEventService:
    """Read-only task event stream access, with one short-lived transaction per poll."""

    TERMINAL = {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.CANCELLED.value,
    }

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def exists(self, task_id: str, owner_id: str) -> bool:
        async with self.session_factory() as session:
            return await TaskRepository(session).get(task_id, owner_id) is not None

    async def read_after(self, task_id: str, owner_id: str, cursor: int) -> TaskEventBatch | None:
        async with self.session_factory() as session:
            repository = TaskRepository(session)
            task = await repository.get(task_id, owner_id)
            if task is None:
                return None
            rows = await repository.events_after(task_id, cursor)
            events = [
                {
                    "id": event.id,
                    "task_id": event.task_id,
                    "type": event.type,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
                for event in rows
            ]
            return TaskEventBatch(status=task.status, events=events)

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        return status in cls.TERMINAL
