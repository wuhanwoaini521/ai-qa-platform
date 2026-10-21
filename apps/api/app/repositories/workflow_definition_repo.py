from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import WorkflowDefinitionORM, WorkflowDefinitionVersionORM, utc_now


class WorkflowVersionConflict(RuntimeError):
    """The draft changed since the client read it, so the save would overwrite someone else's edit."""


class WorkflowVersionNotFound(LookupError):
    pass


def graph_checksum(graph: dict[str, Any]) -> str:
    """Stable digest of a graph, order-independent for edges and keyed by node order for readability."""
    normalised = {
        "nodes": sorted(
            (
                {
                    "key": node.get("key"),
                    "kind": node.get("kind"),
                    "title": node.get("title") or "",
                    "inputs": node.get("inputs") or {},
                }
                for node in graph.get("nodes") or []
            ),
            key=lambda item: str(item["key"]),
        ),
        "edges": sorted(
            ({"source": edge.get("source"), "target": edge.get("target")} for edge in graph.get("edges") or []), key=str
        ),
    }
    return hashlib.sha256(json.dumps(normalised, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class WorkflowDefinitionRepository:
    """Persist definitions as one mutable draft plus immutable published versions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_definitions(self, project_id: str) -> list[WorkflowDefinitionORM]:
        return list(
            (
                await self.session.execute(
                    select(WorkflowDefinitionORM)
                    .where(WorkflowDefinitionORM.project_id == project_id)
                    .order_by(WorkflowDefinitionORM.created_at)
                )
            ).scalars()
        )

    async def get(self, definition_id: str) -> WorkflowDefinitionORM | None:
        return await self.session.get(WorkflowDefinitionORM, definition_id)

    async def get_version(self, definition_id: str, version: int) -> WorkflowDefinitionVersionORM | None:
        return (
            await self.session.execute(
                select(WorkflowDefinitionVersionORM).where(
                    WorkflowDefinitionVersionORM.definition_id == definition_id,
                    WorkflowDefinitionVersionORM.version == version,
                )
            )
        ).scalar_one_or_none()

    async def draft(self, definition_id: str) -> WorkflowDefinitionVersionORM | None:
        return (
            await self.session.execute(
                select(WorkflowDefinitionVersionORM).where(
                    WorkflowDefinitionVersionORM.definition_id == definition_id,
                    WorkflowDefinitionVersionORM.state == "DRAFT",
                )
            )
        ).scalar_one_or_none()

    async def versions(self, definition_id: str) -> list[WorkflowDefinitionVersionORM]:
        return list(
            (
                await self.session.execute(
                    select(WorkflowDefinitionVersionORM)
                    .where(WorkflowDefinitionVersionORM.definition_id == definition_id)
                    .order_by(WorkflowDefinitionVersionORM.version.desc())
                )
            ).scalars()
        )

    async def create(
        self,
        project_id: str,
        name: str,
        description: str,
        actor_id: str | None,
        graph: dict[str, Any] | None = None,
    ) -> tuple[WorkflowDefinitionORM, WorkflowDefinitionVersionORM]:
        definition = WorkflowDefinitionORM(
            project_id=project_id,
            name=name,
            description=description,
            draft_version=1,
            created_by=actor_id,
        )
        self.session.add(definition)
        await self.session.flush()
        draft = WorkflowDefinitionVersionORM(
            definition_id=definition.id,
            project_id=project_id,
            version=1,
            state="DRAFT",
            graph=graph or {"nodes": [], "edges": []},
            checksum=graph_checksum(graph or {"nodes": [], "edges": []}),
            issues=[],
            created_by=actor_id,
        )
        self.session.add(draft)
        await self.session.flush()
        return definition, draft

    async def save_draft(
        self,
        definition: WorkflowDefinitionORM,
        graph: dict[str, Any],
        issues: list[dict[str, Any]],
        actor_id: str | None,
        base_checksum: str | None = None,
    ) -> WorkflowDefinitionVersionORM:
        draft = await self.draft(definition.id)
        if draft is None:
            raise WorkflowVersionNotFound("This definition has no draft to save into.")
        if base_checksum and draft.checksum != base_checksum:
            raise WorkflowVersionConflict(
                "The draft changed since this page loaded it. Reload the draft before saving."
            )
        draft.graph = graph
        draft.checksum = graph_checksum(graph)
        draft.issues = issues
        draft.created_by = actor_id or draft.created_by
        definition.updated_at = utc_now()
        await self.session.flush()
        return draft

    async def restore_as_draft(
        self, definition: WorkflowDefinitionORM, version: int, actor_id: str | None
    ) -> WorkflowDefinitionVersionORM:
        source = await self.get_version(definition.id, version)
        if source is None:
            raise WorkflowVersionNotFound(f"Version {version} does not exist.")
        return await self.save_draft(definition, dict(source.graph), [], actor_id)

    async def publish(
        self, definition: WorkflowDefinitionORM, issues: list[dict[str, Any]], actor_id: str | None
    ) -> WorkflowDefinitionVersionORM:
        draft = await self.draft(definition.id)
        if draft is None:
            raise WorkflowVersionNotFound("This definition has no draft to publish.")
        if issues:
            raise WorkflowVersionConflict("A workflow with validation issues cannot be published.")
        draft.state = "PUBLISHED"
        draft.published_by = actor_id
        draft.published_at = utc_now()
        definition.published_version = draft.version
        next_version = draft.version + 1
        successor = WorkflowDefinitionVersionORM(
            definition_id=definition.id,
            project_id=definition.project_id,
            version=next_version,
            state="DRAFT",
            graph=dict(draft.graph),
            checksum=draft.checksum,
            issues=[],
            created_by=actor_id,
        )
        self.session.add(successor)
        definition.draft_version = next_version
        definition.updated_at = utc_now()
        await self.session.flush()
        return draft
