from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import (
    AutomationBindingORM,
    ExternalArtifactReferenceORM,
    FailureAnalysisORM,
    FailureRecordORM,
    ProjectORM,
    RequirementORM,
    TestCaseORM,
    TestDesignORM,
    TestExecutionORM,
    TestRunORM,
)


class ProjectKnowledgeRepository:
    """Read model queries for the bounded project knowledge graph."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_project_graph(self, project_id: str) -> dict:
        project = await self.session.get(ProjectORM, project_id)
        if not project:
            return {}
        requirements = list(
            (
                await self.session.scalars(
                    select(RequirementORM).where(RequirementORM.project_id == project_id).limit(501)
                )
            ).all()
        )
        cases = list(
            (
                await self.session.scalars(select(TestCaseORM).where(TestCaseORM.project_id == project_id).limit(1001))
            ).all()
        )
        executions = list(
            (
                await self.session.execute(
                    select(TestExecutionORM, TestRunORM)
                    .join(TestRunORM, TestExecutionORM.run_id == TestRunORM.id)
                    .where(TestRunORM.project_id == project_id)
                    .order_by(TestRunORM.created_at.desc(), TestExecutionORM.id)
                    .limit(2001)
                )
            ).all()
        )
        return {
            "project": project,
            "requirements": requirements,
            "cases": cases,
            "executions": executions,
        }

    async def load_designs_and_bindings(self, requirement_ids: set[str], case_ids: set[str]) -> tuple[list, list]:
        designs = list(
            (
                await self.session.scalars(
                    select(TestDesignORM).where(TestDesignORM.requirement_id.in_(requirement_ids)).limit(1001)
                )
            ).all()
        )
        bindings = list(
            (
                await self.session.scalars(
                    select(AutomationBindingORM).where(AutomationBindingORM.test_case_id.in_(case_ids))
                )
            ).all()
        )
        return designs, bindings

    async def load_run_evidence(self, run_ids: set[str]) -> tuple[list, list, list]:
        if not run_ids:
            return [], [], []
        artifacts = list(
            (
                await self.session.scalars(
                    select(ExternalArtifactReferenceORM)
                    .where(ExternalArtifactReferenceORM.run_id.in_(run_ids))
                    .limit(501)
                )
            ).all()
        )
        failures = list(
            (
                await self.session.scalars(
                    select(FailureRecordORM).where(FailureRecordORM.run_id.in_(run_ids)).limit(501)
                )
            ).all()
        )
        analyses = list(
            (
                await self.session.scalars(
                    select(FailureAnalysisORM)
                    .where(FailureAnalysisORM.failure_id.in_([item.id for item in failures[:500]]))
                    .limit(2000)
                )
            ).all()
        )
        return artifacts, failures, analyses
