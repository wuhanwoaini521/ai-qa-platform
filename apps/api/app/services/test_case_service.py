from __future__ import annotations

from project_model.models import (
    AutomationBinding,
    AutomationStatus,
    TestCase,
    TestCaseCreate,
    TestCasePriority,
    TestCaseUpdate,
)

from app.persistence.models import TestCaseORM
from app.repositories.test_case_repo import TestCaseRepository


class TestCaseService:
    def __init__(self, test_case_repo: TestCaseRepository) -> None:
        self.test_case_repo = test_case_repo

    def _to_dto(self, orm: TestCaseORM) -> TestCase:
        binding = orm.__dict__.get("binding")
        return TestCase(
            binding=AutomationBinding.model_validate(binding) if binding else None,
            id=orm.id,
            project_id=orm.project_id,
            requirement_id=orm.requirement_id,
            test_design_id=orm.test_design_id,
            title=orm.title,
            preconditions=orm.preconditions or "",
            steps=orm.steps or [],
            expected_result=orm.expected_result or "",
            test_model=orm.test_model or None,
            priority=TestCasePriority(orm.priority),
            automation_status=AutomationStatus(orm.automation_status),
            tags=orm.tags or [],
            external_system=orm.external_system,
            external_case_id=orm.external_case_id,
            external_url=orm.external_url,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def count_test_cases(self) -> int:
        return await self.test_case_repo.count_all()

    async def list_test_cases(self, project_id: str | None = None, limit: int | None = None) -> list[TestCase]:
        if project_id:
            orms = await self.test_case_repo.list_by_project(project_id, limit=limit)
        else:
            orms = await self.test_case_repo.list_all(limit=limit)
        return [self._to_dto(orm) for orm in orms]

    async def get_test_case(self, case_id: str) -> TestCase | None:
        orm = await self.test_case_repo.get_by_id(case_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def create_test_case(self, data: TestCaseCreate) -> TestCase:
        from app.services.lifecycle_validation import validate_case_model

        data = await validate_case_model(self.test_case_repo.session, data)
        orm = await self.test_case_repo.create(data)
        return self._to_dto(orm)

    async def update_test_case(self, case_id: str, data: TestCaseUpdate) -> TestCase | None:
        from app.services.lifecycle_validation import validate_case_model

        original = await self.test_case_repo.get_by_id(case_id)
        if not original:
            return None
        merged = TestCaseCreate.model_validate(
            {**self._to_dto(original).model_dump(), **data.model_dump(exclude_unset=True)}
        )
        checked = await validate_case_model(self.test_case_repo.session, merged)
        data = data.model_copy(update={"requirement_id": checked.requirement_id})
        orm = await self.test_case_repo.update(case_id, data)
        if not orm:
            return None
        return self._to_dto(orm)
