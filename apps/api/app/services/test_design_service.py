from __future__ import annotations

from project_model.models import (
    TestDesign,
    TestDesignCategory,
    TestDesignCreate,
    TestDesignUpdate,
)

from app.persistence.models import TestDesignORM
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_design_repo import TestDesignRepository


class TestDesignService:
    def __init__(self, test_design_repo: TestDesignRepository, requirement_repo: RequirementRepository) -> None:
        self.test_design_repo = test_design_repo
        self.requirement_repo = requirement_repo

    def _to_dto(self, orm: TestDesignORM) -> TestDesign:
        return TestDesign(
            id=orm.id,
            requirement_id=orm.requirement_id,
            title=orm.title,
            category=TestDesignCategory(orm.category),
            description=orm.description or "",
            risk=orm.risk or "Medium",
            scenario_model=orm.scenario_model or None,
            status=orm.status or "DRAFT",
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def list_by_requirement(self, requirement_id: str) -> list[TestDesign]:
        orms = await self.test_design_repo.list_by_requirement(requirement_id)
        return [self._to_dto(orm) for orm in orms]

    async def get_test_design(self, design_id: str) -> TestDesign | None:
        orm = await self.test_design_repo.get_by_id(design_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def create_test_design(self, data: TestDesignCreate) -> TestDesign:
        from app.services.lifecycle_validation import validate_design_model

        await validate_design_model(self.requirement_repo, data)
        orm = await self.test_design_repo.create(data)
        return self._to_dto(orm)

    async def update_test_design(self, design_id: str, data: TestDesignUpdate) -> TestDesign | None:
        from app.services.lifecycle_validation import validate_design_model

        original = await self.test_design_repo.get_by_id(design_id)
        if not original:
            return None
        merged = TestDesignCreate.model_validate(
            {**self._to_dto(original).model_dump(), **data.model_dump(exclude_unset=True)}
        )
        await validate_design_model(self.requirement_repo, merged)
        orm = await self.test_design_repo.update(design_id, data)
        if not orm:
            return None
        return self._to_dto(orm)
