from __future__ import annotations

import re
from pathlib import PurePosixPath

from project_model.models import Breakpoint, BreakpointUpsert, Workspace

from app.ports.task_unit_of_work import TaskUnitOfWorkFactory


class WorkspaceCatalogService:
    """Workspace and debugger catalog use cases with explicit transaction ownership."""

    def __init__(self, repository_scope: TaskUnitOfWorkFactory) -> None:
        self.repository_scope = repository_scope

    async def project_name_for_workspace(self, workspace_id: str) -> str:
        async with self.repository_scope() as repositories:
            project = await repositories.projects.get_by_id(workspace_id)
            return project.name if project else "Automation Project"

    async def list_workspaces(self, project_id: str) -> list[Workspace]:
        async with self.repository_scope() as repositories:
            rows = await repositories.workspaces.list_by_project_id(project_id)
            # Existing workspace/file/run APIs use project_id as the canonical workspace key.
            return [
                Workspace(
                    id=row.project_id,
                    project_id=row.project_id,
                    path=row.path,
                    branch=row.branch,
                    status=row.status,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    async def list_breakpoints(self, workspace_id: str) -> list[Breakpoint]:
        async with self.repository_scope() as repositories:
            return list(await repositories.breakpoints.list_for_workspace(workspace_id))

    async def list_enabled_breakpoints(self, workspace_id: str) -> list[Breakpoint]:
        async with self.repository_scope() as repositories:
            return list(await repositories.breakpoints.list_enabled_for_workspace(workspace_id))

    async def upsert_manual_breakpoint(self, workspace_id: str, payload: BreakpointUpsert) -> Breakpoint:
        if payload.source != "manual":
            raise ValueError("Only manual breakpoints can be changed through this endpoint")
        file_path = payload.file_path.replace("\\", "/")
        path = PurePosixPath(file_path)
        if (
            path.is_absolute()
            or re.match(r"^[A-Za-z]:", file_path)
            or any(part in ("", ".", "..") for part in path.parts)
        ):
            raise ValueError("Breakpoint file_path must be a safe workspace-relative path")
        async with self.repository_scope() as repositories:
            breakpoint = await repositories.breakpoints.upsert_manual(workspace_id, payload, path.as_posix())
            await repositories.commit()
            return breakpoint

    async def delete_breakpoint(self, workspace_id: str, breakpoint_id: str) -> bool:
        async with self.repository_scope() as repositories:
            deleted = await repositories.breakpoints.delete(workspace_id, breakpoint_id)
            if deleted:
                await repositories.commit()
            return deleted
