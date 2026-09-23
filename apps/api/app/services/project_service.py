from __future__ import annotations

from project_model.models import (
    FrameworkType,
    Project,
    ProjectCreate,
    ProjectUpdate,
    WorkspaceCreate,
)

from app.persistence.models import ProjectORM
from app.repositories.project_repo import ProjectRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.workspace_service import WorkspaceService


class ProjectService:
    def __init__(
        self,
        project_repo: ProjectRepository,
        workspace_repo: WorkspaceRepository,
        workspace_service: WorkspaceService,
    ) -> None:
        self.project_repo = project_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service

    def _to_dto(self, orm: ProjectORM) -> Project:
        return Project(
            id=orm.id,
            name=orm.name,
            description=orm.description or "",
            repository_url=orm.repository_url,
            default_branch=orm.default_branch,
            framework_type=FrameworkType(orm.framework_type),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def list_projects(self) -> list[Project]:
        orms = await self.project_repo.list_all()
        return [self._to_dto(orm) for orm in orms]

    async def get_project(self, project_id: str) -> Project | None:
        orm = await self.project_repo.get_by_id(project_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def create_project(self, data: ProjectCreate) -> Project:
        orm = await self.project_repo.create(data)
        # Create workspace record
        ws_create = WorkspaceCreate(project_id=orm.id, branch=data.default_branch)
        ws_path = str(self.workspace_service.get_workspace_dir(orm.id))
        await self.workspace_repo.create(ws_create, path=ws_path)

        if data.bootstrap_workspace:
            await self.workspace_service.initialize_workspace(orm.id, orm.name)

        return self._to_dto(orm)

    async def update_project(self, project_id: str, data: ProjectUpdate) -> Project | None:
        orm = await self.project_repo.update(project_id, data)
        if not orm:
            return None
        return self._to_dto(orm)
