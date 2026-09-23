from __future__ import annotations

from project_model.models import (
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
        return TestCase(
            id=orm.id,
            project_id=orm.project_id,
            requirement_id=orm.requirement_id,
            test_design_id=orm.test_design_id,
            title=orm.title,
            preconditions=orm.preconditions or "",
            steps=orm.steps or [],
            expected_result=orm.expected_result or "",
            priority=TestCasePriority(orm.priority),
            automation_status=AutomationStatus(orm.automation_status),
            tags=orm.tags or [],
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def list_test_cases(self, project_id: str | None = None) -> list[TestCase]:
        if project_id:
            orms = await self.test_case_repo.list_by_project(project_id)
        else:
            orms = await self.test_case_repo.list_all()
        return [self._to_dto(orm) for orm in orms]

    async def get_test_case(self, case_id: str) -> TestCase | None:
        orm = await self.test_case_repo.get_by_id(case_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def create_test_case(self, data: TestCaseCreate) -> TestCase:
        orm = await self.test_case_repo.create(data)
        return self._to_dto(orm)

    async def update_test_case(self, case_id: str, data: TestCaseUpdate) -> TestCase | None:
        orm = await self.test_case_repo.update(case_id, data)
        if not orm:
            return None
        return self._to_dto(orm)
