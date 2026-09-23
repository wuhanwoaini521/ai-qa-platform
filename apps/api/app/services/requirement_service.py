from __future__ import annotations

from project_model.models import (
    Requirement,
    RequirementCreate,
    RequirementStatus,
    RequirementUpdate,
)

from app.persistence.models import RequirementORM
from app.repositories.requirement_repo import RequirementRepository


class RequirementService:
    def __init__(self, requirement_repo: RequirementRepository) -> None:
        self.requirement_repo = requirement_repo

    def _to_dto(self, orm: RequirementORM) -> Requirement:
        return Requirement(
            id=orm.id,
            project_id=orm.project_id,
            title=orm.title,
            description=orm.description or "",
            acceptance_criteria=orm.acceptance_criteria or "",
            status=RequirementStatus(orm.status),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def list_requirements(self, project_id: str | None = None) -> list[Requirement]:
        if project_id:
            orms = await self.requirement_repo.list_by_project(project_id)
        else:
            orms = await self.requirement_repo.list_all()
        return [self._to_dto(orm) for orm in orms]

    async def get_requirement(self, req_id: str) -> Requirement | None:
        orm = await self.requirement_repo.get_by_id(req_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def create_requirement(self, data: RequirementCreate) -> Requirement:
        orm = await self.requirement_repo.create(data)
        return self._to_dto(orm)

    async def update_requirement(self, req_id: str, data: RequirementUpdate) -> Requirement | None:
        orm = await self.requirement_repo.update(req_id, data)
        if not orm:
            return None
        return self._to_dto(orm)
