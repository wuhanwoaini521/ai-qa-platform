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
        from project_model.lifecycle import RequirementDocument

        from app.services.lifecycle_validation import input_hash

        document = RequirementDocument.model_validate(orm.qa_model) if orm.qa_model else None
        analyzed = (
            next((item for item in reversed(document.history) if item.status == "SUCCESS"), None) if document else None
        )
        return Requirement(
            analysis_stale=bool(
                analyzed
                and analyzed.input_hash
                != input_hash(orm.title, orm.description or "", orm.acceptance_criteria or "", document)
            ),
            id=orm.id,
            project_id=orm.project_id,
            title=orm.title,
            description=orm.description or "",
            acceptance_criteria=orm.acceptance_criteria or "",
            qa_model=orm.qa_model or None,
            status=RequirementStatus(orm.status),
            external_system=orm.external_system,
            external_id=orm.external_id,
            external_url=orm.external_url,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def count_requirements(self) -> int:
        return await self.requirement_repo.count_all()

    async def list_requirements(self, project_id: str | None = None, limit: int | None = None) -> list[Requirement]:
        if project_id:
            orms = await self.requirement_repo.list_by_project(project_id, limit=limit)
        else:
            orms = await self.requirement_repo.list_all(limit=limit)
        return [self._to_dto(orm) for orm in orms]

    async def get_requirement(self, req_id: str) -> Requirement | None:
        orm = await self.requirement_repo.get_by_id(req_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def create_requirement(self, data: RequirementCreate) -> Requirement:
        if data.qa_model and data.qa_model.history:
            raise ValueError("Analysis history is server-owned; create content without invocation records")
        orm = await self.requirement_repo.create(data)
        return self._to_dto(orm)

    async def update_requirement(self, req_id: str, data: RequirementUpdate) -> Requirement | None:
        from app.services.lifecycle_validation import validate_requirement_replacement

        original = await self.requirement_repo.get_by_id(req_id)
        if not original:
            return None
        history = (original.qa_model or {}).get("history", [])
        if history and history[-1].get("status") == "RUNNING":
            from datetime import datetime, timedelta

            from app.persistence.models import utc_now

            if datetime.fromisoformat(history[-1]["started_at"]) > utc_now() - timedelta(minutes=10):
                raise ValueError("Analysis is running; cancel or wait before editing this requirement")
        if "qa_model" in data.model_fields_set:
            if (not data.qa_model and history) or (
                data.qa_model and [item.model_dump(mode="json") for item in data.qa_model.history] != history
            ):
                raise ValueError("Analysis history is server-owned and cannot be edited")
            if history and data.qa_model and data.qa_model.analysis != self._to_dto(original).qa_model.analysis:
                raise ValueError("Recorded analysis is server-owned; use the analysis workflow to replace it")
            await validate_requirement_replacement(self.requirement_repo.session, req_id, data.qa_model)
        orm = await self.requirement_repo.update(req_id, data)
        if not orm:
            return None
        return self._to_dto(orm)
